"""CapCut Independent Renderer v0.4 - standalone local desktop application.

No GUI clicking, no CapCut launch, no modifications to draft files.
"""
import os
import sys
import json
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from engine import Draft, executable, render, capability_check
from state import state_folder, save_state, load_state, InstanceLock, completed_for
from power import keep_awake

APP_DIR=Path(__file__).resolve().parent
OUTPUT_DEFAULT=Path.home()/'Documents'/'CapCut_Independent_Exports'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('CapCut Independent Renderer — v0.4 Draft Style + Effects')
        self.geometry('1010x720')
        self.minsize(830,620)
        self.configure(bg='#111827')
        self.items=[]
        self.signal=queue.Queue()
        self.cancel=threading.Event()
        self.active=False
        self.selected_path=None
        self.output=tk.StringVar(value=str(OUTPUT_DEFAULT))
        self.media=tk.StringVar(value='')
        self.preset=tk.StringVar(value='Test 480p')
        self.test=tk.BooleanVar(value=True)
        self.test_length=tk.StringVar(value='60')
        self.caption_fade=tk.BooleanVar(value=False)
        self.mapped_effects=tk.BooleanVar(value=True)
        self.closing=False
        self.state_path=state_folder()/'queue.json'
        self.worker_thread=None
        self.status=tk.StringVar(value='Add a local CapCut project folder. Draft files are never modified.')
        self.percent=tk.DoubleVar(value=0)
        self.build()
        self.restore()
        self.protocol("WM_DELETE_WINDOW",self.close_app)
        self.after(120,self.poll)
        self.check_dependencies()

    def build(self):
        s=ttk.Style(self)
        s.theme_use('clam')
        s.configure('Dark.TFrame',background='#111827')
        s.configure('Section.TFrame',background='#1f2937')
        s.configure('Dark.TLabel',background='#111827',foreground='#e5e7eb',font=('Segoe UI',10))
        s.configure('Muted.TLabel',background='#111827',foreground='#9ca3af',font=('Segoe UI',9))
        s.configure('Header.TLabel',background='#111827',foreground='#f9fafb',font=('Segoe UI',19,'bold'))
        s.configure('Dark.TButton',font=('Segoe UI',9),padding=(10,7))
        s.configure('Dark.Treeview',background='#172033',fieldbackground='#172033',foreground='#e5e7eb',rowheight=29,font=('Segoe UI',9))
        s.configure('Dark.Treeview.Heading',background='#334155',foreground='#ffffff',font=('Segoe UI',9,'bold'))
        s.map('Dark.Treeview',background=[('selected','#1d4ed8')])
        s.configure('Dark.Horizontal.TProgressbar',background='#22c55e',troughcolor='#374151')
        root=ttk.Frame(self,style='Dark.TFrame',padding=18)
        root.pack(fill='both',expand=True)
        ttk.Label(root,text='CapCut Independent Renderer',style='Header.TLabel').pack(anchor='w')
        ttk.Label(root,text='Separate Windows app  •  Reads draft JSON  •  Own FFmpeg export  •  No CapCut GUI',style='Muted.TLabel').pack(anchor='w',pady=(2,12))
        actions=ttk.Frame(root,style='Dark.TFrame');actions.pack(fill='x',pady=(0,10))
        for text,cmd in [('Add Project Folder',self.add_folder),('Add draft JSON',self.add_json),
                         ('Scan local CapCut',self.scan),('Remove selected',self.remove),
                         ('Analyze selected',self.analyze),('Recheck media',self.recheck)]:
            ttk.Button(actions,text=text,command=cmd,style='Dark.TButton').pack(side='left',padx=(0,7))
        order=ttk.Frame(root,style='Dark.TFrame');order.pack(fill='x',pady=(0,7))
        for text,cmd in [('Move up',lambda:self.move(-1)),('Move down',lambda:self.move(1)),('Retry selected / Render again',self.retry)]:
            ttk.Button(order,text=text,command=cmd,style='Dark.TButton').pack(side='left',padx=(0,7))
        ttk.Label(order,text='FIFO saved. Matching completed exports are skipped.',style='Muted.TLabel').pack(side='left',padx=7)
        columns=('project','duration','media','status')
        self.tree=ttk.Treeview(root,columns=columns,show='headings',height=8,style='Dark.Treeview',selectmode='extended')
        for name,title,width in [('project','Project',340),('duration','Timeline',90),('media','Media',155),('status','State',205)]:
            self.tree.heading(name,text=title)
            self.tree.column(name,width=width,anchor=('w' if name in ('project','status') else 'center'),stretch=name=='project')
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        control=ttk.Frame(root,style='Dark.TFrame');control.pack(fill='x',pady=(12,0))
        ttk.Label(control,text='Media relink folder (optional)',style='Dark.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Entry(control,textvariable=self.media).grid(row=0,column=1,sticky='ew',padx=(10,7),pady=3)
        ttk.Button(control,text='Browse',command=self.choose_media).grid(row=0,column=2)
        ttk.Label(control,text='MP4 output folder',style='Dark.TLabel').grid(row=1,column=0,sticky='w',pady=3)
        ttk.Entry(control,textvariable=self.output).grid(row=1,column=1,sticky='ew',padx=(10,7),pady=3)
        ttk.Button(control,text='Browse',command=self.choose_output).grid(row=1,column=2)
        control.grid_columnconfigure(1,weight=1)
        setting=ttk.Frame(root,style='Dark.TFrame');setting.pack(fill='x',pady=(11,8))
        ttk.Label(setting,text='Quality',style='Dark.TLabel').pack(side='left')
        ttk.Combobox(setting,textvariable=self.preset,width=15,values=['Test 480p','720p','1080p','Original'],state='readonly').pack(side='left',padx=(7,19))
        ttk.Checkbutton(setting,text='Short test first',variable=self.test).pack(side='left')
        ttk.Entry(setting,textvariable=self.test_length,width=5).pack(side='left',padx=(6,2))
        ttk.Label(setting,text='seconds',style='Muted.TLabel').pack(side='left')
        ttk.Label(setting,text='(Uncheck to render whole project)',style='Muted.TLabel').pack(side='left',padx=10)
        ttk.Checkbutton(root,text='Add simple caption fade (approximation; replaces no native animations)',variable=self.caption_fade).pack(anchor='w')
        ttk.Checkbutton(root,text='Apply mapped video effects (HDR look approximation; see report)',variable=self.mapped_effects).pack(anchor='w')
        runbar=ttk.Frame(root,style='Dark.TFrame');runbar.pack(fill='x',pady=(5,10))
        self.start_button=ttk.Button(runbar,text='START RENDER QUEUE',command=self.start,style='Dark.TButton')
        self.start_button.pack(side='left')
        ttk.Button(runbar,text='STOP',command=self.stop,style='Dark.TButton').pack(side='left',padx=7)
        ttk.Button(runbar,text='Open output folder',command=self.open_output,style='Dark.TButton').pack(side='left',padx=7)
        ttk.Button(runbar,text='Check FFmpeg',command=self.check_dependencies,style='Dark.TButton').pack(side='left',padx=7)
        ttk.Progressbar(root,maximum=100,variable=self.percent,style='Dark.Horizontal.TProgressbar').pack(fill='x',pady=(2,7))
        ttk.Label(root,textvariable=self.status,style='Muted.TLabel',wraplength=920).pack(anchor='w',pady=(0,8))
        ttk.Label(root,text='Activity & diagnostics',style='Dark.TLabel').pack(anchor='w')
        self.log=tk.Text(root,height=7,bg='#0b1220',fg='#cbd5e1',font=('Consolas',9),relief='flat',wrap='word')
        self.log.pack(fill='both',expand=True,pady=(5,0))
        self.log.insert('end','Independent renderer v0.4. Source caption backgrounds/fonts supported. Mapped HDR look is approximate, not native CapCut.\n')
        self.log.configure(state='disabled')

    def persist(self):
        try:
            save_state(self.state_path,{'version':4,'items':self.items,
                'output':self.output.get(),'media':self.media.get(),'preset':self.preset.get(),
                'test':self.test.get(),'test_length':self.test_length.get(),'caption_fade':self.caption_fade.get(),'mapped_effects':self.mapped_effects.get()})
        except OSError as error:
            self.say('Queue could not be saved: '+str(error))

    def restore(self):
        saved,warning=load_state(self.state_path)
        for key,var in [('output',self.output),('media',self.media),('preset',self.preset),
                        ('test',self.test),('test_length',self.test_length),('caption_fade',self.caption_fade),('mapped_effects',self.mapped_effects)]:
            if key in saved:var.set(saved[key])
        if saved.get('version',0)<4:
            self.caption_fade.set(False)
            self.say('v0.4: added caption fade starts OFF to preserve source appearance; turn it on only if wanted.')
        self.items=saved.get('items',[])
        self.refresh()
        if warning:self.say(warning)
        if self.items:self.say(f'Restored {len(self.items)} queued projects. Press Start to run pending items.')

    def move(self,direction):
        if self.active:return
        selected=self.tree.selection()
        if len(selected)!=1:return
        idx=int(selected[0]);target=idx+direction
        if 0<=target<len(self.items):
            self.items[idx],self.items[target]=self.items[target],self.items[idx]
            self.tree.selection_remove(*selected)
            self.refresh()
            self.tree.selection_set(str(target))

    def retry(self):
        if self.active:return
        for key in self.tree.selection():
            self.items[int(key)]['status']='Ready - retry'
        self.refresh()

    def close_app(self):
        if self.active:
            self.closing=True
            self.stop()
            self.status.set('Stopping render and cleaning temporary files before closing...')
        else:
            self.persist()
            self.destroy()

    def say(self,message):
        self.log.configure(state='normal')
        self.log.insert('end',str(message)+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def check_dependencies(self):
        f=executable('ffmpeg');p=executable('ffprobe')
        self.say(('Ready: FFmpeg + FFprobe found.' if f and p else
                 'FFmpeg missing: Install FFmpeg or place ffmpeg.exe and ffprobe.exe in app/tools/'))

    def add(self,path):
        if self.active:return
        resolved=str(Path(path).resolve())
        if resolved in [a['path'] for a in self.items]:return
        try:
            d=Draft(resolved,self.media.get())
            kinds=f'{sum(s.kind=="video" for s in d.segments)} video, {len(d.captions)} text'
            resolved=str(d.path)
            item={'path':resolved,'name':d.name,'length':d.duration,'media':kinds,
                  'status':('Missing media ('+str(len(d.missing))+')') if d.missing else 'Ready'}
            if resolved in [a['path'] for a in self.items]: return
            if d.caption_errors: item['status']='Blocked: caption parsing'
            self.items.append(item)
            self.refresh()
            self.say(f'Added {d.name} | {d.duration:.1f}s | Missing: {len(d.missing)} | Unsupported warnings: {len(d.warnings)}')
            if d.missing:self.say('  Missing assets: '+('; '.join(d.missing[:3])))
        except Exception as e:
            messagebox.showerror('Cannot read draft',str(e))
            self.say(f'Failed to add: {e}')

    def recheck(self):
        if self.active:return
        ready=0
        blocked=0
        for item in self.items:
            if item['status'].startswith('Verified'): continue
            try:
                d=Draft(item['path'],self.media.get())
                item['status']='Missing media ('+str(len(d.missing))+')' if d.missing else 'Ready'
                if d.caption_errors: item['status']='Blocked: caption parsing'
                if d.missing or d.caption_errors:blocked+=1
                else:ready+=1
            except Exception as e:
                item['status']='Invalid draft'
                blocked+=1
                self.say(f'Recheck failed ({item["name"]}): {e}')
        self.refresh()
        self.say(f'Recheck complete: {ready} ready / {blocked} blocked. Media folder: {self.media.get() or "Original paths"}')

    def add_folder(self):
        p=filedialog.askdirectory(title='Choose CapCut project folder containing draft_content.json')
        if p:self.add(p)

    def add_json(self):
        p=filedialog.askopenfilename(title='Choose CapCut draft file',filetypes=[('JSON files','*.json')])
        if p:self.add(p)

    def scan(self):
        if self.active:return
        base=Path(os.environ.get('LOCALAPPDATA',''))/'CapCut'/'User Data'/'Projects'/'com.lveditor.draft'
        if not base.is_dir():
            messagebox.showinfo('CapCut drafts not found','Default CapCut draft folder not found. Use Add Project Folder instead.\n\n'+str(base))
            return
        found=sorted((p for p in base.iterdir() if p.is_dir() and any((p/x).is_file() for x in ('draft_content.json','draft_info.json'))),
                     key=lambda p:p.stat().st_mtime,reverse=True)
        if not found:
            self.say('No readable draft folders found.')
            return
        # First rough version deliberately scans only most recently changed 20 drafts
        for p in found[:20]:self.add(str(p))
        self.say(f'Scanned newest {min(20,len(found))} of {len(found)} local draft folders.')

    def refresh(self):
        selected=self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i,a in enumerate(self.items):
            mins,sec=divmod(int(a['length']),60)
            self.tree.insert('', 'end',iid=str(i),values=(a['name'],f'{mins:02d}:{sec:02d}',a['media'],a['status']))
        for key in selected:
            if self.tree.exists(key): self.tree.selection_add(key)
        self.persist()

    def select(self,*_):
        ids=self.tree.selection()
        if ids and int(ids[0])<len(self.items):
            self.selected_path=self.items[int(ids[0])]['path']

    def remove(self):
        if self.active:return
        ids=set(int(x) for x in self.tree.selection())
        self.items=[a for i,a in enumerate(self.items) if i not in ids]
        self.refresh()

    def analyze(self):
        if self.active:return
        ids=self.tree.selection()
        if not ids:
            messagebox.showinfo('Select a project','Select one project in the queue to analyze.')
            return
        try:
            a=self.items[int(ids[0])]
            d=Draft(a['path'],self.media.get())
            summary=d.summary()
            output=Path(self.output.get());output.mkdir(parents=True,exist_ok=True)
            report=output/(f'{self._report_name(d.name)}_analysis.json')
            report.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
            self.say(f'Analysis saved: {report}')
            self.say(f'  {summary["video_segments"]} videos; {summary["image_segments"]} images; {summary["audio_segments"]} audio')
            self.say(f'  Captions: {len(d.captions)} parsed, {len(d.caption_errors)} unparsed (block export)')
            self.say(f'  Caption backgrounds: {summary["caption_backgrounds"]}; mapped effects: {summary["effects_mapped"]}')
            self.say(f'  Animation materials: {d.animation_active} active; {d.animation_empty} empty placeholders (not skipped animations)')
            self.say(f'  {len(d.missing)} missing paths; {len(d.warnings)} capability warnings')
            if d.caption_errors:self.say('CAPTION ERRORS:\n'+'\n'.join(d.caption_errors[:20]))
            if d.missing:self.say('MISSING:\n'+'\n'.join('  • '+x for x in d.missing[:20]))
            if d.warnings:self.say('UNSUPPORTED:\n'+'\n'.join('  • '+x for x in d.warnings[:25]))
            messagebox.showinfo('Analysis complete',f'{d.name}\n\nMissing: {len(d.missing)}\nCapability warnings: {len(d.warnings)}\n\nReport: {report}')
        except Exception as e:messagebox.showerror('Analysis error',str(e))

    def _report_name(self,name):
        from engine import safe_name
        return safe_name(name)

    def choose_media(self):
        if self.active:return
        p=filedialog.askdirectory(title='Folder containing source images and video')
        if p:
            self.media.set(p)
            self.recheck()

    def choose_output(self):
        if self.active:return
        p=filedialog.askdirectory(title='Choose MP4 output directory')
        if p:self.output.set(p);self.persist()

    def open_output(self):
        try:
            p=Path(self.output.get()).expanduser();p.mkdir(parents=True,exist_ok=True)
            if sys.platform=='win32':os.startfile(str(p))
            elif sys.platform=='darwin':__import__('subprocess').Popen(['open',str(p)])
            else: __import__('subprocess').Popen(['xdg-open',str(p)])
        except Exception as e: messagebox.showerror('Cannot open folder',str(e))

    def start(self):
        if self.active:return
        if not self.items:
            messagebox.showinfo('Empty queue','Add one or more CapCut projects first.');return
        if not executable('ffmpeg') or not executable('ffprobe'):
            messagebox.showerror('FFmpeg required','FFmpeg and FFprobe not found. Install from https://ffmpeg.org/download.html or put both .exe files into app/tools/.')
            return
        try:
            seconds=int(self.test_length.get()) if self.test.get() else 0
            if self.test.get() and not 1<=seconds<=300: raise ValueError('Test length must be 1–300 seconds.')
        except ValueError as e:
            messagebox.showerror('Invalid test duration',str(e));return
        self.cancel.clear();self.active=True
        self.start_button.configure(state='disabled')
        self.percent.set(0)
        settings={'media':self.media.get(),'output':self.output.get(),'preset':self.preset.get(),
                  'seconds':seconds,'fade':self.caption_fade.get(),'mapped_effects':self.mapped_effects.get(),'renderer_version':'0.4'}
        paths=[(i,a['path']) for i,a in enumerate(self.items) if not completed_for(a,settings)]
        if not paths:
            self.active=False
            self.start_button.configure(state='normal')
            self.say('All queued projects are completed. Select Retry to render them again.')
            return
        self.persist()
        args=(paths,self.media.get(),self.output.get(),self.preset.get(),seconds,self.caption_fade.get(),self.mapped_effects.get())
        self.worker_thread=threading.Thread(target=self.worker,args=args,daemon=False)
        self.worker_thread.start()
        self.say('=== Render queue started ===')

    def worker(self,paths,media,output,preset,seconds,fade,effects_enabled=True):
        try:
            with keep_awake() as held:
                if os.name=='nt' and not held:
                    self.signal.put(('log','Windows sleep prevention could not be enabled. Keep the PC awake while rendering.'))
                App.run_jobs(self,paths,media,output,preset,seconds,fade,effects_enabled)
        except Exception as error:
            self.signal.put(('log','Queue worker stopped: '+str(error)))
        finally:
            self.signal.put(('finished',))

    def run_jobs(self,paths,media,output,preset,seconds,fade,effects_enabled=True):
        for i,path in paths:
            if self.cancel.is_set(): break
            self.signal.put(('state',i,'Analyzing'))
            try:
                draft=Draft(path,media)
                # Always write an inspection report, even for blocked or failed renders.
                analysis_dir=Path(output);analysis_dir.mkdir(parents=True,exist_ok=True)
                from engine import safe_name
                analysis_path=analysis_dir/(safe_name(draft.name)+'_analysis.json')
                analysis_path.write_text(json.dumps(draft.summary(),indent=2,ensure_ascii=False),encoding='utf-8')
                self.signal.put(('log',f'ANALYSIS: {analysis_path}'))
                self.signal.put(('log',f'{draft.name}: {len(draft.warnings)} feature warnings, {len(draft.missing)} missing media.'))
                if draft.missing:
                    self.signal.put(('state',i,'Blocked: Missing media'))
                    self.signal.put(('log','BLOCKED (no export): '+ ' | '.join(draft.missing[:5])))
                    continue
                if draft.caption_errors:
                    self.signal.put(('state',i,'Blocked: caption parsing'))
                    self.signal.put(('log','CAPTION PARSING BLOCKED: '+' | '.join(draft.caption_errors[:5])))
                    continue
                if draft.warnings:self.signal.put(('log','Caption styling is approximate; unsupported effects/animations are listed in the analysis.'))
                self.signal.put(('state',i,'Rendering'))
                def send_progress(v,msg):
                    self.signal.put(('progress',i,v,msg))
                file,report=render(draft,output,preset,seconds,send_progress,self.cancel,caption_fade=fade,effects_enabled=effects_enabled)
                self.signal.put(('log',f'OUTPUT: {file}'))
                self.signal.put(('log',f'REPORT: {report}'))
                settings={'media':media,'output':output,'preset':preset,'seconds':seconds,'fade':fade,'mapped_effects':effects_enabled,'renderer_version':'0.4'}
                self.signal.put(('output',i,str(file),str(report),settings,draft.source_sha256))
                self.signal.put(('state',i,'Verified - limitations'))
            except InterruptedError:
                self.signal.put(('state',i,'Stopped'))
                break
            except Exception as e:
                self.signal.put(('state',i,'Failed'))
                self.signal.put(('log',f'FAILED: {type(e).__name__}: {e}'))
                try:
                    from engine import safe_name
                    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
                    failure={'status':'failed','draft_file':str(path),
                             'error_type':type(e).__name__,'error':str(e)}
                    target=folder/(safe_name(Path(path).parent.name)+'_FAILED.report.json')
                    target.write_text(json.dumps(failure,indent=2,ensure_ascii=False),encoding='utf-8')
                    self.signal.put(('log',f'Failure report: {target}'))
                except Exception as log_error:
                    self.signal.put(('log',f'Could not save failure report: {log_error}'))
                continue

    def stop(self):
        if self.active:
            self.cancel.set()
            self.say('Stop requested. Current FFmpeg task will be terminated.')

    def poll(self):
        try:
            while True:
                item=self.signal.get_nowait();kind=item[0]
                if kind=='log':self.say(item[1])
                elif kind=='state':
                    _,idx,state=item
                    if idx<len(self.items):
                        self.items[idx]['status']=state
                        self.refresh()
                    self.status.set(f'{self.items[idx]["name"]}: {state}')
                elif kind=='output':
                    _,idx,file,report,settings,source_sha256=item
                    self.items[idx]['last_output']=file
                    self.items[idx]['last_report']=report
                    self.items[idx]['last_settings']=settings
                    self.items[idx]['last_source_sha256']=source_sha256
                    self.persist()
                elif kind=='progress':
                    _,idx,v,msg=item
                    self.percent.set(v)
                    self.status.set(f'{self.items[idx]["name"]} • {msg}')
                elif kind=='finished':
                    self.active=False
                    self.start_button.configure(state='normal')
                    self.status.set('Stopped.' if self.cancel.is_set() else 'Queue finished. Check outputs and reports.')
                    self.say('=== Queue ended ===')
                    self.persist()
        except queue.Empty: pass
        if self.closing and not self.active and (not self.worker_thread or not self.worker_thread.is_alive()):
            self.persist()
            self.destroy()
            return
        self.after(120,self.poll)

if __name__=='__main__':
    guard=None
    try:
        guard=InstanceLock(state_folder()/'instance.lock')
        App().mainloop()
    except Exception as error:
        import traceback
        log=state_folder()/'startup_error.txt'
        log.write_text(traceback.format_exc(),encoding='utf-8')
        try:
            root=tk.Tk();root.withdraw()
            messagebox.showerror('Independent renderer',str(error)+'\n\nDetails: '+str(log))
            root.destroy()
        except Exception:
            print(error)
        sys.exit(1)
    finally:
        if guard:guard.close()
