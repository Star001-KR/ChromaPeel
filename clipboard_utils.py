from __future__ import annotations

import ctypes
import io
from ctypes import wintypes
from pathlib import Path

from PIL import Image


def copy_image_to_clipboard(path: Path) -> None:
    """Copy image file at ``path`` to the Windows clipboard.

    Sets both ``CF_DIB`` (flattened RGB on white — best compatibility with
    Paint, Word, chat apps) and the registered ``"PNG"`` clipboard format
    (alpha preserved — for Photoshop/GIMP/etc.). Raises on failure.
    """
    img = Image.open(path)

    # CF_DIB (RGB with alpha composited on white for wide compatibility)
    flat = Image.new("RGB", img.size, (255, 255, 255))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat.paste(rgba, mask=rgba.split()[3])
    else:
        flat.paste(img.convert("RGB"))
    bmp_buf = io.BytesIO()
    flat.save(bmp_buf, "BMP")
    dib_data = bmp_buf.getvalue()[14:]  # strip 14-byte BMP file header

    # PNG (alpha preserved)
    png_buf = io.BytesIO()
    img.save(png_buf, "PNG")
    png_data = png_buf.getvalue()

    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    def _alloc_and_write(data: bytes) -> wintypes.HGLOBAL:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("GlobalAlloc 실패")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise OSError("GlobalLock 실패")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        return handle

    png_format = user32.RegisterClipboardFormatW("PNG")

    if not user32.OpenClipboard(None):
        raise OSError("클립보드를 열 수 없습니다")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_DIB, _alloc_and_write(dib_data))
        if png_format:
            user32.SetClipboardData(png_format, _alloc_and_write(png_data))
    finally:
        user32.CloseClipboard()
