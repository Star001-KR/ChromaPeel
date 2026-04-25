from __future__ import annotations

import ctypes
import io
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


def copy_image_to_clipboard(path: Path) -> None:
    """Copy the image at ``path`` to the system clipboard.

    Windows uses ``CF_DIB`` (RGB on white) plus the registered ``"PNG"``
    format (alpha preserved). macOS uses ``osascript`` with ``«class PNGf»``.
    Linux uses ``wl-copy`` (Wayland) or ``xclip`` (X11) — at least one must
    be installed. Raises on failure.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)

    if sys.platform == "win32":
        _copy_windows(p)
    elif sys.platform == "darwin":
        _copy_macos(p)
    else:
        _copy_linux(p)


def _copy_windows(path: Path) -> None:
    from ctypes import wintypes

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


def _copy_macos(path: Path) -> None:
    posix = str(path.resolve()).replace('"', '\\"')
    script = f'set the clipboard to (read (POSIX file "{posix}") as «class PNGf»)'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise OSError(f"osascript 실패: {result.stderr.strip() or result.stdout.strip()}")


def _copy_linux(path: Path) -> None:
    abs_path = str(path.resolve())
    if shutil.which("wl-copy"):
        with open(abs_path, "rb") as f:
            result = subprocess.run(
                ["wl-copy", "--type", "image/png"],
                stdin=f, capture_output=True,
            )
        if result.returncode != 0:
            raise OSError(f"wl-copy 실패: {result.stderr.decode(errors='replace').strip()}")
        return
    if shutil.which("xclip"):
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", abs_path],
            capture_output=True,
        )
        if result.returncode != 0:
            raise OSError(f"xclip 실패: {result.stderr.decode(errors='replace').strip()}")
        return
    raise OSError("이미지 클립보드 복사를 위해 'wl-clipboard' 또는 'xclip' 패키지가 필요합니다")
