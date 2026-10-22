"""Read-only Windows PC resource and codec capability report (no telemetry)."""
from __future__ import annotations
import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

from .media import ffmpeg_path


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("load_percent", ctypes.c_ulong),
        ("total_phys", ctypes.c_ulonglong),
        ("avail_phys", ctypes.c_ulonglong),
        ("total_page", ctypes.c_ulonglong),
        ("avail_page", ctypes.c_ulonglong),
        ("total_virt", ctypes.c_ulonglong),
        ("avail_virt", ctypes.c_ulonglong),
    ]


def available_memory_bytes() -> tuple[int | None, int | None]:
    if platform.system() != "Windows":
        return None, None
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        if ok:
            return status.total_phys, status.avail_phys
    except (OSError, AttributeError):
        pass
    return None, None


def probe(root: str | Path | None = None) -> dict:
    """Read-only inventory. GPU encoders shown only as build capabilities."""
    directory = Path(root or Path.home()).resolve()
    disk = shutil.disk_usage(directory)
    ram_total, ram_avail = available_memory_bytes()
    encoders = []
    try:
        p = subprocess.run([ffmpeg_path(), "-hide_banner", "-encoders"],
                           capture_output=True, text=True, timeout=12)
        body = p.stdout
        encoders = [name for name in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf")
                    if name in body]
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    vram = None
    gpu_name = "Not measured"
    if platform.system() == "Windows":
        try:
            p = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)"],
                capture_output=True, text=True, timeout=8,
            )
            if p.returncode == 0 and p.stdout.strip():
                gpu_name = p.stdout.strip().splitlines()[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
    warnings = []
    if ram_total is not None and ram_total < 8 * 1024**3:
        warnings.append("Less than 8 GiB RAM: low-resolution proxies recommended")
    if disk.free < 10 * 1024**3:
        warnings.append("Less than 10 GiB free scratch space: high-resolution render may be blocked")
    if os.cpu_count() and os.cpu_count() < 4:
        warnings.append("Below four logical cores: multi-layer preview may be slow")
    return {
        "system": platform.platform(),
        "cpu": platform.processor() or "Unknown CPU",
        "logical_cores": os.cpu_count(),
        "ram_total_gib": round(ram_total/1024**3,1) if ram_total else None,
        "ram_available_gib": round(ram_avail/1024**3,1) if ram_avail else None,
        "disk_free_gib": round(disk.free/1024**3,1),
        "disk_total_gib": round(disk.total/1024**3,1),
        "gpu_name": gpu_name,
        "gpu_vram": vram,
        "ffmpeg_encoders_present": encoders,
        "gpu_acceleration_verified": False,
        "warnings": warnings,
    }
