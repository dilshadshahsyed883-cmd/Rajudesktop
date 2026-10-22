"""Offline-only embedded SML backend.

HTTP is bound exclusively to 127.0.0.1. The original SML pages and APIs are
mounted at /self-media-library/ to preserve all UI routes. All data is under
a dedicated Rajudesktop local app folder. External SML, Drive, YouTube and
proxy endpoints cannot be reached by this process's supported API surface.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


BLOCKED_PREFIXES=(
    "/self-media-library/api/v1/media/proxy/",
    "/self-media-library/api/v1/media/imports/",
)
BLOCKED_POST_PATHS={
    "/self-media-library/api/v1/media/imports",
    "/self-media-library/api/v1/media/imports/batch",
}


def configure_backend(data_dir: str | Path) -> Path:
    """Set environment and cross-platform FFmpeg search path before app import."""
    root=Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    os.environ["SML_DATA_ROOT"]=str(root)
    os.environ["SML_OFFLINE_ONLY"]="1"
    os.environ.setdefault("SML_AI_WORKER","1")
    try:
        import imageio_ffmpeg
        exe=Path(imageio_ffmpeg.get_ffmpeg_exe())
        import shutil
        if shutil.which("ffmpeg") is None and exe.is_file():
            # imageio-ffmpeg's bundled executable has a version-specific
            # filename on Windows. The original SML code invokes "ffmpeg".
            runtime=root/"runtime-bin"
            runtime.mkdir(exist_ok=True)
            binary=runtime/("ffmpeg.exe" if os.name=="nt" else "ffmpeg")
            if not binary.is_file() or binary.stat().st_size!=exe.stat().st_size:
                temporary=binary.with_suffix(".new")
                shutil.copy2(exe,temporary)
                os.replace(temporary,binary)
            os.environ["PATH"]=str(runtime)+os.pathsep+os.environ.get("PATH","")
        else:
            os.environ["PATH"]=str(exe.parent)+os.pathsep+os.environ.get("PATH","")
    except (ImportError,OSError):
        pass
    backend=str(Path(__file__).resolve().parent)
    if backend not in sys.path:
        sys.path.insert(0,backend)
    return root


def create_app(data_dir: str | Path, port: int):
    """A unique service process is expected; never share module/global DBs."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    root=configure_backend(data_dir)
    from app import app as sml_app

    outer=FastAPI(title="Rajudesktop Offline SML",docs_url=None,
                  redoc_url=None,openapi_url=None)
    hostname=f"127.0.0.1:{port}"

    @outer.middleware("http")
    async def local_only(request: Request, call_next):
        host=request.headers.get("host","").lower()
        remote=request.client.host if request.client else ""
        if host!=hostname or remote not in {"127.0.0.1","::1"}:
            return JSONResponse({"detail":"Desktop SML localhost access only"},status_code=403)
        origin=request.headers.get("origin","")
        if origin and origin.rstrip("/")!=f"http://{hostname}":
            return JSONResponse({"detail":"External origins cannot access desktop SML"},status_code=403)
        path=request.url.path
        if (path in BLOCKED_POST_PATHS and request.method.upper()!="GET"
            or any(path.startswith(prefix) for prefix in BLOCKED_PREFIXES)):
            return JSONResponse(
                {"detail":"This offline SML action requires an internet service "
                          "and is intentionally disabled on desktop"},
                status_code=409,
            )
        response=await call_next(request)
        response.headers["Cache-Control"]="private, no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        return response

    @outer.get("/__sml_desktop_health")
    async def desktop_health():
        return {"ok":True,"mode":"offline-local","data_path":str(root)}

    # Mounted FastAPI subapps do not reliably run their own lifespan/startup
    # handlers: lift SML's DB migration, image V2 and AI queue initialization
    # into the local parent service explicitly.
    for handler in sml_app.router.on_startup:
        outer.router.add_event_handler("startup",handler)
    for handler in sml_app.router.on_shutdown:
        outer.router.add_event_handler("shutdown",handler)
    outer.mount("/self-media-library",sml_app)
    return outer


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Local-only Self Media Library")
    parser.add_argument("--port",type=int,required=True)
    parser.add_argument("--data-dir",required=True)
    args=parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be in 1024..65535")
    import uvicorn
    uvicorn.run(create_app(args.data_dir,args.port),
                host="127.0.0.1",port=args.port,
                access_log=False,log_level="warning")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
