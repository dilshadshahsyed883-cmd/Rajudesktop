"""Guarded Windows CapCut native export with a small Tkinter GUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog,messagebox,ttk

from .core import FileObserver,GuardError,target_file,validate_project_name
from .windows import WindowsCapCut,DIALOG_EXPORT_X,DIALOG_EXPORT_Y

VERSION="0.2.0"

def state_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))/"CapCutNativeExport"

class NativeExportApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"CapCut Native Export — v{VERSION}")
        self.geometry("800x585")
        self.minsize(735,530)
        self.config(bg="#151922")
        self.events=queue.Queue()
        self.busy=False
        self.stop_monitor=threading.Event()
        self.root_dir=state_dir()
        self.root_dir.mkdir(parents=True,exist_ok=True)
        self.settings_path=self.root_dir/"settings.json"
        try:
            cfg=json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            cfg={}
        self.project=tk.StringVar(value=cfg.get("project",""))
        self.output_folder=tk.StringVar(value=cfg.get("output_folder",str(Path.home()/"Videos")))
        self.timeout=tk.StringVar(value=str(cfg.get("timeout_minutes",120)))
        self.armed=tk.BooleanVar(value=False)
        self.status=tk.StringVar(value="Open the project in CapCut before attaching.")
        self._style()
        self._build()
        self.after(130,self._flush)
        self.protocol("WM_DELETE_WINDOW",self._quit)

    def _style(self):
        style=ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame",background="#151922")
        style.configure("TLabel",background="#151922",foreground="#e6e9f0",font=("Segoe UI",10))
        style.configure("Title.TLabel",background="#151922",foreground="#ffffff",font=("Segoe UI",18,"bold"))
        style.configure("Sub.TLabel",background="#151922",foreground="#b0bac9",font=("Segoe UI",9))
        style.configure("TButton",font=("Segoe UI",10),padding=(9,8))
        style.configure("Action.TButton",font=("Segoe UI",10,"bold"),padding=(12,9))
        style.configure("TEntry",font=("Segoe UI",10),padding=7)
        style.configure("TCheckbutton",background="#151922",foreground="#e6e9f0",font=("Segoe UI",9))

    def _build(self):
        root=ttk.Frame(self,padding=(20,16))
        root.pack(fill="both",expand=True)
        ttk.Label(root,text="Native CapCut Export",style="Title.TLabel").pack(anchor="w")
        ttk.Label(root,text="Real CapCut renderer • separate from Z Builder • current project only",style="Sub.TLabel").pack(anchor="w",pady=(2,14))
        form=ttk.Frame(root)
        form.pack(fill="x")
        ttk.Label(form,text="Exact CapCut project name / MP4 name").grid(row=0,column=0,sticky="w")
        ttk.Entry(form,textvariable=self.project,width=51).grid(row=1,column=0,columnspan=2,sticky="ew",pady=(5,11))
        ttk.Label(form,text="Expected output folder (must match CapCut Export to)").grid(row=2,column=0,sticky="w")
        row=ttk.Frame(form)
        row.grid(row=3,column=0,columnspan=2,sticky="ew",pady=(5,11))
        row.columnconfigure(0,weight=1)
        ttk.Entry(row,textvariable=self.output_folder).grid(row=0,column=0,sticky="ew")
        ttk.Button(row,text="Browse",command=self._browse).grid(row=0,column=1,padx=(9,0))
        ttk.Label(form,text="Monitoring timeout (minutes)").grid(row=4,column=0,sticky="w")
        ttk.Entry(form,textvariable=self.timeout,width=12).grid(row=5,column=0,sticky="w",pady=(4,12))
        form.columnconfigure(0,weight=1)
        actions=ttk.Frame(root)
        actions.pack(fill="x",pady=(1,5))
        self.buttons=[]
        for label,callback in [
            ("1  Detect CapCut",self._detect),
            ("2  Open native Export",self._open_export),
            ("3  Preview export click",self._inspect)]:
            btn=ttk.Button(actions,text=label,command=callback)
            btn.pack(side="left",padx=(0,8))
            self.buttons.append(btn)
        ttk.Checkbutton(root,variable=self.armed,
            text="I confirmed CapCut Export Name and Export to folder match the fields above.").pack(anchor="w",pady=(8,9))
        last=ttk.Frame(root)
        last.pack(fill="x")
        self.export_btn=ttk.Button(last,text="4  START NATIVE EXPORT",command=self._start,style="Action.TButton")
        self.export_btn.pack(side="left",padx=(0,10))
        self.buttons.append(self.export_btn)
        ttk.Button(last,text="Stop monitoring",command=self.stop_monitor.set).pack(side="left")
        ttk.Button(last,text="Open log folder",command=lambda:os.startfile(self.root_dir)).pack(side="right")
        self.progress=ttk.Progressbar(root,mode="indeterminate")
        self.progress.pack(fill="x",pady=(12,7))
        ttk.Label(root,textvariable=self.status,style="Sub.TLabel",wraplength=730).pack(anchor="w",pady=(0,8))
        self.log_box=tk.Text(root,height=7,state="disabled",bg="#0c111a",fg="#b7d4ef",
                             relief="flat",padx=8,pady=7,font=("Consolas",9))
        self.log_box.pack(fill="both",expand=True)
        self._log("Audit: CapCut 9.6.0.4097, project 1028. One already-open project per export.")

    def _browse(self):
        initial=self.output_folder.get()
        path=filedialog.askdirectory(initialdir=initial if Path(initial).is_dir() else str(Path.home()))
        if path:
            self.output_folder.set(path)

    def _settings(self):
        return {"project":self.project.get(),
                "output_folder":self.output_folder.get(),
                "timeout_minutes":self.timeout.get()}

    def _save(self):
        temp=self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._settings(),indent=2),encoding="utf-8")
        temp.replace(self.settings_path)

    def _log(self,line):
        line=time.strftime("%H:%M:%S")+"  "+str(line)
        self.log_box.config(state="normal")
        self.log_box.insert("end",line+"\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        try:
            with (self.root_dir/"native_export.log").open("a",encoding="utf-8") as fp:
                fp.write(line+"\n")
        except OSError:
            pass

    def _emit(self,kind,value):
        self.events.put((kind,value))

    def _flush(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=="log":
                    self._log(value)
                elif kind=="status":
                    self.status.set(str(value))
                elif kind=="error":
                    self._log("HALTED: "+str(value))
                    self.status.set("HALTED: "+str(value))
                    messagebox.showerror("Export halted safely",str(value))
                elif kind=="done":
                    self.busy=False
                    self.progress.stop()
                    for btn in self.buttons:
                        btn.config(state="normal")
        except queue.Empty:
            pass
        self.after(130,self._flush)

    def _run(self,fn):
        if self.busy:
            return
        settings=self._settings()  # Read Tk variables on the GUI thread.
        try:
            self._save()
        except OSError as exc:
            messagebox.showerror("Settings",str(exc))
            return
        self.busy=True
        self.stop_monitor.clear()
        self.progress.start(12)
        for btn in self.buttons:
            btn.config(state="disabled")
        def worker():
            try:
                fn(settings)
            except Exception as exc:
                if isinstance(exc,GuardError):
                    try:
                        report,items=WindowsCapCut().diagnostic_report(self.root_dir/"diagnostic_windows.json")
                        self._emit("log",f"Diagnostic saved: {report}; candidate windows: {len(items)}")
                    except Exception as diag_exc:
                        self._emit("log",f"Diagnostic unavailable: {type(diag_exc).__name__}: {diag_exc}")
                self._emit("error",exc)
            finally:
                self._emit("done",None)
        threading.Thread(target=worker,daemon=True).start()

    def _detect(self):
        def worker(settings):
            api=WindowsCapCut()
            try:
                editor=api.editor()
            except GuardError:
                dialog=api.dialog(validate_project_name(settings["project"]))
                self._emit("log",f"CapCut native Export dialog verified directly: {dialog.title}, PID {dialog.pid}")
                self._emit("status","Native Export dialog verified; editor detection not required.")
                return
            self._emit("log",f"Editor confirmed: hwnd={editor.hwnd}, pid={editor.pid}, class={editor.class_name}, size={editor.width}x{editor.height}")
            self._emit("status","CapCut editor detected. You can open native Export.")
        self._run(worker)

    def _open_export(self):
        self.armed.set(False)
        def worker(settings):
            name=validate_project_name(settings["project"])
            api=WindowsCapCut()
            dialog=api.open_export(name)
            snap=self.root_dir/"evidence"/"export_dialog.png"
            api.screenshot(dialog,snap)
            self._emit("log",f"Verified {dialog.title} window hwnd={dialog.hwnd}; screenshot {snap}")
            self._emit("status","Native Export open; verify CapCut Name and Export to fields.")
        self._run(worker)

    def _inspect(self):
        def worker(settings):
            api=WindowsCapCut()
            dialog=api.dialog(validate_project_name(settings["project"]))
            snap=self.root_dir/"evidence"/"export_click_position.png"
            api.screenshot(dialog,snap,marker=(DIALOG_EXPORT_X,DIALOG_EXPORT_Y))
            self._emit("log",f"Red click target preview: {snap}")
            self._emit("status","Inspect the red marker. If it misses the button, do not export.")
            os.startfile(snap)
        self._run(worker)

    def _start(self):
        if not self.armed.get():
            messagebox.showwarning("Check CapCut settings","Confirm the Name and Export to fields first.")
            return
        if not messagebox.askyesno("Start real CapCut export","Start native export of the currently open CapCut project?"):
            return
        def worker(settings):
            name=validate_project_name(settings["project"])
            folder=Path(settings["output_folder"])
            target=target_file(folder,name)
            try:
                minutes=int(settings["timeout_minutes"])
            except ValueError as exc:
                raise GuardError("Monitoring time must be a whole number of minutes.") from exc
            if not 2<=minutes<=720:
                raise GuardError("Monitoring time must be between 2 and 720 minutes.")
            api=WindowsCapCut()
            dialog=api.dialog(name)
            proof=self.root_dir/"evidence"/"pre_export.png"
            api.screenshot(dialog,proof,marker=(DIALOG_EXPORT_X,DIALOG_EXPORT_Y))
            self._emit("log",f"Preflight OK: {dialog.title}; output target absent: {target}")
            point=api.press_export(name)
            self._emit("log",f"Clicked native CapCut Export at {point}; monitoring {target}")
            watcher=FileObserver(target)
            end=time.monotonic()+minutes*60
            last=""
            while time.monotonic()<end:
                if self.stop_monitor.is_set():
                    self._emit("status","Monitoring stopped; CapCut may still be exporting.")
                    return
                success,message=watcher.poll()
                if message!=last:
                    self._emit("status",message)
                    self._emit("log",message)
                    last=message
                if success:
                    self._emit("log",f"OUTPUT VERIFIED: {target}")
                    self._emit("status",f"Native MP4 container verified: {target}")
                    return
                self.stop_monitor.wait(watcher.stable_interval_seconds)
            raise GuardError("Timed out before MP4 finalized. Verify CapCut's Export to location.")
        self._run(worker)

    def _quit(self):
        if self.busy and not messagebox.askyesno("Still monitoring","Close monitor? CapCut export will not be cancelled."):
            return
        self.stop_monitor.set()
        try:
            self._save()
        except OSError:
            pass
        self.destroy()

def main():
    if os.name!="nt":
        raise SystemExit("Native CapCut automation runs only on Windows 10/11.")
    NativeExportApp().mainloop()
