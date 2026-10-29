#!/usr/bin/env python3
"""cc.py - CapCut desktop control CLI for agents (Windows).

UI Automation tree + screenshots + mouse/keyboard input, all in physical screen pixels.
Run with the skill venv:  scripts\\.venv\\Scripts\\python.exe scripts\\cc.py <command> -h
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import math
import re
import subprocess
import sys
import time
import winreg
from pathlib import Path

# Must happen before anything reads screen metrics: makes UIA rects, screenshots and
# SetCursorPos all agree in physical pixels at any display scale.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKILL_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = SKILL_DIR / "evidence"
LAST_NODES = EVIDENCE_DIR / ".last_nodes.json"
PROCESS_NAMES = {"capcut.exe"}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

INTERACTIVE_TYPES = {
    "ButtonControl", "CheckBoxControl", "ComboBoxControl", "EditControl", "HyperlinkControl",
    "ListItemControl", "MenuItemControl", "RadioButtonControl", "SliderControl", "SpinnerControl",
    "TabItemControl", "TreeItemControl", "SplitButtonControl", "DataItemControl", "ScrollBarControl",
    "MenuBarControl", "ToolBarControl", "TabControl", "ListControl", "MenuControl",
}


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2) if not isinstance(obj, str) else obj)


# ----------------------------------------------------------------------------- windows

def _proc_path(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def _window_rect(hwnd) -> list[int]:
    r = wt.RECT()
    # Extended frame bounds exclude the invisible resize border Windows 10 adds.
    if dwmapi.DwmGetWindowAttribute(wt.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    return [r.left, r.top, r.right, r.bottom]


def capcut_windows() -> list[dict]:
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        path = _proc_path(pid.value)
        if Path(path).name.lower() not in PROCESS_NAMES:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, title, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        minimized = bool(user32.IsIconic(hwnd))
        rect = _window_rect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if minimized or (w > 20 and h > 20):
            try:
                dpi = user32.GetDpiForWindow(hwnd)
            except Exception:
                dpi = 96
            found.append(dict(hwnd=int(hwnd), pid=pid.value, title=title.value, cls=cls.value,
                              rect=rect, size=[w, h], minimized=minimized,
                              maximized=bool(user32.IsZoomed(hwnd)), dpi=dpi,
                              scale=round(dpi / 96, 2), exe=path))
        return True

    user32.EnumWindows(cb, 0)
    found.sort(key=lambda d: d["size"][0] * d["size"][1], reverse=True)
    return found


def main_window(title: str | None = None) -> dict:
    wins = capcut_windows()
    if title:
        wins = [w for w in wins if title.lower() in w["title"].lower()]
    if not wins:
        die("No visible CapCut window. Launch CapCut (cc.py launch) and try again.")
    # The main editor/home window is the largest one; minimized windows have no size, prefer
    # a normal window if one exists.
    normal = [w for w in wins if not w["minimized"]]
    return (normal or wins)[0]


def focus_window(w: dict, maximize: bool = False) -> bool:
    hwnd = wt.HWND(w["hwnd"])
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if maximize:
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    my_thread = kernel32.GetCurrentThreadId()
    attached = False
    if fg_thread and fg_thread != my_thread:
        attached = bool(user32.AttachThreadInput(my_thread, fg_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_thread, fg_thread, False)
    time.sleep(0.35)
    return user32.GetForegroundWindow() == w["hwnd"]


def ensure_focus(args):
    if getattr(args, "no_focus", False):
        return
    w = main_window(getattr(args, "title", None))
    fg = user32.GetForegroundWindow()
    fg_ids = {c["hwnd"] for c in capcut_windows()}
    if fg not in fg_ids:
        if not focus_window(w):
            print("WARN: could not confirm CapCut is foreground; input may go elsewhere.", file=sys.stderr)


# ----------------------------------------------------------------------------- input

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


def _send(*inputs: INPUT):
    arr = (INPUT * len(inputs))(*inputs)
    n = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if n != len(inputs):
        die(f"SendInput blocked ({n}/{len(inputs)} events). CapCut elevated, secure desktop, "
            "or the agent sandbox is preventing desktop input.")


def _kev(vk=0, scan=0, flags=0) -> INPUT:
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def _mev(flags, data=0) -> INPUT:
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(0, 0, ctypes.c_ulong(data & 0xFFFFFFFF).value, flags, 0, 0)
    return i


VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "plus": 0xBB, "=": 0xBB, "minus": 0xBD, "-": 0xBD, ",": 0xBC, "comma": 0xBC, ".": 0xBE,
    "period": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE, "[": 0xDB, "]": 0xDD, "\\": 0xDC, "`": 0xC0,
    "bracketleft": 0xDB, "leftbracket": 0xDB, "bracketright": 0xDD, "rightbracket": 0xDD,
    "apps": 0x5D, "menu": 0x5D,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5B, 0x5D}


def _vk_for(name: str) -> int:
    k = name.lower()
    if k in VK:
        return VK[k]
    if len(k) == 1 and k.isalnum():
        return ord(k.upper())
    die(f"Unknown key '{name}'")


def press_combo(combo: str, hold: float = 0.03):
    parts = [p for p in re.split(r"\+(?!$)", combo) if p]
    vks = [_vk_for(p) for p in parts]
    downs = [_kev(v, 0, 1 if v in EXTENDED else 0) for v in vks]
    ups = [_kev(v, 0, (1 if v in EXTENDED else 0) | 0x2) for v in reversed(vks)]
    _send(*downs)
    time.sleep(hold)
    _send(*ups)


def type_unicode(text: str, delay: float = 0.005):
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        _send(_kev(0, unit, 0x4), _kev(0, unit, 0x4 | 0x2))
        if delay:
            time.sleep(delay)


def move_to(x: int, y: int):
    if not user32.SetCursorPos(int(x), int(y)):
        die("SetCursorPos failed")
    _send(_mev(0x0001))  # zero relative move so apps see WM_MOUSEMOVE


BUTTONS = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}


def click_at(x: int, y: int, button="left", count=1, modifiers: list[str] | None = None):
    mods = [_vk_for(m) for m in (modifiers or [])]
    if mods:
        _send(*[_kev(v) for v in mods])
    move_to(x, y)
    time.sleep(0.05)
    down, up = BUTTONS[button]
    for _ in range(count):
        _send(_mev(down))
        time.sleep(0.02)
        _send(_mev(up))
        time.sleep(0.06)
    if mods:
        _send(*[_kev(v, 0, 0x2) for v in reversed(mods)])


def drag(x1, y1, x2, y2, steps=20, hold=0.15, button="left"):
    down, up = BUTTONS[button]
    move_to(x1, y1)
    time.sleep(0.05)
    _send(_mev(down))
    time.sleep(hold)
    for i in range(1, steps + 1):
        t = i / steps
        move_to(round(x1 + (x2 - x1) * t), round(y1 + (y2 - y1) * t))
        time.sleep(0.015)
    time.sleep(hold)
    _send(_mev(up))


def scroll_at(x, y, clicks: int, horizontal=False, modifiers: list[str] | None = None):
    mods = [_vk_for(m) for m in (modifiers or [])]
    move_to(x, y)
    if mods:
        _send(*[_kev(v) for v in mods])
    flag = 0x1000 if horizontal else 0x0800
    for _ in range(abs(clicks)):
        _send(_mev(flag, 120 if clicks > 0 else -120))
        time.sleep(0.04)
    if mods:
        _send(*[_kev(v, 0, 0x2) for v in reversed(mods)])


def set_clipboard(text: str):
    # PowerShell's Set-Clipboard handles Unicode without extra dependencies.
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                   input=text.encode("utf-8"), check=True)


# ----------------------------------------------------------------------------- UIA

def uia():
    try:
        import uiautomation as auto  # noqa
    except ImportError:
        die("uiautomation not installed. Run scripts\\setup.ps1 and use scripts\\.venv\\Scripts\\python.exe")
    auto.SetGlobalSearchTimeout(2)
    return auto


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


PATTERN_NAMES = ["Invoke", "Toggle", "SelectionItem", "ExpandCollapse", "Value", "RangeValue",
                 "ScrollItem", "Scroll", "Selection", "LegacyIAccessible"]


def node_info(auto, c, depth: int, idx: int, patterns: bool) -> dict:
    r = _safe(lambda: c.BoundingRectangle)
    rect = [r.left, r.top, r.right, r.bottom] if r else None
    d = dict(i=idx, depth=depth, type=_safe(lambda: c.ControlTypeName, "?"),
             name=_safe(lambda: c.Name, "") or "", id=_safe(lambda: c.AutomationId, "") or "",
             cls=_safe(lambda: c.ClassName, "") or "", rect=rect,
             enabled=_safe(lambda: c.IsEnabled, None), offscreen=_safe(lambda: c.IsOffscreen, None))
    if patterns:
        d["help"] = _safe(lambda: c.HelpText, "") or ""
        d["focusable"] = _safe(lambda: c.IsKeyboardFocusable, None)
        d["focused"] = _safe(lambda: c.HasKeyboardFocus, None)
        pats, state = [], {}
        for pn in PATTERN_NAMES:
            pid = getattr(auto.PatternId, pn + "Pattern", None)
            p = _safe(lambda: c.GetPattern(pid)) if pid else None
            if not p:
                continue
            pats.append(pn)
            if pn == "Toggle":
                state["toggle"] = _safe(lambda: p.ToggleState)
            elif pn == "SelectionItem":
                state["selected"] = _safe(lambda: p.IsSelected)
            elif pn == "ExpandCollapse":
                state["expanded"] = _safe(lambda: p.ExpandCollapseState)
            elif pn == "Value":
                state["value"] = _safe(lambda: p.Value)
            elif pn == "RangeValue":
                state["range"] = [_safe(lambda: p.Value), _safe(lambda: p.Minimum), _safe(lambda: p.Maximum)]
            elif pn == "LegacyIAccessible":
                la = _safe(lambda: p.DefaultAction, "")
                if la:
                    state["default_action"] = la
                desc = _safe(lambda: p.Description, "")
                if desc:
                    state["description"] = desc
        d["patterns"] = pats
        if state:
            d["state"] = state
    return d


def roots_for(auto, args) -> list:
    root = getattr(args, "root", "all") or "all"
    if root == "desktop":
        return [auto.GetRootControl()]
    if root == "focused":
        return [auto.GetFocusedControl()]
    if root.startswith("point:"):
        x, y = (int(v) for v in root.split(":", 1)[1].split(","))
        return [auto.ControlFromPoint(x, y)]
    if root == "window":
        return [auto.ControlFromHandle(main_window(getattr(args, "title", None))["hwnd"])]
    wins = capcut_windows()
    if not wins:
        die("No visible CapCut window.")
    # Owned windows (menus, dialogs) already appear inside their owner's UIA subtree; walking them
    # as separate roots would list every element twice.
    user32.GetWindow.restype = wt.HWND
    handles = {w["hwnd"] for w in wins}
    top = [w for w in wins if (user32.GetWindow(wt.HWND(w["hwnd"]), 4) or 0) not in handles]  # GW_OWNER
    return [auto.ControlFromHandle(w["hwnd"]) for w in (top or wins)]


def walk(auto, roots, max_depth: int, max_nodes: int, patterns: bool, within: str | None = None):
    nodes, stack_roots = [], []
    for r in roots:
        if within:
            hit = _find_first_by_name(auto, r, within, max_depth)
            if hit is not None:
                stack_roots.append(hit)
        else:
            stack_roots.append(r)
    if within and not stack_roots:
        die(f"--within '{within}' not found")

    def rec(c, depth):
        if len(nodes) >= max_nodes:
            return
        nodes.append(node_info(auto, c, depth, len(nodes), patterns))
        if depth >= max_depth:
            return
        child = _safe(lambda: c.GetFirstChildControl())
        while child is not None and len(nodes) < max_nodes:
            rec(child, depth + 1)
            child = _safe(lambda: child.GetNextSiblingControl())

    for r in stack_roots:
        rec(r, 0)
    return nodes


def _find_first_by_name(auto, root, text: str, max_depth: int):
    t = text.lower()
    queue = [(root, 0)]
    while queue:
        c, d = queue.pop(0)
        if t in (_safe(lambda: c.Name, "") or "").lower():
            return c
        if d < max_depth:
            ch = _safe(lambda: c.GetFirstChildControl())
            while ch is not None:
                queue.append((ch, d + 1))
                ch = _safe(lambda: ch.GetNextSiblingControl())
    return None


def is_interactive(n: dict) -> bool:
    return n["type"] in INTERACTIVE_TYPES or bool(n.get("patterns") and set(n["patterns"]) - {"LegacyIAccessible", "Scroll"})


def fmt_node(n: dict) -> str:
    bits = [f"[{n['i']}]", "  " * n["depth"] + n["type"].replace("Control", "")]
    if n["name"]:
        bits.append(json.dumps(n["name"], ensure_ascii=False))
    if n.get("id"):
        bits.append(f"id={n['id']}")
    if n.get("cls"):
        bits.append(f"cls={n['cls'][:40]}")
    if n.get("rect"):
        bits.append("@(%d,%d,%d,%d)" % tuple(n["rect"]))
    if n.get("help"):
        bits.append(f"help={json.dumps(n['help'], ensure_ascii=False)}")
    if n.get("patterns"):
        bits.append("{" + ",".join(p for p in n["patterns"] if p != "LegacyIAccessible") + "}")
    if n.get("state"):
        bits.append(json.dumps(n["state"], ensure_ascii=False))
    if n.get("enabled") is False:
        bits.append("DISABLED")
    if n.get("offscreen"):
        bits.append("offscreen")
    return " ".join(bits)


def save_nodes(nodes: list, source: str):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_NODES.write_text(json.dumps(dict(time=time.time(), source=source, nodes=nodes), ensure_ascii=False), encoding="utf-8")


def matches(n: dict, a) -> bool:
    if a.type and n["type"].lower().replace("control", "") != a.type.lower().replace("control", ""):
        return False
    if a.name is not None and n["name"].lower() != a.name.lower():
        return False
    # CapCut puts live status text in AutomationId (e.g. id="Generating captions... 42%", Name="CapCut")
    if a.contains and a.contains.lower() not in (n["name"] + " " + n.get("help", "") + " " + (n.get("id") or "")).lower():
        return False
    if a.regex and not re.search(a.regex, n["name"], re.I):
        return False
    if a.id and n.get("id") != a.id:
        return False
    if a.cls and a.cls.lower() not in (n.get("cls") or "").lower():
        return False
    return True


def has_query(a) -> bool:
    return any([a.type, a.name is not None, a.contains, a.regex, a.id, a.cls])


# ----------------------------------------------------------------------------- screenshot

def grab(region: list[int]):
    import mss
    from PIL import Image
    with (getattr(mss, "MSS", None) or mss.mss)() as sct:
        vs = sct.monitors[0]
        l = max(region[0], vs["left"]); t = max(region[1], vs["top"])
        r = min(region[2], vs["left"] + vs["width"]); b = min(region[3], vs["top"] + vs["height"])
        if r <= l or b <= t:
            die(f"Region {region} is off-screen")
        s = sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
        return Image.frombytes("RGB", s.size, s.bgra, "raw", "BGRX"), [l, t, r, b]


def draw_grid(img, origin, step: int, scale: float):
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", max(11, int(13 * max(scale, 0.6))))
    except Exception:
        font = ImageFont.load_default()
    ox, oy = origin
    w, h = img.size
    first_x = math.ceil(ox / step) * step
    for sx in range(first_x, ox + int(w / scale) + 1, step):
        px = round((sx - ox) * scale)
        major = sx % (step * 5) == 0
        d.line([(px, 0), (px, h)], fill=(255, 0, 255) if major else (0, 255, 255), width=1)
        d.text((px + 2, 2), str(sx), fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    first_y = math.ceil(oy / step) * step
    for sy in range(first_y, oy + int(h / scale) + 1, step):
        py = round((sy - oy) * scale)
        major = sy % (step * 5) == 0
        d.line([(0, py), (w, py)], fill=(255, 0, 255) if major else (0, 255, 255), width=1)
        d.text((2, py + 2), str(sy), fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))


def take_screenshot(region=None, window=True, grid=False, step=100, scale=1.0, out_path=None, title=None):
    from PIL import Image
    # Screenshots grab a screen rectangle, not the window's own pixels: if another app is on
    # top (the agent's own desktop app often re-raises itself) we would capture that instead.
    w = main_window(title)
    if user32.GetForegroundWindow() not in {c["hwnd"] for c in capcut_windows()}:
        focus_window(w)
    foreground_ok = user32.GetForegroundWindow() in {c["hwnd"] for c in capcut_windows()}
    if not foreground_ok:
        print("WARN: CapCut is not the foreground window; the screenshot may show another app.", file=sys.stderr)
    if region is None:
        if window:
            region = w["rect"]
        else:
            import mss
            with (getattr(mss, "MSS", None) or mss.mss)() as sct:
                vs = sct.monitors[0]
                region = [vs["left"], vs["top"], vs["left"] + vs["width"], vs["top"] + vs["height"]]
    img, real = grab(region)
    if scale != 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    if grid:
        draw_grid(img, (real[0], real[1]), step, scale)
    if out_path is None:
        d = EVIDENCE_DIR / "shots" / dt.date.today().isoformat()
        d.mkdir(parents=True, exist_ok=True)
        out_path = d / (dt.datetime.now().strftime("%H%M%S_%f")[:-3] + (".grid" if grid else "") + ".png")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return dict(path=str(out_path), foreground_ok=foreground_ok, screen_region=real, image_size=list(img.size), scale=scale,
                mapping="screen_x = region.left + image_x/scale ; screen_y = region.top + image_y/scale"
                        + (" (grid labels already show screen coords)" if grid else ""))


# ----------------------------------------------------------------------------- commands

def cmd_version(a):
    info = dict(install_dir=None, versions=[], latest=None, running=[])
    for hive, sub in [(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")]:
        try:
            with winreg.OpenKey(hive, sub) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as e:
                            if "capcut" not in str(winreg.QueryValueEx(e, "DisplayName")[0]).lower():
                                continue
                            info["registry_version"] = _safe(lambda: winreg.QueryValueEx(e, "DisplayVersion")[0])
                            un = _safe(lambda: winreg.QueryValueEx(e, "UninstallString")[0], "")
                            if un:
                                info["install_dir"] = str(Path(un.strip('"')).parent)
                    except OSError:
                        continue
        except OSError:
            continue
    if info["install_dir"]:
        apps = Path(info["install_dir"])
        vers = sorted([p.name for p in apps.iterdir() if p.is_dir() and re.match(r"^\d+(\.\d+)+$", p.name)],
                      key=lambda s: [int(x) for x in s.split(".")])
        info["versions"] = vers
        info["latest"] = vers[-1] if vers else None
        info["launcher"] = str(apps / "CapCut.exe")
    for w in capcut_windows():
        m = re.search(r"\\(\d+(?:\.\d+)+)\\", w["exe"])
        v = m.group(1) if m else w["exe"]
        if v not in info["running"]:
            info["running"].append(v)
    out(info)


def cmd_launch(a):
    if capcut_windows():
        out("CapCut is already running.")
        return
    un = None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall") as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    with winreg.OpenKey(k, winreg.EnumKey(k, i)) as e:
                        if "capcut" in str(_safe(lambda: winreg.QueryValueEx(e, "DisplayName")[0], "")).lower():
                            un = winreg.QueryValueEx(e, "UninstallString")[0]
        except OSError:
            pass
    if not un:
        die("CapCut install not found in registry.")
    exe = Path(un.strip('"')).parent / "CapCut.exe"
    subprocess.Popen([str(exe)], close_fds=True)
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        if capcut_windows():
            out(dict(launched=str(exe), windows=len(capcut_windows())))
            return
        time.sleep(1)
    die("CapCut did not show a window before the timeout.")


def cmd_windows(a):
    out(capcut_windows())


def cmd_focus(a):
    w = main_window(a.title)
    ok = focus_window(w, a.maximize)
    w = main_window(a.title)
    out(dict(foreground=ok, title=w["title"], rect=w["rect"], maximized=w["maximized"], scale=w["scale"]))


def cmd_tree(a):
    auto = uia()
    roots = roots_for(auto, a)
    patterns = a.patterns or a.filter == "interactive"
    nodes = walk(auto, roots, a.depth, a.max_nodes, patterns, a.within)
    if len(nodes) < 8 and (a.root in (None, "all", "window")):
        # Qt turns accessibility on lazily when a client first asks; retry once.
        time.sleep(1.2)
        nodes = walk(auto, roots_for(auto, a), a.depth, a.max_nodes, patterns, a.within)
    save_nodes(nodes, "tree")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(nodes, ensure_ascii=False, indent=1), encoding="utf-8")
    shown = [n for n in nodes if (a.filter != "interactive" or is_interactive(n))
             and (a.filter != "named" or n["name"] or n.get("help"))]
    for n in shown:
        print(fmt_node(n))
    named = sum(1 for n in nodes if n["name"])
    print(f"-- {len(nodes)} nodes walked, {named} named, {len(shown)} shown"
          + (" (max-nodes reached)" if len(nodes) >= a.max_nodes else "")
          + (f"; saved {a.json}" if a.json else ""))


def _find_nodes(auto, a):
    nodes = walk(auto, roots_for(auto, a), a.depth, a.max_nodes, True, getattr(a, "within", None))
    return [n for n in nodes if matches(n, a)]


def cmd_find(a):
    if not has_query(a):
        die("find needs at least one of --name/--contains/--regex/--type/--id/--cls")
    auto = uia()
    hits = _find_nodes(auto, a)
    if not hits:
        time.sleep(1.0)
        hits = _find_nodes(auto, a)
    for k, n in enumerate(hits):
        n["i"] = k
        n["depth"] = 0
    save_nodes(hits, "find")
    for n in hits:
        print(fmt_node(n))
    print(f"-- {len(hits)} match(es); indices refer to this result list")


def _relocate(auto, a, stored: dict):
    """Find the live element that best matches a stored node (same type/name/id, nearest rect)."""
    nodes_and_ctrls = []

    def rec(c, depth):
        if depth > a.depth:
            return
        n = node_info(auto, c, depth, 0, False)
        if n["type"] == stored["type"] and n["name"] == stored["name"] and n["id"] == stored.get("id", ""):
            nodes_and_ctrls.append((n, c))
        ch = _safe(lambda: c.GetFirstChildControl())
        while ch is not None:
            rec(ch, depth + 1)
            ch = _safe(lambda: ch.GetNextSiblingControl())

    for r in roots_for(auto, a):
        rec(r, 0)
    if not nodes_and_ctrls:
        return None, None
    sx, sy = _center(stored["rect"]) if stored.get("rect") else (0, 0)
    nodes_and_ctrls.sort(key=lambda nc: (_center(nc[0]["rect"])[0] - sx) ** 2 + (_center(nc[0]["rect"])[1] - sy) ** 2
                         if nc[0]["rect"] else 1e18)
    return nodes_and_ctrls[0]


def _center(rect):
    return ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)


def _control_for_query(auto, a):
    hits = []

    def rec(c, depth):
        if depth > a.depth:
            return
        n = node_info(auto, c, depth, 0, bool(a.contains))
        if matches(n, a):
            hits.append((n, c))
        ch = _safe(lambda: c.GetFirstChildControl())
        while ch is not None:
            rec(ch, depth + 1)
            ch = _safe(lambda: ch.GetNextSiblingControl())

    roots = roots_for(auto, a)
    if a.within:
        roots = [r2 for r2 in (_find_first_by_name(auto, r, a.within, a.depth) for r in roots) if r2 is not None]
        if not roots:
            die(f"--within '{a.within}' not found")
    for r in roots:
        rec(r, 0)
    return hits


def cmd_act(a):
    auto = uia()
    if a.index is not None:
        if not LAST_NODES.exists():
            die("No saved nodes; run tree or find first.")
        saved = json.loads(LAST_NODES.read_text(encoding="utf-8"))
        try:
            stored = saved["nodes"][a.index]
        except IndexError:
            die(f"Index {a.index} not in last {saved['source']} result ({len(saved['nodes'])} nodes)")
        node, ctrl = _relocate(auto, a, stored)
        if ctrl is None:
            if a.action in ("click", "double", "right", "hover") and stored.get("rect"):
                print("WARN: element not re-found live; using its stored rect (may be stale).", file=sys.stderr)
                node = stored
            else:
                die(f"Element [{a.index}] {stored['type']} '{stored['name']}' no longer present. Re-read the tree.")
    else:
        if not has_query(a):
            die("act needs --index N or a query (--name/--contains/--regex/--type/--id/--cls)")
        hits = _control_for_query(auto, a)
        if not hits:
            die("No element matches the query.")
        if len(hits) > 1 and a.nth is None:
            for k, (n, _) in enumerate(hits[:30]):
                n["i"] = k
                n["depth"] = 0
                print(fmt_node(n))
            die(f"{len(hits)} elements match; tighten the query or pass --nth K.", 2)
        node, ctrl = hits[a.nth or 0]

    label = f"{node['type']} {json.dumps(node['name'], ensure_ascii=False)}"
    rect = node.get("rect")

    def pattern(name):
        pid = getattr(auto.PatternId, name + "Pattern")
        return _safe(lambda: ctrl.GetPattern(pid)) if ctrl is not None else None

    def mouse(kind):
        if not rect or rect[2] <= rect[0]:
            die(f"{label} has no usable rectangle (offscreen/virtualized). Scroll it into view first.")
        ensure_focus(a)
        x, y = _center(rect)
        if kind == "hover":
            move_to(x, y)
        else:
            click_at(x, y, "right" if kind == "right" else "left", 2 if kind == "double" else 1)
        return f"{kind} at ({x},{y})"

    act = a.action
    if act == "invoke":
        p = pattern("Invoke")
        if p:
            p.Invoke()
            result = "Invoke pattern"
        elif a.fallback_click:
            result = mouse("click") + " (no Invoke pattern)"
        else:
            die(f"{label} has no Invoke pattern; use 'act click' or pass --fallback-click")
    elif act in ("toggle",):
        p = pattern("Toggle")
        if not p:
            die(f"{label} has no Toggle pattern")
        p.Toggle()
        result = f"toggled -> {_safe(lambda: p.ToggleState)}"
    elif act == "select":
        p = pattern("SelectionItem")
        if not p:
            die(f"{label} has no SelectionItem pattern")
        p.Select()
        result = "selected"
    elif act in ("expand", "collapse"):
        p = pattern("ExpandCollapse")
        if not p:
            die(f"{label} has no ExpandCollapse pattern")
        (p.Expand if act == "expand" else p.Collapse)()
        result = act + "ed"
    elif act == "set-value":
        if a.value is None:
            die("set-value needs --value")
        p = pattern("Value")
        if p:
            p.SetValue(a.value)
            result = f"Value set to: {a.value}"
        else:
            ensure_focus(a)
            mouse("click")
            press_combo("ctrl+a")
            type_unicode(a.value)
            result = f"typed {a.value!r} (no Value pattern)"
    elif act == "focus":
        _safe(lambda: ctrl.SetFocus())
        result = "focus requested"
    elif act in ("click", "double", "right", "hover"):
        result = mouse(act)
    else:
        die(f"unknown action {act}")
    time.sleep(a.settle)
    out(dict(element=label, id=node.get("id"), rect=rect, result=result))


def cmd_screenshot(a):
    region = [int(v) for v in a.region.split(",")] if a.region else None
    out(take_screenshot(region, window=not a.full, grid=a.grid, step=a.step, scale=a.scale,
                        out_path=a.out, title=a.title))


def cmd_click(a):
    ensure_focus(a)
    mods = a.mod.split("+") if a.mod else None
    button = "right" if a.right else "left"
    click_at(a.x, a.y, button, 2 if a.double else 1, mods)
    time.sleep(a.settle)
    out(dict(clicked=[a.x, a.y], button=button, double=a.double, modifiers=mods))


def cmd_hover(a):
    move_to(a.x, a.y)
    out(dict(hover=[a.x, a.y]))


def cmd_drag(a):
    ensure_focus(a)
    drag(a.x1, a.y1, a.x2, a.y2, a.steps, a.hold)
    time.sleep(a.settle)
    out(dict(dragged=[a.x1, a.y1, a.x2, a.y2], steps=a.steps))


def cmd_scroll(a):
    ensure_focus(a)
    scroll_at(a.x, a.y, a.clicks, a.horizontal, a.mod.split("+") if a.mod else None)
    out(dict(scrolled=a.clicks, at=[a.x, a.y], horizontal=a.horizontal, modifiers=a.mod))


def cmd_key(a):
    ensure_focus(a)
    for combo in a.combos:
        for _ in range(a.repeat):
            press_combo(combo)
            time.sleep(a.gap)
    time.sleep(a.settle)
    out(dict(keys=a.combos, repeat=a.repeat))


def cmd_type(a):
    ensure_focus(a)
    type_unicode(a.text)
    if a.enter:
        press_combo("enter")
    out(dict(typed=a.text, enter=a.enter))


def cmd_paste(a):
    ensure_focus(a)
    set_clipboard(a.text)
    press_combo("ctrl+v")
    if a.enter:
        press_combo("enter")
    out(dict(pasted=a.text, enter=a.enter))


def cmd_wait(a):
    time.sleep(a.ms / 1000)
    out(dict(waited_ms=a.ms))


def cmd_wait_for(a):
    if not has_query(a):
        die("wait-for needs a query")
    auto = uia()
    t0 = time.time()
    while True:
        hits = _find_nodes(auto, a)
        present = bool(hits)
        if present != a.gone:
            out(dict(condition="gone" if a.gone else "present", seconds=round(time.time() - t0, 1),
                     match=None if a.gone else fmt_node(hits[0])))
            return
        if time.time() - t0 > a.timeout:
            die(f"timeout after {a.timeout}s waiting for element to be {'gone' if a.gone else 'present'}", 3)
        time.sleep(a.interval)


def cmd_evidence(a):
    stamp = dt.datetime.now()
    d = EVIDENCE_DIR / stamp.date().isoformat() / (stamp.strftime("%H%M%S") + "-" + re.sub(r"[^\w.-]+", "_", a.label))
    d.mkdir(parents=True, exist_ok=True)
    meta = dict(label=a.label, time=stamp.isoformat(timespec="seconds"), windows=capcut_windows())
    if meta["windows"]:
        meta["screenshot"] = take_screenshot(out_path=d / "window.png")
        meta["screenshot_grid"] = take_screenshot(grid=True, scale=a.scale, out_path=d / "window.grid.png")
        auto = uia()
        a.root = "all"
        nodes = walk(auto, roots_for(auto, a), a.depth, a.max_nodes, True)
        (d / "tree.json").write_text(json.dumps(nodes, ensure_ascii=False, indent=1), encoding="utf-8")
        meta["tree_nodes"] = len(nodes)
    if a.project:
        inspector = Path(__file__).with_name("draft_inspect.py")
        r = subprocess.run([sys.executable, str(inspector), "summary", a.project, "--json", str(d / "draft_summary.json"),
                            "--copy-json-to", str(d)], capture_output=True, text=True, encoding="utf-8")
        meta["draft"] = dict(returncode=r.returncode, stderr=r.stderr.strip()[-500:], summary=str(d / "draft_summary.json"))
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    out(dict(evidence_dir=str(d), tree_nodes=meta.get("tree_nodes"), draft=meta.get("draft")))


# ----------------------------------------------------------------------------- CLI

def add_query(p, with_depth=True):
    p.add_argument("--name", help="exact Name (case-insensitive)")
    p.add_argument("--contains", help="substring of Name, HelpText or AutomationId (CapCut puts status like 'Generating captions... 42%%' in the id)")
    p.add_argument("--regex", help="regex on Name")
    p.add_argument("--type", help="ControlType, e.g. Button, Edit, TabItem")
    p.add_argument("--id", help="exact AutomationId")
    p.add_argument("--cls", help="substring of ClassName")
    p.add_argument("--within", help="only search under the first element whose Name contains this")
    add_root(p)


def add_root(p):
    p.add_argument("--root", default="all", help="all (every CapCut window, default) | window | focused | desktop | point:x,y")
    p.add_argument("--title", help="pick CapCut window whose title contains this")
    p.add_argument("--depth", type=int, default=40)
    p.add_argument("--max-nodes", type=int, default=6000)


def add_input_common(p):
    p.add_argument("--no-focus", action="store_true", help="don't bring CapCut to the foreground first")
    p.add_argument("--settle", type=float, default=0.25, help="seconds to wait after the action")


def build_parser():
    ap = argparse.ArgumentParser(prog="cc.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("version", help="install dir, installed versions, running version").set_defaults(fn=cmd_version)
    p = sp.add_parser("launch", help="start CapCut if not running")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(fn=cmd_launch)
    sp.add_parser("windows", help="list visible CapCut top-level windows").set_defaults(fn=cmd_windows)
    p = sp.add_parser("focus", help="bring main CapCut window to foreground")
    p.add_argument("--maximize", action="store_true")
    p.add_argument("--title")
    p.set_defaults(fn=cmd_focus)

    p = sp.add_parser("tree", help="dump the UI Automation tree")
    add_root(p)
    p.add_argument("--within", help="start at the first element whose Name contains this")
    p.add_argument("--filter", choices=["all", "interactive", "named"], default="all")
    p.add_argument("--patterns", action="store_true", help="include patterns/state/HelpText (slower)")
    p.add_argument("--json", help="also write full node list to this file")
    p.set_defaults(fn=cmd_tree)

    p = sp.add_parser("find", help="search the tree; prints indices usable with act --index")
    add_query(p)
    p.set_defaults(fn=cmd_find)

    p = sp.add_parser("act", help="act on an element by query or by index from last tree/find")
    p.add_argument("action", choices=["invoke", "toggle", "select", "expand", "collapse", "set-value", "focus",
                                      "click", "double", "right", "hover"])
    p.add_argument("--index", type=int)
    p.add_argument("--nth", type=int)
    p.add_argument("--value")
    p.add_argument("--fallback-click", action="store_true")
    add_query(p)
    add_input_common(p)
    p.set_defaults(fn=cmd_act)

    p = sp.add_parser("screenshot", help="PNG of the CapCut window (default), a region, or all screens")
    p.add_argument("--region", help="l,t,r,b in screen pixels")
    p.add_argument("--full", action="store_true", help="whole virtual screen")
    p.add_argument("--grid", action="store_true", help="overlay grid labelled in SCREEN coordinates")
    p.add_argument("--step", type=int, default=100, help="grid spacing in screen px")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--out")
    p.add_argument("--title")
    p.set_defaults(fn=cmd_screenshot)

    p = sp.add_parser("click", help="click at screen coordinates")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--double", action="store_true")
    p.add_argument("--right", action="store_true")
    p.add_argument("--mod", help="modifiers held during click, e.g. ctrl or shift+ctrl")
    add_input_common(p)
    p.set_defaults(fn=cmd_click)

    p = sp.add_parser("hover", help="move the mouse without clicking (tooltips)")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.set_defaults(fn=cmd_hover)

    p = sp.add_parser("drag", help="press-move-release")
    for n in ("x1", "y1", "x2", "y2"):
        p.add_argument(n, type=int)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--hold", type=float, default=0.15)
    add_input_common(p)
    p.set_defaults(fn=cmd_drag)

    p = sp.add_parser("scroll", help="mouse wheel at a point (clicks: +up / -down)")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("clicks", type=int)
    p.add_argument("--horizontal", action="store_true")
    p.add_argument("--mod", help="e.g. ctrl (timeline zoom) or alt")
    add_input_common(p)
    p.set_defaults(fn=cmd_scroll)

    p = sp.add_parser("key", help="key combos, e.g. ctrl+b  or  left left left")
    p.add_argument("combos", nargs="+")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--gap", type=float, default=0.06)
    add_input_common(p)
    p.set_defaults(fn=cmd_key)

    p = sp.add_parser("type", help="type Unicode text into the focused control")
    p.add_argument("text")
    p.add_argument("--enter", action="store_true")
    add_input_common(p)
    p.set_defaults(fn=cmd_type)

    p = sp.add_parser("paste", help="put text on the clipboard and Ctrl+V it")
    p.add_argument("text")
    p.add_argument("--enter", action="store_true")
    add_input_common(p)
    p.set_defaults(fn=cmd_paste)

    p = sp.add_parser("wait", help="sleep")
    p.add_argument("--ms", type=int, default=500)
    p.set_defaults(fn=cmd_wait)

    p = sp.add_parser("wait-for", help="poll until an element appears (or --gone)")
    add_query(p)
    p.add_argument("--gone", action="store_true")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--interval", type=float, default=1.0)
    p.set_defaults(fn=cmd_wait_for)

    p = sp.add_parser("evidence", help="save screenshot + grid + tree (+ draft summary) under evidence/")
    p.add_argument("label")
    p.add_argument("--project", help="CapCut project name or folder for draft summary")
    p.add_argument("--scale", type=float, default=0.6)
    p.add_argument("--title")
    p.add_argument("--depth", type=int, default=40)
    p.add_argument("--max-nodes", type=int, default=6000)
    p.set_defaults(fn=cmd_evidence)
    return ap


def main():
    a = build_parser().parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
