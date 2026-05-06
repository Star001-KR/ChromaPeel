"""Smoke test for the chromapeel_gui package entry point.

Guards against the regression where run.bat / run.sh pointed at a stale
chromapeel_gui.py path while the code lived in the chromapeel_gui/ package,
causing pythonw.exe to fail silently on Windows.
"""
import chromapeel_gui


def test_chromapeel_gui_main_is_callable():
    assert callable(chromapeel_gui.main)


def test_chromapeel_gui_dunder_main_importable():
    import importlib

    module = importlib.import_module("chromapeel_gui.__main__")
    assert callable(module.main)
