"""Unit tests for clipboard_utils — dispatch + per-platform invocation safety.

The actual OS clipboard is never touched: subprocess.run / shutil.which / sys
are monkeypatched so these tests are platform-agnostic.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import clipboard_utils
from clipboard_utils import copy_image_to_clipboard


def _make_png(path: Path) -> Path:
    Image.new("RGB", (2, 2), (255, 0, 0)).save(path)
    return path


# ---------- top-level dispatch ----------

def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        copy_image_to_clipboard(tmp_path / "does_not_exist.png")


@pytest.mark.parametrize("platform,target", [
    ("win32", "_copy_windows"),
    ("darwin", "_copy_macos"),
    ("linux", "_copy_linux"),
    ("freebsd", "_copy_linux"),  # any non-win/non-mac falls through to linux path
])
def test_dispatches_per_platform(monkeypatch, tmp_path, platform, target):
    src = _make_png(tmp_path / "in.png")
    calls = []
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(clipboard_utils, target, lambda p: calls.append(p))
    copy_image_to_clipboard(src)
    assert calls == [src]


# ---------- macOS ----------

def test_macos_uses_safe_temp_symlink_not_user_path(monkeypatch, tmp_path):
    """B3 regression: paths with shell-meaningful chars must not leak into osascript."""
    # Use chars valid on all OS (Windows reserves " and \). The point is to confirm
    # the implementation never embeds the user's path into the AppleScript string,
    # regardless of what characters it contains.
    src = _make_png(tmp_path / "a' b.png")  # single quote + space

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_macos(src)

    cmd = captured["cmd"]
    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    script = cmd[2]
    # Script references the safe symlink basename
    assert "image.png" in script
    # Original user-controlled path (with metacharacters) must not appear
    assert str(src) not in script
    assert src.name not in script


def test_macos_raises_on_osascript_failure(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(OSError, match="osascript"):
        clipboard_utils._copy_macos(src)


# ---------- Linux ----------

def _which_factory(available: dict[str, str]):
    """Return a fake shutil.which that resolves only the listed tool names."""
    return lambda name: available.get(name)


def test_linux_prefers_wl_copy_when_available(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"wl-copy": "/usr/bin/wl-copy", "xclip": "/usr/bin/xclip"}))

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_linux(src)

    assert captured["cmd"][0] == "wl-copy"
    assert "image/png" in captured["cmd"]


def test_linux_falls_back_to_xclip_when_wl_copy_missing(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"xclip": "/usr/bin/xclip"}))

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_linux(src)

    assert captured["cmd"][0] == "xclip"
    assert "-selection" in captured["cmd"]
    assert "clipboard" in captured["cmd"]


def test_linux_raises_when_neither_tool_available(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which", _which_factory({}))
    with pytest.raises(OSError, match="wl-clipboard|xclip"):
        clipboard_utils._copy_linux(src)


def test_linux_wl_copy_failure_raises(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"wl-copy": "/usr/bin/wl-copy"}))
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"nope"),
    )
    with pytest.raises(OSError, match="wl-copy"):
        clipboard_utils._copy_linux(src)


def test_linux_xclip_failure_raises(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"xclip": "/usr/bin/xclip"}))
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"nope"),
    )
    with pytest.raises(OSError, match="xclip"):
        clipboard_utils._copy_linux(src)
