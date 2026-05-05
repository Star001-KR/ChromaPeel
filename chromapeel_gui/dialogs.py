from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from grid_split import split_image_grid

from . import ALPHA_DIR, _open_path

logger = logging.getLogger(__name__)


class GridSplitDialog(tk.Toplevel):
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

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        # 부모 위에 모달로 표시.
        self.update_idletasks()
        self.grab_set()

    def _build_ui(self) -> None:
        file_row = ttk.Frame(self, padding=(10, 10, 10, 4))
        file_row.pack(fill="x")
        ttk.Button(file_row, text="이미지 선택...", command=self._select_image).pack(side="left")
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


class ManualCropDialog(tk.Toplevel):
    """이미지에서 사각형 영역을 마우스로 선택해 잘라내는 모달."""

    HANDLE_SIZE = 8
    HANDLE_HIT_PADDING = 4
    MIN_DRAG_PIXELS = 2
    MAX_CANVAS_WIDTH = 720
    MAX_CANVAS_HEIGHT = 540

    HANDLE_CURSORS = {
        "nw": "top_left_corner",
        "n": "top_side",
        "ne": "top_right_corner",
        "e": "right_side",
        "se": "bottom_right_corner",
        "s": "bottom_side",
        "sw": "bottom_left_corner",
        "w": "left_side",
    }

    def __init__(self, parent, image_path: Path, on_complete=None):
        super().__init__(parent)
        self.title(f"크롭 — {image_path.name}")
        self.transient(parent)
        self.resizable(False, False)

        self.image_path = image_path
        self.on_complete = on_complete

        self._pil_image = Image.open(image_path)
        self.orig_w, self.orig_h = self._pil_image.size

        scale = min(
            self.MAX_CANVAS_WIDTH / self.orig_w,
            self.MAX_CANVAS_HEIGHT / self.orig_h,
            1.0,
        )
        self.scale = scale
        self.disp_w = max(1, int(round(self.orig_w * scale)))
        self.disp_h = max(1, int(round(self.orig_h * scale)))

        if scale < 1.0:
            disp_image = self._pil_image.resize(
                (self.disp_w, self.disp_h), Image.LANCZOS
            )
        else:
            disp_image = self._pil_image
        self._photo = ImageTk.PhotoImage(disp_image)

        self.box: tuple[float, float, float, float] | None = None
        self._drag_mode: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._box_at_drag_start: tuple[float, float, float, float] | None = None
        self._suppress_entry_sync = False

        self._build_ui()
        self.grab_set()
        self.focus_set()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            outer, width=self.disp_w, height=self.disp_h,
            highlightthickness=1, highlightbackground="#888",
            background="#222", cursor="crosshair",
        )
        self.canvas.grid(row=0, column=0, padx=(0, 8), sticky="n")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="n")

        ttk.Label(
            right, text=f"원본: {self.orig_w}×{self.orig_h}px",
            foreground="#666",
        ).pack(anchor="w", pady=(0, 6))
        if self.scale < 1.0:
            ttk.Label(
                right, text=f"표시 비율: {self.scale * 100:.0f}%",
                foreground="#888",
            ).pack(anchor="w", pady=(0, 8))

        self.x_var = tk.StringVar(value="0")
        self.y_var = tk.StringVar(value="0")
        self.w_var = tk.StringVar(value="0")
        self.h_var = tk.StringVar(value="0")

        for label, var in [
            ("X", self.x_var), ("Y", self.y_var),
            ("Width", self.w_var), ("Height", self.h_var),
        ]:
            row = ttk.Frame(right)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=8).pack(side="left")
            ttk.Entry(row, textvariable=var, width=10).pack(side="left")
            var.trace_add("write", lambda *_: self._on_entry_changed())

        ttk.Label(
            right, text="빈 영역 드래그로 선택,\n박스 내부 드래그로 이동,\n핸들 드래그로 크기 조정.",
            foreground="#666", justify="left",
        ).pack(anchor="w", pady=(12, 0))

        btnrow = ttk.Frame(outer)
        btnrow.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btnrow, text="취소", command=self._on_cancel).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(btnrow, text="확인", command=self._on_confirm).pack(side="right")

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_mouse_move)

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_confirm())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # --- coordinate helpers ---
    def _canvas_to_image(self, x: float, y: float) -> tuple[int, int]:
        ix = int(round(x / self.scale)) if self.scale else 0
        iy = int(round(y / self.scale)) if self.scale else 0
        ix = max(0, min(self.orig_w, ix))
        iy = max(0, min(self.orig_h, iy))
        return ix, iy

    def _image_to_canvas(self, ix: float, iy: float) -> tuple[float, float]:
        return ix * self.scale, iy * self.scale

    def _normalize_box(
        self, x1: float, y1: float, x2: float, y2: float,
    ) -> tuple[float, float, float, float]:
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        x1 = max(0, min(self.disp_w, x1))
        x2 = max(0, min(self.disp_w, x2))
        y1 = max(0, min(self.disp_h, y1))
        y2 = max(0, min(self.disp_h, y2))
        return x1, y1, x2, y2

    # --- drawing ---
    def _redraw_box(self) -> None:
        self.canvas.delete("box")
        self.canvas.delete("handle")
        if self.box is None:
            return
        x1, y1, x2, y2 = self.box
        self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="#ffeb3b", width=2, tags="box",
        )
        half = self.HANDLE_SIZE / 2
        for hx, hy in self._handle_positions().values():
            self.canvas.create_rectangle(
                hx - half, hy - half, hx + half, hy + half,
                fill="#ffeb3b", outline="#000", tags="handle",
            )

    def _handle_positions(self) -> dict[str, tuple[float, float]]:
        if self.box is None:
            return {}
        x1, y1, x2, y2 = self.box
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return {
            "nw": (x1, y1), "n": (cx, y1), "ne": (x2, y1),
            "e": (x2, cy), "se": (x2, y2), "s": (cx, y2),
            "sw": (x1, y2), "w": (x1, cy),
        }

    def _hit_handle(self, x: float, y: float) -> str | None:
        threshold = self.HANDLE_SIZE / 2 + self.HANDLE_HIT_PADDING
        for name, (hx, hy) in self._handle_positions().items():
            if abs(x - hx) <= threshold and abs(y - hy) <= threshold:
                return name
        return None

    def _hit_box_interior(self, x: float, y: float) -> bool:
        if self.box is None:
            return False
        x1, y1, x2, y2 = self.box
        return x1 <= x <= x2 and y1 <= y <= y2

    # --- entry sync ---
    def _update_entries_from_box(self) -> None:
        self._suppress_entry_sync = True
        try:
            if self.box is None:
                self.x_var.set("0")
                self.y_var.set("0")
                self.w_var.set("0")
                self.h_var.set("0")
                return
            x1, y1, x2, y2 = self.box
            ix1, iy1 = self._canvas_to_image(x1, y1)
            ix2, iy2 = self._canvas_to_image(x2, y2)
            self.x_var.set(str(ix1))
            self.y_var.set(str(iy1))
            self.w_var.set(str(max(0, ix2 - ix1)))
            self.h_var.set(str(max(0, iy2 - iy1)))
        finally:
            self._suppress_entry_sync = False

    def _on_entry_changed(self) -> None:
        if self._suppress_entry_sync:
            return
        try:
            ix = int(self.x_var.get())
            iy = int(self.y_var.get())
            iw = int(self.w_var.get())
            ih = int(self.h_var.get())
        except ValueError:
            return
        if iw <= 0 or ih <= 0:
            return
        ix = max(0, min(self.orig_w, ix))
        iy = max(0, min(self.orig_h, iy))
        iw = max(1, min(self.orig_w - ix, iw))
        ih = max(1, min(self.orig_h - iy, ih))
        x1, y1 = self._image_to_canvas(ix, iy)
        x2, y2 = self._image_to_canvas(ix + iw, iy + ih)
        self.box = (x1, y1, x2, y2)
        self._redraw_box()

    # --- mouse events ---
    def _on_mouse_down(self, event) -> None:
        x, y = float(event.x), float(event.y)
        handle = self._hit_handle(x, y)
        if handle is not None:
            self._drag_mode = f"resize:{handle}"
            self._drag_start = (x, y)
            self._box_at_drag_start = self.box
            return
        if self._hit_box_interior(x, y):
            self._drag_mode = "move"
            self._drag_start = (x, y)
            self._box_at_drag_start = self.box
            return
        cx = max(0.0, min(float(self.disp_w), x))
        cy = max(0.0, min(float(self.disp_h), y))
        self._drag_mode = "create"
        self._drag_start = (cx, cy)
        self.box = (cx, cy, cx, cy)
        self._redraw_box()
        self._update_entries_from_box()

    def _on_mouse_drag(self, event) -> None:
        if self._drag_mode is None or self._drag_start is None:
            return
        x = max(0.0, min(float(self.disp_w), float(event.x)))
        y = max(0.0, min(float(self.disp_h), float(event.y)))
        if self._drag_mode == "create":
            sx, sy = self._drag_start
            self.box = self._normalize_box(sx, sy, x, y)
        elif self._drag_mode == "move" and self._box_at_drag_start is not None:
            sx, sy = self._drag_start
            ox1, oy1, ox2, oy2 = self._box_at_drag_start
            w = ox2 - ox1
            h = oy2 - oy1
            nx1 = max(0.0, min(self.disp_w - w, ox1 + (x - sx)))
            ny1 = max(0.0, min(self.disp_h - h, oy1 + (y - sy)))
            self.box = (nx1, ny1, nx1 + w, ny1 + h)
        elif self._drag_mode.startswith("resize:") and self._box_at_drag_start is not None:
            handle = self._drag_mode.split(":", 1)[1]
            ox1, oy1, ox2, oy2 = self._box_at_drag_start
            nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2
            if "n" in handle:
                ny1 = y
            if "s" in handle:
                ny2 = y
            if "w" in handle:
                nx1 = x
            if "e" in handle:
                nx2 = x
            self.box = self._normalize_box(nx1, ny1, nx2, ny2)
        self._redraw_box()
        self._update_entries_from_box()

    def _on_mouse_up(self, event) -> None:
        if self._drag_mode == "create" and self.box is not None:
            x1, y1, x2, y2 = self.box
            if (x2 - x1) < self.MIN_DRAG_PIXELS or (y2 - y1) < self.MIN_DRAG_PIXELS:
                self.box = None
                self.canvas.delete("box")
                self.canvas.delete("handle")
                self._update_entries_from_box()
        self._drag_mode = None
        self._drag_start = None
        self._box_at_drag_start = None

    def _on_mouse_move(self, event) -> None:
        if self._drag_mode is not None:
            return
        x, y = float(event.x), float(event.y)
        handle = self._hit_handle(x, y)
        if handle is not None:
            self.canvas.configure(cursor=self.HANDLE_CURSORS.get(handle, "sizing"))
        elif self._hit_box_interior(x, y):
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="crosshair")

    # --- finish ---
    def _on_cancel(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _on_confirm(self) -> None:
        if self.box is None:
            messagebox.showwarning(
                "크롭 영역 없음", "먼저 크롭 영역을 선택하세요.", parent=self,
            )
            return
        x1, y1, x2, y2 = self.box
        ix1, iy1 = self._canvas_to_image(x1, y1)
        ix2, iy2 = self._canvas_to_image(x2, y2)
        w = ix2 - ix1
        h = iy2 - iy1
        if w <= 0 or h <= 0:
            messagebox.showwarning(
                "크롭 영역 오류",
                "영역의 너비와 높이는 1픽셀 이상이어야 합니다.",
                parent=self,
            )
            return
        try:
            from manual_crop import crop_image
        except ImportError as e:
            messagebox.showerror(
                "크롭 모듈 없음",
                f"manual_crop 모듈을 불러올 수 없습니다: {e}",
                parent=self,
            )
            return
        try:
            out_path = crop_image(
                str(self.image_path), ix1, iy1, w, h, out_dir=str(ALPHA_DIR),
            )
        except Exception as e:
            messagebox.showerror("크롭 실패", str(e), parent=self)
            return
        if self.on_complete is not None:
            try:
                self.on_complete(Path(out_path))
            except Exception:
                logger.warning("크롭 완료 콜백 실패", exc_info=True)
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
