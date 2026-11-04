"""Read a selected rectangle from the Windows desktop."""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass

import numpy as np

user = c.WinDLL("user32", use_last_error=True)
gdi = c.WinDLL("gdi32", use_last_error=True)
dwm = c.WinDLL("dwmapi", use_last_error=True)

WDA_EXCLUDEFROMCAPTURE = 0x11
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
SWP_NOACTIVATE = 0x10
HWND_TOPMOST = -1
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000


def signature(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype = result
    fn.argtypes = args
    return fn


set_dpi = signature(user, "SetProcessDpiAwarenessContext", w.BOOL, w.HANDLE)
get_ancestor = signature(user, "GetAncestor", w.HWND, w.HWND, w.UINT)
get_dc = signature(user, "GetDC", w.HDC, w.HWND)
release_dc = signature(user, "ReleaseDC", c.c_int, w.HWND, w.HDC)
compatible_dc = signature(gdi, "CreateCompatibleDC", w.HDC, w.HDC)
delete_dc = signature(gdi, "DeleteDC", w.BOOL, w.HDC)
select_object = signature(gdi, "SelectObject", w.HANDLE, w.HDC, w.HANDLE)
delete_object = signature(gdi, "DeleteObject", w.BOOL, w.HANDLE)
bit_blt = signature(
    gdi, "BitBlt", w.BOOL, w.HDC, c.c_int, c.c_int, c.c_int, c.c_int,
    w.HDC, c.c_int, c.c_int, w.DWORD,
)
get_style = signature(user, "GetWindowLongW", w.LONG, w.HWND, c.c_int)
set_style = signature(user, "SetWindowLongW", w.LONG, w.HWND, c.c_int, w.LONG)
set_affinity = signature(
    user, "SetWindowDisplayAffinity", w.BOOL, w.HWND, w.DWORD
)
set_position = signature(
    user, "SetWindowPos", w.BOOL, w.HWND, w.HWND, c.c_int, c.c_int,
    c.c_int, c.c_int, w.UINT,
)
get_cursor = signature(user, "GetCursorPos", w.BOOL, c.POINTER(w.POINT))
get_metrics = signature(user, "GetSystemMetrics", c.c_int, c.c_int)
flush_compositor = signature(dwm, "DwmFlush", w.LONG)
flush_gdi = signature(gdi, "GdiFlush", w.BOOL)


class BitmapInfo(c.Structure):
    _fields_ = [
        ("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
        ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
        ("size_image", w.DWORD), ("xppm", w.LONG), ("yppm", w.LONG),
        ("colors", w.DWORD), ("important", w.DWORD), ("rgb", w.DWORD),
    ]


create_dib = signature(
    gdi, "CreateDIBSection", w.HANDLE, w.HDC, c.POINTER(BitmapInfo),
    w.UINT, c.POINTER(c.c_void_p), w.HANDLE, w.DWORD,
)


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int


def desktop() -> Region:
    # SM_XVIRTUALSCREEN through SM_CYVIRTUALSCREEN.
    return Region(*(get_metrics(index) for index in range(76, 80)))


def cursor() -> tuple[int, int]:
    point = w.POINT()
    if not get_cursor(c.byref(point)):
        raise c.WinError(c.get_last_error())
    return point.x, point.y


def hwnd(widget) -> int:
    widget.update_idletasks()
    return get_ancestor(widget.winfo_id(), GA_ROOT)


def place(handle: int, region: Region) -> None:
    if not set_position(
        handle, HWND_TOPMOST, region.x, region.y, region.width, region.height,
        SWP_NOACTIVATE,
    ):
        raise c.WinError(c.get_last_error())


def exclude_overlay(handle: int) -> bool:
    style = get_style(handle, GWL_EXSTYLE)
    set_style(
        handle, GWL_EXSTYLE,
        style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
    )
    return bool(set_affinity(handle, WDA_EXCLUDEFROMCAPTURE))


def capture(region: Region) -> np.ndarray:
    if region.width < 1 or region.height < 1:
        raise ValueError("Capture region must have a positive size.")
    source = get_dc(None)
    if not source:
        raise c.WinError(c.get_last_error())
    memory = bitmap = previous = None
    try:
        memory = compatible_dc(source)
        if not memory:
            raise c.WinError(c.get_last_error())
        info = BitmapInfo(40, region.width, -region.height, 1, 32)
        pixels = c.c_void_p()
        bitmap = create_dib(source, c.byref(info), 0, c.byref(pixels), None, 0)
        if not bitmap:
            raise c.WinError(c.get_last_error())
        previous = select_object(memory, bitmap)
        if not previous:
            raise c.WinError(c.get_last_error())
        if not bit_blt(
            memory, 0, 0, region.width, region.height, source,
            region.x, region.y, SRCCOPY | CAPTUREBLT,
        ):
            raise c.WinError(c.get_last_error())
        flush_gdi()
        bgra = c.string_at(pixels, region.width * region.height * 4)
        image = np.frombuffer(bgra, dtype=np.uint8).reshape(
            region.height, region.width, 4
        )[:, :, :3]
    finally:
        if previous:
            select_object(memory, previous)
        if bitmap:
            delete_object(bitmap)
        if memory:
            delete_dc(memory)
        release_dc(None, source)
    return image
