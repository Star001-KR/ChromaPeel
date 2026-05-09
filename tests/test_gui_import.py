"""Smoke test for the chromapeel_gui package entry point.

Guards against the regression where run.bat / run.sh pointed at a stale
chromapeel_gui.py path while the code lived in the chromapeel_gui/ package,
causing pythonw.exe to fail silently on Windows.
"""
from pathlib import Path

import chromapeel_gui


def test_chromapeel_gui_main_is_callable():
    assert callable(chromapeel_gui.main)


def test_chromapeel_gui_dunder_main_importable():
    import importlib

    module = importlib.import_module("chromapeel_gui.__main__")
    assert callable(module.main)


def test_cleanup_clip_tempdir_removes_directory(tmp_path):
    """dialog destroy 시 paste tempdir 이 통째로 정리된다 — 회귀 방지.

    이전 구현은 paste 한 PNG 를 ``base/`` 에 누수시켰고 cleanup 이 없었다. 지금은
    각 dialog 가 ``tempfile.mkdtemp`` 로 격리 dir 을 만들고 destroy 시 이 헬퍼로
    통째 삭제한다.
    """
    from chromapeel_gui.dialogs import _cleanup_clip_tempdir

    target = tmp_path / "stage"
    target.mkdir()
    (target / "clipboard_a.png").write_bytes(b"fake")
    (target / "clipboard_b.png").write_bytes(b"fake")

    _cleanup_clip_tempdir(target)

    assert not target.exists()


def test_cleanup_clip_tempdir_handles_none():
    """paste 한 적이 없는 dialog (tempdir is None) 도 안전하게 호출 가능."""
    from chromapeel_gui.dialogs import _cleanup_clip_tempdir

    _cleanup_clip_tempdir(None)  # no exception


def test_cleanup_clip_tempdir_swallows_missing_dir(tmp_path):
    """이미 삭제된 dir 에 대한 cleanup 도 예외 없이 통과 (ignore_errors)."""
    from chromapeel_gui.dialogs import _cleanup_clip_tempdir

    _cleanup_clip_tempdir(tmp_path / "never_existed")
