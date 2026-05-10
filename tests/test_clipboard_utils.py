"""Unit tests for clipboard_utils — dispatch + per-platform invocation safety.

The actual OS clipboard is never touched: subprocess.run / shutil.which / sys
are monkeypatched so these tests are platform-agnostic.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import clipboard_utils
from clipboard_utils import (
    ClipboardImageError,
    copy_image_to_clipboard,
    read_image_from_clipboard,
    stage_clipboard_image,
    stage_clipboard_image_or_exit,
)


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


# ---------- read_image_from_clipboard ----------

def _patch_grabclipboard(monkeypatch, value):
    monkeypatch.setattr(
        clipboard_utils.ImageGrab, "grabclipboard", lambda: value
    )


def test_read_image_returns_pil_image_when_clipboard_has_image(monkeypatch):
    fake = Image.new("RGB", (4, 4), (10, 20, 30))
    _patch_grabclipboard(monkeypatch, fake)

    result = read_image_from_clipboard()

    assert isinstance(result, Image.Image)
    assert result.size == (4, 4)


def test_read_image_returns_none_when_clipboard_empty(monkeypatch):
    _patch_grabclipboard(monkeypatch, None)
    assert read_image_from_clipboard() is None


def test_read_image_returns_none_when_clipboard_has_text_or_unknown(monkeypatch):
    _patch_grabclipboard(monkeypatch, [])
    assert read_image_from_clipboard() is None

    _patch_grabclipboard(monkeypatch, ["/some/path/document.txt"])
    assert read_image_from_clipboard() is None


def test_read_image_loads_first_image_when_clipboard_has_file_paths(monkeypatch, tmp_path):
    png_path = tmp_path / "clip.png"
    Image.new("RGB", (5, 7), (200, 100, 50)).save(png_path)
    _patch_grabclipboard(monkeypatch, [str(png_path)])

    result = read_image_from_clipboard()

    assert isinstance(result, Image.Image)
    assert result.size == (5, 7)


def test_read_image_returns_none_when_clipboard_returns_unsupported_type(monkeypatch):
    _patch_grabclipboard(monkeypatch, 42)
    assert read_image_from_clipboard() is None


# ---------- stage_clipboard_image ----------

def test_stage_writes_timestamped_png(monkeypatch, tmp_path):
    """기본 동작: clipboard PIL 이미지를 staging_dir 에 PNG로 저장."""
    _patch_grabclipboard(
        monkeypatch, Image.new("RGB", (3, 4), (10, 20, 30)),
    )
    out = stage_clipboard_image(tmp_path / "stage")

    assert out.is_file()
    assert out.parent == tmp_path / "stage"
    assert out.name.startswith("clipboard_")
    assert out.suffix == ".png"
    img = Image.open(out)
    assert img.size == (3, 4)


def test_stage_uses_microseconds_to_avoid_collision(monkeypatch, tmp_path):
    """동일 초에 두 번 호출되어도 파일명 충돌이 없어야 한다 (마이크로초 포함).

    회귀 방지: 이전에 grid_split/manual_crop/imageAlpha 가 각각 ``%Y%m%d_%H%M%S``
    (초 단위) 만 사용하여 같은 초에 두 번 호출 시 덮어쓰기 위험이 있었다.
    """
    monkeypatch.setattr(
        clipboard_utils.ImageGrab, "grabclipboard",
        lambda: Image.new("RGB", (2, 2), (255, 0, 0)),
    )
    out1 = stage_clipboard_image(tmp_path)
    out2 = stage_clipboard_image(tmp_path)

    assert out1 != out2
    assert out1.exists() and out2.exists()


def test_stage_raises_clipboard_image_error_when_empty(monkeypatch, tmp_path):
    _patch_grabclipboard(monkeypatch, None)
    with pytest.raises(ClipboardImageError, match="이미지가 없습니다"):
        stage_clipboard_image(tmp_path)


def test_stage_wraps_pil_exception_as_clipboard_image_error(monkeypatch, tmp_path):
    """PIL.ImageGrab.grabclipboard() 가 예외를 던지는 시나리오 (Linux wl-paste 미설치 등).

    회귀 방지: CLI 가 ``--from-clipboard`` 를 처리할 때 traceback 을 그대로 노출
    하지 않고 사용자 친화 메시지로 변환해야 한다.
    """
    def _raise():
        raise OSError("wl-paste not installed")
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)

    with pytest.raises(ClipboardImageError, match="클립보드 읽기 실패"):
        stage_clipboard_image(tmp_path)


def test_stage_creates_missing_directory(monkeypatch, tmp_path):
    _patch_grabclipboard(monkeypatch, Image.new("RGB", (1, 1), (0, 0, 0)))
    target = tmp_path / "deep" / "nested" / "stage"
    assert not target.exists()

    out = stage_clipboard_image(target)

    assert target.is_dir()
    assert out.is_file()


def test_stage_avoids_collision_when_timestamp_is_identical(monkeypatch, tmp_path):
    """동일 마이크로초 timestamp 가 강제돼도 두 파일이 충돌 없이 생성된다.

    회귀 방지: 이전 구현은 ``%Y%m%d_%H%M%S_%f`` 단독 의존 — 동일 마이크로초 두
    호출 시 덮어쓰기 위험이 있었다. uuid suffix + ``exists()`` retry 로 보강했고
    여기서는 monkeypatch 로 timestamp 를 고정해 그 보강을 강제 검증한다.
    """
    _patch_grabclipboard(monkeypatch, Image.new("RGB", (2, 2), (0, 255, 0)))
    monkeypatch.setattr(
        clipboard_utils, "_now_timestamp", lambda: "20260509_030918_123456",
    )

    out1 = stage_clipboard_image(tmp_path)
    out2 = stage_clipboard_image(tmp_path)

    assert out1 != out2
    assert out1.exists() and out2.exists()
    # 두 파일 모두 같은 timestamp prefix 를 갖되 uuid suffix 가 다르다.
    assert out1.name.startswith("clipboard_20260509_030918_123456_")
    assert out2.name.startswith("clipboard_20260509_030918_123456_")


def test_stage_wraps_save_failure_as_clipboard_image_error(monkeypatch, tmp_path):
    """img.save 가 OSError 를 던지면 ClipboardImageError 로 래핑된다.

    회귀 방지: 이전 구현은 mkdir/save 를 try 블록 밖에 두어 디스크 풀, 권한 부족
    등에서 CLI 가 traceback 을 그대로 노출했다. 지금은 save 실패도 사용자 친화
    메시지로 변환된다.
    """
    fake_image = Image.new("RGB", (1, 1), (255, 255, 255))

    def _failing_save(self, *args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(Image.Image, "save", _failing_save)
    _patch_grabclipboard(monkeypatch, fake_image)

    with pytest.raises(ClipboardImageError, match="이미지 저장 실패"):
        stage_clipboard_image(tmp_path)


def test_stage_wraps_mkdir_failure_as_clipboard_image_error(monkeypatch, tmp_path):
    """mkdir 권한 부족 등 OSError 도 ClipboardImageError 로 래핑된다."""
    _patch_grabclipboard(monkeypatch, Image.new("RGB", (1, 1)))

    def _failing_mkdir(self, *args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "mkdir", _failing_mkdir)

    with pytest.raises(ClipboardImageError, match="스테이징 폴더 생성 실패"):
        stage_clipboard_image(tmp_path / "blocked")


# ---------- stage_clipboard_image_or_exit (CLI wrapper) ----------

def test_stage_or_exit_returns_path_on_success(monkeypatch, tmp_path):
    """성공 경로는 underlying ``stage_clipboard_image`` 와 동일하게 Path 반환."""
    _patch_grabclipboard(monkeypatch, Image.new("RGB", (2, 2), (10, 20, 30)))

    out = stage_clipboard_image_or_exit(tmp_path / "stage")

    assert out.is_file()
    assert out.parent == tmp_path / "stage"
    assert out.suffix == ".png"


def test_stage_or_exit_prints_message_and_exits_on_empty_clipboard(
    monkeypatch, tmp_path, capsys,
):
    """ClipboardImageError 는 traceback 없이 stderr 메시지 + exit(1) 로 변환된다.

    회귀 방지: 3 CLI (`chromapeel-cli/-split/-crop`) 가 공유하던 _stage_clipboard_image
    중복 헬퍼를 단일화한 후에도 정책이 유지되는지 검증.
    """
    _patch_grabclipboard(monkeypatch, None)

    with pytest.raises(SystemExit) as ei:
        stage_clipboard_image_or_exit(tmp_path)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "이미지가 없습니다" in err
    assert "Traceback" not in err


def test_stage_or_exit_wraps_pil_exception(monkeypatch, tmp_path, capsys):
    """ImageGrab 자체 예외 (Linux wl-paste 미설치 등) 도 동일 정책."""
    def _raise():
        raise OSError("wl-paste not installed")
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)

    with pytest.raises(SystemExit) as ei:
        stage_clipboard_image_or_exit(tmp_path)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "클립보드 읽기 실패" in err
    assert "Traceback" not in err
