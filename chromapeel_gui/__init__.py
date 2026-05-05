from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path("base")
ALPHA_DIR = Path("alpha")


def _open_path(path: Path) -> None:
    """기본 연결 프로그램으로 파일 또는 폴더 열기 (크로스 플랫폼)."""
    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.run(["open", target], check=False)
    else:
        subprocess.run(["xdg-open", target], check=False)


def _reveal_path(path: Path) -> None:
    """파일 관리자에서 해당 파일을 선택해 열기. Linux는 부모 폴더를 엽니다."""
    target = str(path)
    if sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{target}"], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", target], check=False)
    else:
        subprocess.run(["xdg-open", str(Path(target).parent)], check=False)


from .app import main  # noqa: E402  pyproject.toml gui-scripts 진입점

__all__ = ["main", "BASE_DIR", "ALPHA_DIR", "_open_path", "_reveal_path"]
