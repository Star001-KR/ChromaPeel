"""클립보드 paste 트리거 + tempdir 격리 mixin.

GridSplit / ManualCrop 두 다이얼로그가 같은 paste 흐름을 공유한다 — Ctrl/Cmd+V
숏컷, 캔버스 우클릭 메뉴, "📋 붙여넣기" 버튼. 다이얼로그마다 stage 후 후처리만
다르므로 (GridSplit 은 preview / overlay, ManualCrop 은 _replace_image) ``stage`` →
``_consume_clipboard_image(staged)`` template method 로 분리한다.

회귀 방지: dialog destroy 시 tempdir 을 통째로 정리해야 base/ 에 누수가 안 된다.
mixin 의 ``_cleanup_clipboard()`` 가 그 책임을 진다.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from clipboard_utils import ClipboardImageError, stage_clipboard_image

logger = logging.getLogger(__name__)


def _cleanup_clip_tempdir(tempdir: Path | None) -> None:
    """dialog 의 클립보드 staging tempdir 을 통째로 제거.

    paste 한 PNG 가 BASE_DIR 에 누수되지 않도록 dialog 별 tempdir 을 만들고
    dialog ``destroy`` 시 이 함수로 정리한다. ``tempdir`` 이 None 이면 no-op.
    """
    if tempdir is None:
        return
    shutil.rmtree(tempdir, ignore_errors=True)


class ClipboardPasteMixin:
    """tk.Toplevel 에 mix-in 해 클립보드 paste 트리거 3종 + tempdir 격리 제공.

    구현체가 정의해야 할 것:
      - ``_consume_clipboard_image(self, staged: Path) -> None``
        : stage 된 PNG 경로를 받아 자기 다이얼로그의 후처리 (preview / canvas 갱신).

    선택 속성:
      - ``self.processing: bool``   — True 면 paste 무시. 없으면 항상 활성.

    사용:
      1. ``__init__`` 안에서 ``self._bind_clipboard(self.canvas)`` 호출
      2. ``destroy`` 안에서 super().destroy() 전에 ``self._cleanup_clipboard()`` 호출
    """

    _clip_tempdir: Path | None = None

    def _bind_clipboard(self, canvas: tk.Widget) -> None:
        self.bind("<Control-v>", self._on_paste_shortcut)
        self.bind("<Command-v>", self._on_paste_shortcut)
        canvas.bind("<Button-3>", self._show_clipboard_menu)
        canvas.bind("<Button-2>", self._show_clipboard_menu)

    def _on_paste_shortcut(self, event):
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, tk.Spinbox)):
            return None
        self._paste_from_clipboard()
        return "break"

    def _show_clipboard_menu(self, event) -> None:
        menu = tk.Menu(self, tearoff=0)
        state = "disabled" if getattr(self, "processing", False) else "normal"
        menu.add_command(
            label="📋 클립보드에서 붙여넣기",
            command=self._paste_from_clipboard,
            state=state,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _paste_from_clipboard(self) -> None:
        if getattr(self, "processing", False):
            return
        if self._clip_tempdir is None:
            self._clip_tempdir = Path(tempfile.mkdtemp(prefix="chromapeel_clip_"))
        try:
            staged = stage_clipboard_image(self._clip_tempdir)
        except ClipboardImageError as e:
            messagebox.showinfo("클립보드", str(e), parent=self)
            return
        except Exception as e:
            logger.warning("클립보드 이미지 저장 실패", exc_info=True)
            messagebox.showerror("클립보드 저장 실패", str(e), parent=self)
            return
        try:
            self._consume_clipboard_image(staged)
        except Exception as e:
            logger.warning("스테이징된 클립보드 이미지 처리 실패", exc_info=True)
            messagebox.showerror("이미지 처리 실패", str(e), parent=self)

    def _consume_clipboard_image(self, staged: Path) -> None:
        """구현체가 오버라이드 — stage 된 PNG 경로를 받아 자기 후처리를 한다."""
        raise NotImplementedError

    def _cleanup_clipboard(self) -> None:
        _cleanup_clip_tempdir(self._clip_tempdir)
        self._clip_tempdir = None
