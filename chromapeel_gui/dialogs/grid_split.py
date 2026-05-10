"""격자 분할 모달 — Rows×Cols 또는 Cell W×H 두 모드.

미리보기 캔버스에 격자 라인 + 잔여 영역(clip) 오버레이를 그려 사용자에게
실제 분할 결과를 즉시 보여준다. 실행은 worker thread 에서 수행하고 완료 시
``alpha/{stem}_split/`` 폴더를 탐색기로 연다.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from grid_split import split_image_grid

from .. import ALPHA_DIR, _open_path
from ._clipboard import ClipboardPasteMixin

logger = logging.getLogger(__name__)


class GridSplitDialog(ClipboardPasteMixin, tk.Toplevel):
    """이미지 격자 분할 모달. Rows×Cols 또는 Cell W×H 모드로 동작."""

    PREVIEW_SIZE = 400
    GRID_COLOR = "#ff0000"
    CLIP_COLOR = "#888888"

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("격자 분할")
        self.transient(parent)
        self.resizable(False, False)

        self.image_path: Path | None = None
        self.image_size: tuple[int, int] | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_offset: tuple[int, int] = (0, 0)
        self._preview_scale: float = 1.0
        self.processing = False

        self.mode = tk.StringVar(value="rowcol")
        self.rows = tk.IntVar(value=2)
        self.cols = tk.IntVar(value=2)
        self.cell_w = tk.IntVar(value=64)
        self.cell_h = tk.IntVar(value=64)

        self._build_ui()
        # 변수 변경 추적 — Spinbox 키보드 입력까지 잡힘.
        for v in (self.rows, self.cols, self.cell_w, self.cell_h):
            v.trace_add("write", lambda *_: self._update_preview_overlay())
        self._update_mode_state()

        self._bind_clipboard(self.canvas)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        # 부모 위에 모달로 표시.
        self.update_idletasks()
        self.grab_set()

    def _build_ui(self) -> None:
        file_row = ttk.Frame(self, padding=(10, 10, 10, 4))
        file_row.pack(fill="x")
        ttk.Button(file_row, text="이미지 선택...", command=self._select_image).pack(side="left")
        ttk.Button(
            file_row, text="📋 붙여넣기", command=self._paste_from_clipboard,
        ).pack(side="left", padx=(8, 0))
        self.path_label = ttk.Label(file_row, text="(선택된 이미지 없음)", foreground="#888")
        self.path_label.pack(side="left", padx=8)

        mode_row = ttk.Frame(self, padding=(10, 4))
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text="모드:").pack(side="left")
        ttk.Radiobutton(
            mode_row, text="Rows × Cols", variable=self.mode, value="rowcol",
            command=self._update_mode_state,
        ).pack(side="left", padx=8)
        ttk.Radiobutton(
            mode_row, text="Cell W × H", variable=self.mode, value="cell",
            command=self._update_mode_state,
        ).pack(side="left", padx=8)

        input_row = ttk.Frame(self, padding=(10, 4))
        input_row.pack(fill="x")

        self.rowcol_frame = ttk.Frame(input_row)
        self.rowcol_frame.pack(side="left", padx=(0, 16))
        ttk.Label(self.rowcol_frame, text="Rows:").pack(side="left")
        self.rows_spin = ttk.Spinbox(
            self.rowcol_frame, from_=1, to=999, textvariable=self.rows, width=5,
        )
        self.rows_spin.pack(side="left", padx=4)
        ttk.Label(self.rowcol_frame, text="Cols:").pack(side="left", padx=(8, 0))
        self.cols_spin = ttk.Spinbox(
            self.rowcol_frame, from_=1, to=999, textvariable=self.cols, width=5,
        )
        self.cols_spin.pack(side="left", padx=4)

        self.cell_frame = ttk.Frame(input_row)
        self.cell_frame.pack(side="left")
        ttk.Label(self.cell_frame, text="Cell W:").pack(side="left")
        self.cell_w_spin = ttk.Spinbox(
            self.cell_frame, from_=1, to=9999, textvariable=self.cell_w, width=6,
        )
        self.cell_w_spin.pack(side="left", padx=4)
        ttk.Label(self.cell_frame, text="Cell H:").pack(side="left", padx=(8, 0))
        self.cell_h_spin = ttk.Spinbox(
            self.cell_frame, from_=1, to=9999, textvariable=self.cell_h, width=6,
        )
        self.cell_h_spin.pack(side="left", padx=4)

        preview_lf = ttk.Labelframe(self, text=" 미리보기 ", padding=4)
        preview_lf.pack(padx=10, pady=6)
        self.canvas = tk.Canvas(
            preview_lf, width=self.PREVIEW_SIZE, height=self.PREVIEW_SIZE,
            background="#fafafa", highlightthickness=1, highlightbackground="#ccc",
        )
        self.canvas.pack()

        self.clip_label = ttk.Label(
            self, text="이미지를 선택하세요", padding=(10, 2), foreground="#888",
        )
        self.clip_label.pack(fill="x")

        btn_row = ttk.Frame(self, padding=(10, 6, 10, 10))
        btn_row.pack(fill="x")
        self.btn_split = ttk.Button(btn_row, text="분할 실행", command=self._start_split)
        self.btn_split.pack(side="right")
        self.btn_cancel = ttk.Button(btn_row, text="취소", command=self._on_cancel)
        self.btn_cancel.pack(side="right", padx=(0, 8))
        self.status_label = ttk.Label(btn_row, text="")
        self.status_label.pack(side="left")

    def _consume_clipboard_image(self, staged: Path) -> None:
        with Image.open(staged) as img:
            img.load()
            size = img.size
            preview_img = img.copy()
        self.image_path = staged
        self.image_size = size
        display = str(staged)
        if len(display) > 60:
            display = "..." + display[-57:]
        self.path_label.configure(text=display, foreground="#000")
        self._render_preview(preview_img)
        self._update_preview_overlay()

    def destroy(self) -> None:
        # destroy 는 _on_cancel/_on_split_done/WM_DELETE 모두의 공통 종료 path.
        # 클립보드 tempdir 은 여기서 한 번에 정리한다 — base/ 누수 회귀 방지.
        self._cleanup_clipboard()
        super().destroy()

    def _select_image(self) -> None:
        path_str = filedialog.askopenfilename(
            title="분할할 이미지 선택",
            filetypes=[("PNG 이미지", "*.png"), ("모든 이미지", "*.png *.jpg *.jpeg *.bmp"), ("모든 파일", "*.*")],
            parent=self,
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            with Image.open(path) as img:
                img.load()
                size = img.size
                preview_img = img.copy()
        except Exception as e:
            messagebox.showerror("이미지 열기 실패", str(e), parent=self)
            return
        self.image_path = path
        self.image_size = size
        display = str(path)
        if len(display) > 60:
            display = "..." + display[-57:]
        self.path_label.configure(text=display, foreground="#000")
        self._render_preview(preview_img)
        self._update_preview_overlay()

    def _render_preview(self, img: Image.Image) -> None:
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGBA")
        iw, ih = img.size
        img.thumbnail((self.PREVIEW_SIZE, self.PREVIEW_SIZE))
        new_w, new_h = img.size
        self._preview_photo = ImageTk.PhotoImage(img)
        self._preview_scale = new_w / iw if iw else 1.0
        self._preview_offset = (
            (self.PREVIEW_SIZE - new_w) // 2,
            (self.PREVIEW_SIZE - new_h) // 2,
        )
        self.canvas.delete("all")
        self.canvas.create_image(
            self._preview_offset[0], self._preview_offset[1],
            image=self._preview_photo, anchor="nw", tags="image",
        )

    def _update_mode_state(self) -> None:
        if self.mode.get() == "rowcol":
            for w in (self.rows_spin, self.cols_spin):
                w.configure(state="normal")
            for w in (self.cell_w_spin, self.cell_h_spin):
                w.configure(state="disabled")
        else:
            for w in (self.rows_spin, self.cols_spin):
                w.configure(state="disabled")
            for w in (self.cell_w_spin, self.cell_h_spin):
                w.configure(state="normal")
        self._update_preview_overlay()

    def _get_validated_params(self) -> dict | None:
        if self.image_size is None:
            return None
        iw, ih = self.image_size
        try:
            if self.mode.get() == "rowcol":
                rows = int(self.rows.get())
                cols = int(self.cols.get())
                if rows < 1 or cols < 1:
                    return None
                return {"rows": rows, "cols": cols}
            cw = int(self.cell_w.get())
            ch = int(self.cell_h.get())
            if cw < 1 or ch < 1 or cw > iw or ch > ih:
                return None
            return {"cell_w": cw, "cell_h": ch}
        except (tk.TclError, ValueError):
            return None

    def _update_preview_overlay(self) -> None:
        self.canvas.delete("grid")
        self.canvas.delete("clip")

        if self.image_size is None:
            self.clip_label.configure(text="이미지를 선택하세요", foreground="#888")
            return

        params = self._get_validated_params()
        if params is None:
            self.clip_label.configure(
                text="입력값이 올바르지 않습니다", foreground="#cc6600",
            )
            return

        iw, ih = self.image_size
        ox, oy = self._preview_offset
        s = self._preview_scale
        pw, ph = iw * s, ih * s

        if "rows" in params:
            rows = params["rows"]
            cols = params["cols"]
            for r in range(1, rows):
                y = oy + (r * ph) / rows
                self.canvas.create_line(
                    ox, y, ox + pw, y,
                    fill=self.GRID_COLOR, dash=(4, 2), tags="grid",
                )
            for c in range(1, cols):
                x = ox + (c * pw) / cols
                self.canvas.create_line(
                    x, oy, x, oy + ph,
                    fill=self.GRID_COLOR, dash=(4, 2), tags="grid",
                )
            self.clip_label.configure(
                text=f"균등 {rows}×{cols} 분할 ({iw}×{ih} px)",
                foreground="#000",
            )
        else:
            cw = params["cell_w"]
            ch = params["cell_h"]
            n_cols = iw // cw
            n_rows = ih // ch
            clip_w = iw - n_cols * cw
            clip_h = ih - n_rows * ch
            for r in range(1, n_rows + 1):
                y = oy + (r * ch) * s
                self.canvas.create_line(
                    ox, y, ox + pw, y,
                    fill=self.GRID_COLOR, dash=(4, 2), tags="grid",
                )
            for c in range(1, n_cols + 1):
                x = ox + (c * cw) * s
                self.canvas.create_line(
                    x, oy, x, oy + ph,
                    fill=self.GRID_COLOR, dash=(4, 2), tags="grid",
                )
            if clip_w > 0:
                x_start = ox + (n_cols * cw) * s
                self.canvas.create_rectangle(
                    x_start, oy, ox + pw, oy + ph,
                    fill=self.CLIP_COLOR, stipple="gray50", outline="", tags="clip",
                )
            if clip_h > 0:
                y_start = oy + (n_rows * ch) * s
                self.canvas.create_rectangle(
                    ox, y_start, ox + pw, oy + ph,
                    fill=self.CLIP_COLOR, stipple="gray50", outline="", tags="clip",
                )
            if clip_w or clip_h:
                self.clip_label.configure(
                    text=f"{n_rows}×{n_cols} 셀 — 마지막 {clip_w}×{clip_h} px가 잘려나감",
                    foreground="#cc6600",
                )
            else:
                self.clip_label.configure(
                    text=f"{n_rows}×{n_cols} 셀 — 정확히 나누어떨어짐",
                    foreground="#000",
                )

    def _start_split(self) -> None:
        if self.processing:
            return
        if self.image_path is None:
            messagebox.showwarning(
                "이미지 미선택", "이미지를 먼저 선택하세요", parent=self,
            )
            return
        params = self._get_validated_params()
        if params is None:
            messagebox.showerror(
                "입력 오류", "분할 수치가 올바르지 않습니다", parent=self,
            )
            return

        out_dir = ALPHA_DIR / f"{self.image_path.stem}_split"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("출력 디렉토리 생성 실패", str(e), parent=self)
            return

        self.processing = True
        self.btn_split.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.status_label.configure(text="처리 중...")

        threading.Thread(
            target=self._run_split, args=(out_dir, params), daemon=True,
        ).start()

    def _run_split(self, out_dir: Path, params: dict) -> None:
        try:
            split_image_grid(self.image_path, out_dir, **params)
            self.after(0, lambda: self._on_split_done(out_dir, None))
        except Exception as e:
            err = e
            self.after(0, lambda: self._on_split_done(out_dir, err))

    def _on_split_done(self, out_dir: Path, error: Exception | None) -> None:
        self.processing = False
        if error is not None:
            self.btn_split.configure(state="normal")
            self.btn_cancel.configure(state="normal")
            self.status_label.configure(text="")
            messagebox.showerror("분할 실패", str(error), parent=self)
            return
        try:
            _open_path(out_dir.resolve())
        except Exception:
            logger.warning("결과 폴더 열기 실패: %s", out_dir, exc_info=True)
            messagebox.showinfo(
                "분할 완료", f"결과 폴더: {out_dir}", parent=self,
            )
        self.destroy()

    def _on_cancel(self) -> None:
        if self.processing:
            return
        self.destroy()
