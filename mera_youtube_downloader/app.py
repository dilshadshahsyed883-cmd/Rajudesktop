"""Mera Downloader desktop host and native bridge."""
import json, os, sys, threading, time, subprocess
from pathlib import Path
from core import QUALITY_CHOICES, is_youtube_url, make_options, direct_download
ROOT=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
SETTINGS=Path.home()/".mera_youtube_downloader_settings.json"
class CancelDownload(Exception): pass
def human_size(n):
    if not isinstance(n,(int,float)): return "?"
    for unit in ("B","KB","MB","GB","TB"):
        if n<1024 or unit=="TB": return f"{n:.1f} {unit}"
        n/=1024
def human_time(n):
    if not isinstance(n,(int,float)) or n<0: return "?"
    m,s=divmod(round(n),60); h,m=divmod(m,60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"
class Logger:
    def __init__(self,api): self.api=api
    def debug(self,s):
        if str(s).startswith(("[download] Destination:","[Merger]","[ExtractAudio]")): self.api._log(s)
    def warning(self,s): self.api._log("Warning: "+str(s))
    def error(self,s): self.api._log("Error: "+str(s))
class Api:
    def __init__(self):
        self._lock=threading.RLock()
        self._cancel=threading.Event()
        self._window=None
        try:
            old=json.loads(SETTINGS.read_text(encoding="utf-8"))
            if not isinstance(old,dict): old={}
        except (OSError,ValueError): old={}
        q=old.get("quality")
        self._settings={"folder":str(old.get("folder") or Path.home()/"Downloads"/"YouTube"),"quality":q if q in QUALITY_CHOICES else "720p","playlist":bool(old.get("playlist",False))}
        self._state={"busy":False,"cancelling":False,"status":"Ready","detail":"Paste a YouTube link to start.","progress":0,"speed":"—","eta":"—","size":"—","logs":[],"outcome":""}
        self._log("Ready. Direct download engine; no browser login.")
    def _set(self,**kw):
        with self._lock: self._state.update(kw)
    def _log(self,line):
        with self._lock:
            self._state["logs"].append(time.strftime("%H:%M:%S")+"  "+str(line).rstrip())
            self._state["logs"]=self._state["logs"][-500:]
    def init(self):
        marker=os.environ.get("MERA_SMOKE_FILE")
        if marker: Path(marker).write_text("React desktop bridge ready",encoding="utf-8")
        with self._lock: return {"settings":dict(self._settings),"qualities":list(QUALITY_CHOICES)}
    def poll(self):
        with self._lock: return {**self._state,"logs":list(self._state["logs"])}
    def save(self,config):
        with self._lock:
            q=config.get("quality")
            if q not in QUALITY_CHOICES: return {"ok":False,"error":"Unknown quality"}
            self._settings={"folder":str(config.get("folder","")),"quality":q,"playlist":bool(config.get("playlist"))}
            try:
                temp=SETTINGS.with_suffix(".tmp")
                temp.write_text(json.dumps(self._settings,ensure_ascii=False,indent=2),encoding="utf-8")
                os.replace(temp,SETTINGS)
            except OSError as exc: return {"ok":False,"error":str(exc)}
        return {"ok":True}
    def paste(self):
        try:
            import pyperclip
            return {"ok":True,"text":pyperclip.paste().strip()}
        except Exception as exc: return {"ok":False,"error":str(exc)}
    def browse(self):
        import webview
        try:
            result=self._window.create_file_dialog(webview.FileDialog.FOLDER)
            return {"ok":True,"folder":result[0] if result else ""}
        except Exception as exc: return {"ok":False,"error":str(exc)}
    def open_folder(self,folder):
        try:
            if not str(folder).strip(): raise ValueError("Select a folder first")
            path=Path(folder).expanduser().resolve()
            path.mkdir(parents=True,exist_ok=True)
            if os.name=="nt": os.startfile(str(path))
            elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            else: subprocess.Popen(["xdg-open",str(path)])
            return {"ok":True}
        except Exception as exc: return {"ok":False,"error":str(exc)}
    def start(self,config):
        with self._lock:
            if self._state["busy"]: return {"ok":False,"error":"Download already running"}
            url=str(config.get("url","")).strip()
            folder=str(config.get("folder","")).strip()
            quality=config.get("quality")
            playlist=bool(config.get("playlist"))
            if not is_youtube_url(url): return {"ok":False,"error":"Paste a valid YouTube URL."}
            if not folder: return {"ok":False,"error":"Select a download folder."}
            if quality not in QUALITY_CHOICES: return {"ok":False,"error":"Select a valid quality."}
            if Path(folder).exists() and not Path(folder).is_dir(): return {"ok":False,"error":"Selected location is not a folder."}
            saved=self.save(config)
            if not saved["ok"]: self._log("Settings not saved: "+saved["error"])
            self._cancel.clear()
            self._set(busy=True,cancelling=False,status="Connecting to YouTube",detail="Checking available formats directly...",progress=0,speed="—",eta="—",size="—",outcome="")
            self._log("Starting download: "+url)
            threading.Thread(target=self._worker,args=(url,folder,quality,playlist),daemon=True).start()
            return {"ok":True}
    def cancel(self):
        with self._lock:
            if self._state["busy"]:
                self._cancel.set()
                self._set(cancelling=True,status="Cancelling",detail="Stopping at next download checkpoint...")
                self._log("Cancel requested; partial files may be kept for resume.")
        return {"ok":True}
    def _worker(self,url,folder,quality,playlist):
        last=0; title=""
        def check_cancel():
            if self._cancel.is_set(): raise CancelDownload("Download cancelled.")
        def progress(d):
            nonlocal last,title
            check_cancel()
            t=(d.get("info_dict") or {}).get("title") or "Video"
            if t!=title:
                title=t; self._log("Video: "+str(title))
            if d.get("status")=="finished":
                self._set(progress=99,status="Processing media",detail="Stream downloaded. Finishing / merging...")
            elif d.get("status")=="downloading":
                now=time.monotonic()
                if now-last<.22: return
                last=now
                n=d.get("downloaded_bytes") or 0
                total=d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                self._set(status="Downloading",detail=str(title),progress=min(99,n*100/total) if total else 0,speed=human_size(d.get("speed"))+"/s" if d.get("speed") else "—",eta=human_time(d.get("eta")),size=human_size(n)+" / "+(human_size(total) if total else "?"))
        def postprocess(d):
            check_cancel()
            if d.get("status")=="started": self._set(status="Processing media",detail="Converting / merging with FFmpeg...",progress=99)
            elif d.get("status")=="finished": self._set(status="Finishing",detail="Saving file...")
        try:
            from yt_dlp import YoutubeDL
            opts=make_options(folder,quality,playlist,progress,postprocess,Logger(self),ROOT/"tools")
            check_cancel()
            code=direct_download(YoutubeDL,opts,url)
            check_cancel()
            if code!=0: raise RuntimeError("yt-dlp returned error code "+str(code))
            self._log("Download complete.")
            self._set(status="Completed",detail="Open Folder to see your downloaded files.",progress=100,outcome="success")
        except Exception as exc:
            if self._cancel.is_set() or isinstance(exc,CancelDownload):
                self._log("Download cancelled.")
                self._set(status="Cancelled",detail="Partial files may remain for resume.",outcome="cancelled")
            else:
                msg=str(exc)
                self._log("Details: "+msg)
                if "requested format" in msg.lower(): msg+=" Try Best available or a lower quality."
                self._set(status="Failed",detail=msg,outcome="error")
        finally:
            self._set(busy=False,cancelling=False)
    def _closing(self):
        with self._lock: busy=self._state["busy"]
        if busy and not self._window.create_confirmation_dialog("Close Mera Downloader","A download is running. Close and cancel it?"): return False
        self._cancel.set()
        return True
def main():
    import webview
    api=Api()
    w=webview.create_window("Mera YouTube Downloader",str(ROOT/"frontend"/"dist"/"index.html"),js_api=api,width=1000,height=780,min_size=(760,650))
    api._window=w
    w.events.closing+=api._closing
    webview.start(gui="edgechromium",http_server=True)
if __name__=="__main__": main()
