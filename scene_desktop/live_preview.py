"""Interactive OpenGL-backed layered preview.

Qt's QPainter OpenGL2 engine composites cached decoded images/video frames on
QOpenGLWidget. Decode is CPU/PyAV and asynchronous; this is NOT GPU video
decoding, nor is hardware performance proven until tested on the user's PC.

GPU preview currently approximates expensive color/noise/.cube LUT render
effects; FFmpeg Accurate remains the exact export-preview fallback.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import monotonic

from PySide6.QtCore import QElapsedTimer, Qt, QRectF, QSize, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QImageReader,
                           QPainter, QPen, QPixmap)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from .timeline import StudioProject
from .live_preview_math import (active_layers, active_captions, placement_for,
                                cache_size, classify_gl_renderer,
                                MAX_CACHE_BYTES, PREVIEW_MAX_SIDE,
                                MAX_PARALLEL_DECODERS)

_IMAGE_EXT = {".png",".jpg",".jpeg",".webp",".bmp",".tiff"}
_FRAME_STEP_MS = 40


def _safe_video_frame(source: Path, millisecond: int, side: int) -> QImage:
    """Decode a close frame at target *source* timestamp off the GUI thread.

    The decoding is intentionally done only from a local path; never upload
    source media. Seeking is keyframe aware and bounded to 90 decoded frames.
    """
    import av
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        seconds = max(0.,millisecond/1000.)
        if stream.time_base:
            offset = int(seconds/float(stream.time_base))
            if stream.start_time is not None:
                offset += int(stream.start_time)
            try:
                container.seek(max(0,offset),backward=True,stream=stream)
            except (ValueError,OSError,av.error.FFmpegError):
                pass
        nearest = None
        for count,frame in enumerate(container.decode(stream)):
            if count >= 90:
                break
            nearest = frame
            if frame.pts is None or stream.time_base is None:
                if count:
                    break
                continue
            current = float(frame.pts*stream.time_base)
            if current >= seconds-0.016:
                break
        if nearest is None:
            raise ValueError("Unable to decode requested source frame")
        width,height = nearest.width, nearest.height
        factor = min(1., side/max(1,width,height))
        tw,th=max(2,round(width*factor)),max(2,round(height*factor))
        reduced = nearest.reformat(width=tw,height=th,format="rgb24")
        buffer = reduced.to_ndarray(format="rgb24").tobytes()
        return QImage(buffer,tw,th,tw*3,QImage.Format.Format_RGB888).copy()


def _safe_still_frame(source: Path, unused: int, side: int) -> QImage:
    reader = QImageReader(str(source))
    native = reader.size()
    if native.isValid() and max(native.width(),native.height()) > side:
        native.scale(QSize(side,side),Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(native)
    result = reader.read()
    if result.isNull():
        raise ValueError(f"Cannot read image: {source.name}")
    return result.convertToFormat(QImage.Format.Format_RGB32)


class BoundedFrameProvider:
    """Asynchronous bounded CPU decoder; only GUI thread touches QPixmap."""

    def __init__(self, changed, max_bytes: int = MAX_CACHE_BYTES):
        self.changed = changed
        self.max_bytes=max_bytes
        self.frames: OrderedDict[tuple,QImage]=OrderedDict()
        self.pending: dict[tuple,object]={}
        self.known_errors: dict[str,str]={}
        self.size_bytes=0
        self.generation=0
        self.executor=ThreadPoolExecutor(max_workers=MAX_PARALLEL_DECODERS,
                                         thread_name_prefix="studio-preview")
        self.closed=False

    @staticmethod
    def key(item, at_ms: int):
        source_ms=item.in_ms+max(0,at_ms-item.start_ms)
        bucket=0 if item.kind=="image" else max(0,round(source_ms/_FRAME_STEP_MS))
        return (str(Path(item.asset).resolve()),item.kind,bucket)

    def get(self, item, at_ms: int) -> tuple[tuple,QImage|None]:
        key=self.key(item,at_ms)
        if key in self.frames:
            self.frames.move_to_end(key)
            return key,self.frames[key]
        if (not self.closed and key not in self.pending and
                len(self.pending) < MAX_PARALLEL_DECODERS*2 and
                key[0] not in self.known_errors):
            source=Path(key[0])
            if source.is_file():
                ms=key[2]*_FRAME_STEP_MS
                func=_safe_still_frame if item.kind=="image" else _safe_video_frame
                self.pending[key]=self.executor.submit(func,source,ms,PREVIEW_MAX_SIDE)
        return key,None

    def poll(self):
        if self.closed:
            return
        changed=False
        for key,task in list(self.pending.items()):
            if not task.done():
                continue
            del self.pending[key]
            try:
                frame=task.result()
                if frame.isNull():
                    continue
            except Exception as exc:
                self.known_errors[key[0]]=str(exc)[:160]
                changed=True
                continue
            size=cache_size(frame)
            if size > self.max_bytes:
                continue
            while self.frames and self.size_bytes+size>self.max_bytes:
                _,old=self.frames.popitem(last=False)
                self.size_bytes-=cache_size(old)
            self.frames[key]=frame
            self.size_bytes+=size
            changed=True
        if changed:
            self.changed()

    def reset(self):
        self.frames.clear()
        self.size_bytes=0
        self.known_errors.clear()
        # Old requests may complete, but cannot be reused across generations.
        for work in self.pending.values():
            work.cancel()
        self.pending.clear()

    def close(self):
        self.closed=True
        self.reset()
        self.executor.shutdown(wait=False,cancel_futures=True)


class OpenGLTimelineCanvas(QOpenGLWidget):
    """Multi-layer GPU paint surface, with playhead clock independent of render."""

    positionChanged = Signal(int)
    rendererDetected = Signal(str,str,bool)
    previewError = Signal(str)
    playbackStopped = Signal()

    def __init__(self, parent: QWidget|None=None):
        super().__init__(parent)
        self.setMinimumHeight(175)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.project=StudioProject()
        self.position_ms=0
        self.playing=False
        self._clock=QElapsedTimer()
        self._anchor=0
        self._provider=BoundedFrameProvider(self.update)
        self._pixmaps: OrderedDict[tuple,QPixmap]=OrderedDict()
        self._presented=deque(maxlen=180)
        self._renderer=""
        self._vendor=""
        self._hardware=False
        self._draw_errors=0
        self._last_report=""
        self._tick=QTimer(self)
        self._tick.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick.timeout.connect(self._on_tick)
        self._poll=QTimer(self)
        self._poll.setInterval(20)
        self._poll.timeout.connect(self._poll_sources)
        self._poll.start()

    def initializeGL(self):
        renderer=vendor=""
        try:
            from OpenGL.GL import glGetString,GL_RENDERER,GL_VENDOR
            renderer=(glGetString(GL_RENDERER) or b"").decode("utf-8","replace")
            vendor=(glGetString(GL_VENDOR) or b"").decode("utf-8","replace")
        except (ImportError,RuntimeError,AttributeError):
            pass
        self._renderer=renderer
        self._vendor=vendor
        self._hardware=classify_gl_renderer(renderer,vendor)=="hardware-candidate"
        self.rendererDetected.emit(renderer or "OpenGL renderer unavailable",
                                   vendor or "Unknown",self._hardware)

    def set_project(self, project: StudioProject):
        project.validate()
        self.pause()
        self.project=StudioProject.from_dict(project.to_dict())
        self.position_ms=min(self.position_ms,self.project.duration_ms)
        self._provider.reset()
        self._pixmaps.clear()
        self.update()

    def seek(self, at_ms: int):
        self.position_ms=max(0,min(int(at_ms),self.project.duration_ms))
        if self.playing:
            self._anchor=self.position_ms
            self._clock.restart()
        self.positionChanged.emit(self.position_ms)
        self.update()

    def play(self):
        if self.project.duration_ms<100:
            return
        if self.position_ms >= self.project.duration_ms:
            self.seek(0)
        self._anchor=self.position_ms
        self._clock.restart()
        self.playing=True
        self._tick.start(max(12,round(1000/self.project.fps)))

    def pause(self):
        self._tick.stop()
        self.playing=False

    def _on_tick(self):
        if not self.playing:
            return
        position=self._anchor+self._clock.elapsed()
        if position>=self.project.duration_ms:
            self.seek(self.project.duration_ms)
            self.pause()
            self.playbackStopped.emit()
        else:
            self.position_ms=position
            self.positionChanged.emit(position)
            self.update()

    def _poll_sources(self):
        self._provider.poll()

    def is_hardware(self) -> bool:
        return self._hardware and self.isValid()

    def diagnostics(self) -> dict:
        times=list(self._presented)
        fps=0.
        if len(times)>=2 and times[-1]>times[0]:
            fps=(len(times)-1)/(times[-1]-times[0])
        return {
            "surface": "QOpenGLWidget / Qt GPU-backed QPainter",
            "renderer":self._renderer or "Not initialized",
            "vendor":self._vendor or "Unknown",
            "hardware_renderer_candidate":self.is_hardware(),
            "measured_draw_fps":round(fps,1),
            "frame_cache_mib":round(self._provider.size_bytes/1024**2,1),
            "decode_jobs_pending":len(self._provider.pending),
            "media_errors":list(self._provider.known_errors.values())[:5],
            "note":"CPU PyAV decode; GPU-backed textured composition only. "
                   "Export-only LUT/noise/advanced filters may differ.",
        }

    @staticmethod
    def _bounds(img: QImage, viewport: QRectF):
        iw,ih=img.width(),img.height()
        output_ratio=viewport.width()/max(1.,viewport.height())
        input_ratio=iw/max(1.,ih)
        if input_ratio>output_ratio:
            cropped=ih*output_ratio
            return QRectF((iw-cropped)/2,0,cropped,ih)
        cropped=iw/output_ratio
        return QRectF(0,(ih-cropped)/2,iw,cropped)

    def _get_pixmap(self, key: tuple, image: QImage) -> QPixmap:
        if key in self._pixmaps:
            self._pixmaps.move_to_end(key)
            return self._pixmaps[key]
        pixmap=QPixmap.fromImage(image)
        self._pixmaps[key]=pixmap
        while len(self._pixmaps)>14:
            self._pixmaps.popitem(last=False)
        return pixmap

    def _draw_captions(self, painter: QPainter, viewport: QRectF):
        captions=active_captions(self.project,self.position_ms)
        for item in captions[-2:]:
            style=item.caption_style or {}
            words=style.get("karaoke_words")
            text=item.text.replace("\n"," ").strip()
            if not text:
                continue
            font=QFont("Arial",max(12,round(viewport.height()*.055)))
            font.setBold(True)
            painter.setFont(font)
            metrics=QFontMetricsF(font)
            baseline=viewport.bottom()-max(22,viewport.height()*.07)
            width=metrics.horizontalAdvance(text)
            x=viewport.center().x()-width/2
            painter.setPen(QPen(QColor("#090a0e"),4))
            painter.drawText(QRectF(x-2,baseline-metrics.height(),width+4,
                                   metrics.height()+4),Qt.AlignmentFlag.AlignCenter,text)
            if isinstance(words,list) and words:
                cursor=x
                progress=self.position_ms-item.start_ms
                for word in words:
                    span=str(word.get("word",""))+" "
                    on=progress >= int(word.get("start_ms",0))
                    painter.setPen(QColor("#ffe36b") if on else QColor("#f6f9ff"))
                    painter.drawText(int(cursor),int(baseline),span)
                    cursor+=metrics.horizontalAdvance(span)
            else:
                painter.setPen(QColor("#f6f9ff"))
                painter.drawText(int(x),int(baseline),text)

    def paintGL(self):
        if self.width()<2 or self.height()<2:
            return
        painter=QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,True)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
            painter.fillRect(self.rect(),QColor("#0b0d12"))
            canvas=QRectF(self.rect())
            project_ratio=self.project.width/max(1.,self.project.height)
            view_ratio=canvas.width()/max(1.,canvas.height())
            if view_ratio>project_ratio:
                w=canvas.height()*project_ratio
                frame=QRectF((canvas.width()-w)/2,0,w,canvas.height())
            else:
                h=canvas.width()/project_ratio
                frame=QRectF(0,(canvas.height()-h)/2,canvas.width(),h)
            painter.fillRect(frame,QColor("#05080c"))
            for item in active_layers(self.project,self.position_ms):
                key,img=self._provider.get(item,self.position_ms)
                if img is None:
                    continue
                pix=self._get_pixmap(key,img)
                pos=placement_for(item,self.position_ms,self.project.width,
                                  self.project.height)
                if pos.opacity<.001:
                    continue
                painter.save()
                painter.setClipRect(frame)
                painter.setOpacity(pos.opacity)
                center=frame.center()
                painter.translate(center)
                painter.translate(pos.translate_x*frame.width()/self.project.width,
                                  pos.translate_y*frame.height()/self.project.height)
                painter.rotate(pos.rotation)
                painter.scale(-pos.zoom if pos.mirror else pos.zoom,pos.zoom)
                dst=QRectF(-frame.width()/2,-frame.height()/2,
                            frame.width(),frame.height())
                painter.drawPixmap(dst,pix,self._bounds(img,dst))
                # Preview-only grade hint. Full LUT/noise/color processing belongs
                # to the FFmpeg Accurate renderer, not GPU parity claims.
                if abs(pos.brightness)>.01:
                    c=QColor("white") if pos.brightness>0 else QColor("black")
                    c.setAlphaF(min(.40,abs(pos.brightness)*.38))
                    painter.setOpacity(pos.opacity)
                    painter.fillRect(dst,c)
                painter.restore()
            self._draw_captions(painter,frame)
            if not active_layers(self.project,self.position_ms):
                painter.setPen(QColor("#9faec0"))
                painter.drawText(frame,Qt.AlignmentFlag.AlignCenter,
                                 "GPU Preview — add media to the timeline")
            self._presented.append(monotonic())
        except Exception as exc:
            self._draw_errors+=1
            if self._draw_errors<3:
                self.previewError.emit(str(exc))
        finally:
            painter.end()

    def shutdown(self):
        self.pause()
        self._poll.stop()
        self._provider.close()
        self._pixmaps.clear()
