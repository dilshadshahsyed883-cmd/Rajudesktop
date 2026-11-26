"""Direct-only YouTube download options migrated from Mera V2."""
from pathlib import Path
from urllib.parse import urlsplit
import os
QUALITY_CHOICES = ("Best available", "1080p", "720p", "480p", "360p", "MP3 audio (192 kbps)")
def is_youtube_url(raw_url):
    try:
        x = urlsplit(raw_url.strip())
        host = (x.hostname or "").lower().rstrip(".")
        return x.scheme in ("https","http") and not x.username and not x.password and (host in ("youtu.be","youtube.com","youtube-nocookie.com") or host.endswith((".youtube.com",".youtube-nocookie.com")))
    except (AttributeError,ValueError):
        return False
def format_for_quality(quality):
    if quality == QUALITY_CHOICES[-1]:
        return "bestaudio/best"
    if quality == QUALITY_CHOICES[0]:
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
    if quality not in QUALITY_CHOICES:
        raise ValueError("Unknown quality selected")
    h = int(quality.removesuffix("p"))
    return f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]"
def make_options(folder,quality,playlist,progress,postprocess,logger,tools):
    folder=Path(folder).expanduser().resolve()
    folder.mkdir(parents=True,exist_ok=True)
    tools=Path(tools)
    exe=".exe" if os.name=="nt" else ""
    ffmpeg=tools/("ffmpeg"+exe)
    ffprobe=tools/("ffprobe"+exe)
    deno=tools/("deno"+exe)
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError("Bundled FFmpeg/FFprobe missing. Reinstall the application.")
    if not deno.is_file():
        raise RuntimeError("Bundled Deno missing. Reinstall the application.")
    opts={"format":format_for_quality(quality),"outtmpl":str(folder/"%(title).145B [%(id)s].%(ext)s"),"ffmpeg_location":str(tools),"js_runtimes":{"deno":{"path":str(deno)}},"merge_output_format":"mp4","noplaylist":not playlist,"windowsfilenames":os.name=="nt","restrictfilenames":False,"continuedl":True,"overwrites":False,"nooverwrites":True,"retries":10,"fragment_retries":10,"extractor_retries":3,"socket_timeout":25,"concurrent_fragment_downloads":3,"progress_hooks":[progress],"postprocessor_hooks":[postprocess],"logger":logger,"quiet":True,"no_warnings":False,"ignoreerrors":False}
    if quality==QUALITY_CHOICES[-1]:
        opts["postprocessors"]=[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    return opts
def direct_download(ydl_type, options, url):
    if not is_youtube_url(url):
        raise ValueError("Invalid YouTube URL")
    options=dict(options)
    options.pop("cookiefile",None)
    options.pop("cookiesfrombrowser",None)
    with ydl_type(options) as ydl:
        return ydl.download([url])
