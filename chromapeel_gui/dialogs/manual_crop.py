"""수동 크롭 모달 — 마우스 드래그로 사각형 영역 선택, 8핸들 리사이즈.

캔버스에 표시 비율을 자동 계산해 큰 이미지도 모달 안에 들어가도록 한다.
X / Y / W / H 입력 칸과 양방향 동기화되며, 확인 시 ``manual_crop.crop_image``
를 호출해 ``alpha/{stem}_crop.png`` 로 저장한다.
"""
from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from imageAlpha import EXHAUSTED_USER_MESSAGE, OutputNameExhaustedError

from .. import ALPHA_DIR
from ._clipboard import ClipboardPasteMixin

logger = logging.getLogger(__name__)


class ManualCropDialog(ClipboardPasteMixin, tk.Toplevel):
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
        self.transient(parent)
        self.resizable(False, False)

        self.on_complete = on_complete
        # _load_image_state 가 이전 _pil_image 를 close 하기 위해 None 으로 미리 둔다.
        self._pil_image: Image.Image | None = None

        self._load_image_state(image_path)

        self.box: tuple[float, float, float, float] | None = None
        self._drag_mode: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._box_at_drag_start: tuple[float, float, float, float] | None = None
        self._suppress_entry_sync = False

        self._build_ui()
        self._bind_clipboard(self.canvas)
        self.grab_set()
        self.focus_set()

    def _load_image_state(self, image_path: Path) -> None:
        # 이전 paste/load 의 PIL handle 이 살아 있으면 먼저 close — 그렇지 않으면
        # Windows 에서 staging tempdir 이 file lock 으로 삭제 실패할 수 있다.
        old = self._pil_image
        if old is not None:
            try:
                old.close()
            except Exception:
                logger.debug("이전 PIL 이미지 close 실패", exc_info=True)
        self.image_path = Path(image_path)
        self._pil_image = Image.open(self.image_path)
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
                (self.disp_w, self.disp_h), Image.Resampling.LANCZOS
            )
        else:
            disp_image = self._pil_image
        self._photo = ImageTk.PhotoImage(disp_image)
        self.title(f"크롭 — {self.image_path.name}")

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

        self.btn_paste = ttk.Button(
            right, text="📋 클립보드 이미지 사용",
            command=self._paste_from_clipboard,
        )
        self.btn_paste.pack(anchor="w", pady=(0, 8))

        self.orig_label = ttk.Label(
            right, text=f"원본: {self.orig_w}×{self.orig_h}px",
            foreground="#666",
        )
        self.orig_label.pack(anchor="w", pady=(0, 6))
        self.scale_label = ttk.Label(
            right, text=f"표시 비율: {self.scale * 100:.0f}%",
            foreground="#888",
        )
        if self.scale < 1.0:
            self.scale_label.pack(anchor="w", pady=(0, 8))

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

    # --- clipboard ---
    def _consume_clipboard_image(self, staged: Path) -> None:
        self._replace_image(staged)

    def _replace_image(self, image_path: Path) -> None:
        self._load_image_state(image_path)
        self.canvas.configure(width=self.disp_w, height=self.disp_h)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.box = None
        self._drag_mode = None
        self._drag_start = None
        self._box_at_drag_start = None
        self._update_entries_from_box()
        self.orig_label.configure(text=f"원본: {self.orig_w}×{self.orig_h}px")
        self.scale_label.configure(text=f"표시 비율: {self.scale * 100:.0f}%")
        if self.scale < 1.0:
            if not self.scale_label.winfo_ismapped():
                self.scale_label.pack(
                    anchor="w", pady=(0, 8), after=self.orig_label,
                )
        else:
            self.scale_label.pack_forget()

    # --- finish ---
    def destroy(self) -> None:
        # _on_cancel/_on_confirm 모두 self.destroy() 로 수렴하므로 여기서
        # tempdir 과 PIL handle 을 한 번에 정리한다.
        if self._pil_image is not None:
            try:
                self._pil_image.close()
            except Exception:
                logger.debug("PIL 이미지 close 실패", exc_info=True)
            self._pil_image = None
        self._cleanup_clipboard()
        super().destroy()

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
        except OutputNameExhaustedError:
            # _99 까지 모두 점유 — 사용자 친화적 양식으로 안내, 다이얼로그 유지.
            crop_target = f"{self.image_path.stem}_crop.png"
            messagebox.showwarning(
                "크롭 저장 불가",
                EXHAUSTED_USER_MESSAGE.format(filename=crop_target),
                parent=self,
            )
            return
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
