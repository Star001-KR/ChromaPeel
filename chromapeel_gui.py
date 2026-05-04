from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, simpledialog, ttk

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import imageAlpha
from imageAlpha import __version__
from clipboard_utils import copy_image_to_clipboard

logger = logging.getLogger(__name__)

DEFAULT_TARGET_COLOR = (255, 37, 255)
DEFAULT_TOLERANCE = 20
DEFAULT_FEATHER = 100
DEFAULT_DECONTAMINATE = True
DEFAULT_EDGE_EROSION = 1
DEFAULT_AUTO_DETECT_BG = False

THUMB_SIZE = 96

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


class ThumbnailView(ttk.Frame):
    """Scrollable grid of image thumbnails. Optional drag-out and right-click menu support."""

    def __init__(self, parent, drag_out: bool = False, columns: int = 4,
                 on_right_click=None, on_double_click=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.drag_out = drag_out
        self.columns = columns
        self.on_right_click = on_right_click
        self.on_double_click = on_double_click

        self.canvas = tk.Canvas(self, highlightthickness=0, background="#fafafa")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self._thumbs: dict[str, ImageTk.PhotoImage] = {}
        self._cells: list[tk.Widget] = []
        self._placeholder: tk.Widget | None = None

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def drop_targets(self) -> list[tk.Widget]:
        return [self, self.canvas, self.inner]

    def clear(self):
        for w in self._cells:
            w.destroy()
        self._cells.clear()
        self._thumbs.clear()
        self._remove_placeholder()

    def show_placeholder(self, text: str):
        self.clear()
        self._placeholder = ttk.Label(
            self.inner, text=text, foreground="#888",
            padding=20, justify="center", anchor="center",
        )
        self._placeholder.grid(row=0, column=0, columnspan=self.columns, padx=20, pady=40, sticky="nsew")

    def _remove_placeholder(self):
        if self._placeholder is not None:
            self._placeholder.destroy()
            self._placeholder = None

    def add_thumbnail(self, path: Path):
        self._remove_placeholder()
        try:
            img = Image.open(path)
            img.thumbnail((THUMB_SIZE, THUMB_SIZE))
            photo = ImageTk.PhotoImage(img)
        except Exception:
            logger.warning("썸네일 로드 실패: %s", path, exc_info=True)
            return

        idx = len(self._cells)
        row = idx // self.columns
        col = idx % self.columns

        cell = ttk.Frame(self.inner, padding=4)
        cell.grid(row=row, column=col, padx=4, pady=4, sticky="n")

        image_label = tk.Label(cell, image=photo, bd=1, relief="solid", bg="#ffffff",
                               width=THUMB_SIZE, height=THUMB_SIZE)
        image_label.image = photo
        image_label.pack()

        name = path.name
        if len(name) > 16:
            name = name[:13] + "..."
        ttk.Label(cell, text=name, font=("", 8)).pack()

        self._thumbs[str(path)] = photo
        self._cells.append(cell)

        if self.drag_out:
            abs_path = str(path.resolve())
            image_label.drag_source_register(1, DND_FILES)
            image_label.dnd_bind("<<DragInitCmd>>", lambda e, p=abs_path: ("copy", DND_FILES, (p,)))
            image_label.configure(cursor="hand2")

        if self.on_right_click is not None:
            resolved = path.resolve()
            image_label.bind(
                "<Button-3>",
                lambda e, p=resolved: self.on_right_click(p, e.x_root, e.y_root),
            )

        if self.on_double_click is not None:
            resolved = path.resolve()
            image_label.bind(
                "<Double-Button-1>",
                lambda e, p=resolved: self.on_double_click(p),
            )


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


class ChromaPeelApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title(f"ChromaPeel {__version__}")
        self.root.geometry("940x680")
        self.root.minsize(780, 580)

        BASE_DIR.mkdir(exist_ok=True)
        ALPHA_DIR.mkdir(exist_ok=True)

        self.target_color: tuple[int, int, int] = DEFAULT_TARGET_COLOR
        self.tolerance = tk.IntVar(value=DEFAULT_TOLERANCE)
        self.feather = tk.IntVar(value=DEFAULT_FEATHER)
        self.decontaminate = tk.BooleanVar(value=DEFAULT_DECONTAMINATE)
        self.edge_erosion = tk.IntVar(value=DEFAULT_EDGE_EROSION)
        self.auto_detect_bg = tk.BooleanVar(value=DEFAULT_AUTO_DETECT_BG)

        self.advanced_visible = False
        self.processing = False
        self.status = tk.StringVar(value="준비 — PNG를 입력 패널로 드래그하세요")

        self._build_ui()
        self._refresh_inputs_from_disk()
        self._refresh_outputs_from_disk()

    def _build_ui(self):
        root = self.root

        panels = ttk.Frame(root, padding=(10, 10, 10, 6))
        panels.pack(fill="both", expand=True)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)

        input_lf = ttk.Labelframe(panels, text=" 입력 — 드래그로 등록 · 우클릭으로 복사/제거 ")
        input_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.input_view = ThumbnailView(
            input_lf, drag_out=False,
            on_right_click=lambda p, x, y: self._show_context_menu(
                p, x, y, include_remove_input=True, include_rename=False
            ),
            on_double_click=self._open_file,
        )
        self.input_view.pack(fill="both", expand=True, padx=4, pady=4)
        self.input_view.show_placeholder("여기에 PNG 파일을 드래그하세요")
        for w in [input_lf, self.input_view, *self.input_view.drop_targets()]:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", self._on_drop)

        output_lf = ttk.Labelframe(panels, text=" 결과 — 드래그로 가져가기 · 우클릭으로 복사·이름 변경 ")
        output_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.output_view = ThumbnailView(
            output_lf, drag_out=True,
            on_right_click=lambda p, x, y: self._show_context_menu(
                p, x, y, include_remove_input=False, include_rename=True
            ),
            on_double_click=self._open_file,
        )
        self.output_view.pack(fill="both", expand=True, padx=4, pady=4)

        btnrow = ttk.Frame(root, padding=(10, 4))
        btnrow.pack(fill="x")
        self.btn_clear = ttk.Button(btnrow, text="입력 비우기", command=self._clear_inputs)
        self.btn_clear.pack(side="left")
        self.btn_open_out = ttk.Button(btnrow, text="결과 폴더 열기", command=self._open_alpha_dir)
        self.btn_open_out.pack(side="right")
        self.btn_convert = ttk.Button(btnrow, text="   변환   ", command=self._start_conversion)
        self.btn_convert.pack()

        progress_row = ttk.Frame(root, padding=(10, 0))
        progress_row.pack(fill="x")
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=1)
        self.progress.pack(fill="x")

        toggle_row = ttk.Frame(root, padding=(10, 2))
        toggle_row.pack(fill="x")
        self.btn_toggle = ttk.Button(toggle_row, text="▸ 고급 설정", command=self._toggle_advanced, width=14)
        self.btn_toggle.pack(side="left")

        self.advanced = ttk.Labelframe(root, text=" 파라미터 ", padding=10)
        self._build_advanced(self.advanced)
        self._update_color_ui_state()

        self.status_sep = ttk.Separator(root, orient="horizontal")
        self.status_sep.pack(fill="x", side="bottom", before=toggle_row)
        status_bar = ttk.Label(root, textvariable=self.status, padding=(10, 4), anchor="w", relief="flat")
        status_bar.pack(fill="x", side="bottom", before=self.status_sep)

    def _build_advanced(self, parent):
        color_row = ttk.Frame(parent)
        color_row.pack(fill="x", pady=3)
        ttk.Label(color_row, text="대상 색상:", width=14).pack(side="left")
        self.color_swatch = tk.Label(color_row, text="  ", bg=self._rgb_to_hex(self.target_color),
                                      width=4, relief="solid", bd=1)
        self.color_swatch.pack(side="left", padx=4)
        self.color_label = ttk.Label(color_row, text=str(self.target_color))
        self.color_label.pack(side="left", padx=4)
        self.pick_color_btn = ttk.Button(color_row, text="색상 선택", command=self._pick_color)
        self.pick_color_btn.pack(side="left", padx=4)
        ttk.Checkbutton(
            color_row, text="자동 감지",
            variable=self.auto_detect_bg,
            command=self._update_color_ui_state,
        ).pack(side="left", padx=12)

        self._build_scale_row(parent, "Tolerance:", self.tolerance, 0, 255)
        self._build_scale_row(parent, "Feather:", self.feather, 0, 300)

        edge_row = ttk.Frame(parent)
        edge_row.pack(fill="x", pady=3)
        ttk.Label(edge_row, text="Edge Erosion:", width=14).pack(side="left")
        ttk.Spinbox(edge_row, from_=0, to=10, textvariable=self.edge_erosion, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(edge_row, text="Decontaminate", variable=self.decontaminate).pack(side="left", padx=16)
        ttk.Button(edge_row, text="기본값 복원", command=self._reset_defaults).pack(side="right")

    def _build_scale_row(self, parent, label_text: str, variable: tk.IntVar,
                         from_: int, to_: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label_text, width=14).pack(side="left")
        ttk.Scale(
            row, from_=from_, to=to_, variable=variable,
            command=lambda v: variable.set(int(float(v))),
        ).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(row, textvariable=variable, width=4).pack(side="left")

    def _toggle_advanced(self):
        if self.advanced_visible:
            self.advanced.pack_forget()
            self.btn_toggle.configure(text="▸ 고급 설정")
            self.advanced_visible = False
        else:
            self.advanced.pack(fill="x", padx=10, pady=(0, 6), before=self.status_sep)
            self.btn_toggle.configure(text="▾ 고급 설정")
            self.advanced_visible = True

    def _pick_color(self):
        color = colorchooser.askcolor(
            initialcolor=self._rgb_to_hex(self.target_color),
            title="대상 색상 선택",
        )
        if color[0] is None:
            return
        rgb = tuple(int(c) for c in color[0])
        self.target_color = rgb
        self.color_swatch.configure(bg=self._rgb_to_hex(rgb))
        self.color_label.configure(text=str(rgb))

    def _update_color_ui_state(self) -> None:
        if self.auto_detect_bg.get():
            self.color_swatch.configure(bg="#d0d0d0")
            self.color_label.configure(text="(파일별 자동)")
            self.pick_color_btn.configure(state="disabled")
        else:
            self.color_swatch.configure(bg=self._rgb_to_hex(self.target_color))
            self.color_label.configure(text=str(self.target_color))
            self.pick_color_btn.configure(state="normal")

    def _reset_defaults(self):
        self.target_color = DEFAULT_TARGET_COLOR
        self.tolerance.set(DEFAULT_TOLERANCE)
        self.feather.set(DEFAULT_FEATHER)
        self.decontaminate.set(DEFAULT_DECONTAMINATE)
        self.edge_erosion.set(DEFAULT_EDGE_EROSION)
        self.auto_detect_bg.set(DEFAULT_AUTO_DETECT_BG)
        self._update_color_ui_state()
        self._set_status("기본값으로 복원")

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _on_drop(self, event):
        if self.processing:
            self._set_status("처리 중 — 드롭 무시")
            return

        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            logger.debug("DnD 페이로드 splitlist 실패; 단일 경로로 폴백", exc_info=True)
            paths = [event.data]

        added = 0
        skipped: list[str] = []
        for raw in paths:
            p = Path(str(raw))
            if not p.is_file():
                skipped.append(f"{p.name}(파일 아님)")
                continue
            if p.suffix.lower() != ".png":
                skipped.append(f"{p.name}(PNG 아님)")
                continue
            dest = BASE_DIR / p.name
            try:
                shutil.copy2(p, dest)
                added += 1
            except Exception as e:
                skipped.append(f"{p.name}({e})")

        self._refresh_inputs_from_disk()

        parts = []
        if added:
            parts.append(f"{added}개 추가")
        if skipped:
            parts.append(f"{len(skipped)}개 건너뜀")
        self._set_status(" · ".join(parts) if parts else "드롭된 파일이 없습니다")

    def _refresh_view(self, view: ThumbnailView, folder: Path,
                      placeholder: str) -> None:
        files = self._list_pngs(folder)
        view.clear()
        if not files:
            view.show_placeholder(placeholder)
        else:
            for f in files:
                view.add_thumbnail(f)

    def _refresh_inputs_from_disk(self) -> None:
        self._refresh_view(self.input_view, BASE_DIR,
                           "여기에 PNG 파일을 드래그하세요")

    def _refresh_outputs_from_disk(self) -> None:
        self._refresh_view(self.output_view, ALPHA_DIR,
                           "변환 후 여기에 결과가 표시됩니다")

    @staticmethod
    def _list_pngs(folder: Path) -> list[Path]:
        if not folder.is_dir():
            return []
        return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".png")

    def _clear_inputs(self):
        if self.processing:
            return
        for f in self._list_pngs(BASE_DIR):
            try:
                f.unlink()
            except Exception:
                logger.warning("입력 파일 제거 실패: %s", f, exc_info=True)
        self._refresh_inputs_from_disk()
        self._set_status("입력을 비웠습니다")

    def _open_alpha_dir(self):
        try:
            _open_path(ALPHA_DIR.resolve())
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def _open_file(self, path: Path) -> None:
        try:
            _open_path(path)
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def _build_context_menu(self, path: Path, include_remove_input: bool = False,
                             include_rename: bool = False) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label="이미지 클립보드에 복사",
            command=lambda p=path: self._copy_image(p),
        )
        menu.add_command(
            label="파일 경로 복사",
            command=lambda p=path: self._copy_path(p),
        )
        menu.add_separator()
        menu.add_command(
            label="탐색기에서 보기",
            command=lambda p=path: self._reveal_in_explorer(p),
        )
        if include_rename:
            menu.add_separator()
            menu.add_command(
                label="이름 변경...",
                command=lambda p=path: self._rename_output(p),
                state="disabled" if self.processing else "normal",
            )
        if include_remove_input:
            menu.add_separator()
            menu.add_command(
                label="크롭...",
                command=lambda p=path: self._open_crop_dialog(p),
                state="disabled" if self.processing else "normal",
            )
            menu.add_command(
                label="이 입력 제거",
                command=lambda p=path: self._remove_input(p),
                state="disabled" if self.processing else "normal",
            )
        return menu

    def _show_context_menu(self, path: Path, x_root: int, y_root: int,
                           include_remove_input: bool, include_rename: bool) -> None:
        menu = self._build_context_menu(
            path,
            include_remove_input=include_remove_input,
            include_rename=include_rename,
        )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _open_crop_dialog(self, path: Path) -> None:
        if self.processing:
            return
        try:
            ManualCropDialog(self.root, path, on_complete=self._on_crop_complete)
        except Exception as e:
            messagebox.showerror("크롭 실패", f"이미지를 열 수 없습니다: {e}")

    def _on_crop_complete(self, out_path: Path) -> None:
        self._refresh_outputs_from_disk()
        self._set_status(f"크롭 완료 — {Path(out_path).name}")

    def _remove_input(self, path: Path):
        if self.processing:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            messagebox.showerror("제거 실패", str(e))
            return
        self._refresh_inputs_from_disk()
        self._set_status(f"입력 제거: {path.name}")

    # Characters Windows forbids in filenames (POSIX is more lenient,
    # but we keep one rule so behavior matches across platforms and
    # files stay portable).
    _ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'

    def _rename_output(self, path: Path):
        if self.processing:
            return
        new_name = simpledialog.askstring(
            "이름 변경",
            "새 파일명을 입력하세요 (.png 생략 가능)",
            initialvalue=path.name,
            parent=self.root,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        bad = [c for c in new_name if c in self._ILLEGAL_FILENAME_CHARS or ord(c) < 32]
        if bad:
            messagebox.showerror(
                "이름 변경 실패",
                "파일명에 사용할 수 없는 문자가 포함되어 있습니다: "
                + " ".join(sorted(set(bad))),
            )
            return
        if Path(new_name).suffix.lower() != ".png":
            new_name += ".png"
        new_path = path.with_name(new_name)
        if new_path == path:
            return
        # On case-insensitive filesystems, "IMG.png" → "img.png" refers
        # to the same file — skip the overwrite confirmation.
        same_file = False
        if new_path.exists():
            try:
                same_file = new_path.samefile(path)
            except OSError:
                same_file = False
            if not same_file and not messagebox.askyesno(
                "덮어쓰기 확인", f"{new_name} 파일이 이미 있습니다. 덮어쓸까요?"
            ):
                return
        try:
            path.replace(new_path)
        except Exception as e:
            messagebox.showerror("이름 변경 실패", str(e))
            return
        self._refresh_outputs_from_disk()
        self._set_status(f"이름 변경: {path.name} → {new_name}")

    def _copy_image(self, path: Path):
        try:
            copy_image_to_clipboard(path)
            self._set_status(f"이미지 클립보드에 복사됨: {path.name}")
        except Exception as e:
            self._set_status(f"클립보드 복사 실패: {e}")
            messagebox.showerror("클립보드 복사 실패", str(e))

    def _copy_path(self, path: Path):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(path))
        self.root.update()
        self._set_status(f"경로 복사됨: {path}")

    def _reveal_in_explorer(self, path: Path):
        try:
            _reveal_path(path)
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def _start_conversion(self):
        if self.processing:
            return
        inputs = self._list_pngs(BASE_DIR)
        if not inputs:
            self._set_status("변환할 파일이 없습니다. PNG를 드래그하세요.")
            return

        self.processing = True
        self.btn_convert.configure(state="disabled", text=" 변환 중... ")
        self.btn_clear.configure(state="disabled")
        self.output_view.clear()
        self.output_view.show_placeholder("변환 중...")
        self.progress.configure(maximum=len(inputs), value=0)
        self._set_status(f"0/{len(inputs)} 변환 시작...")

        params = {
            "target_color": None if self.auto_detect_bg.get() else self.target_color,
            "tolerance": int(self.tolerance.get()),
            "feather": int(self.feather.get()),
            "decontaminate": bool(self.decontaminate.get()),
            "edge_erosion": int(self.edge_erosion.get()),
        }

        threading.Thread(target=self._run_process, args=(params,), daemon=True).start()

    def _run_process(self, params):
        first_done = [False]
        failed = [0]

        def cb(i, total, in_path, out_path, error):
            def ui_update():
                if not first_done[0]:
                    self.output_view.clear()
                    first_done[0] = True
                if error is not None:
                    failed[0] += 1
                    self._set_status(
                        f"{i}/{total} 실패 — {Path(in_path).name}: {error}"
                    )
                else:
                    self.output_view.add_thumbnail(Path(out_path))
                    self._set_status(f"{i}/{total} 완료 — {Path(in_path).name}")
                self.progress.configure(value=i)
            self.root.after(0, ui_update)

        try:
            imageAlpha.process_folder(
                input_dir=str(BASE_DIR),
                output_dir=str(ALPHA_DIR),
                progress_callback=cb,
                **params,
            )
            self.root.after(0, lambda: self._on_done(None, failed[0]))
        except Exception as e:
            err = e
            self.root.after(0, lambda: self._on_done(err, failed[0]))

    def _on_done(self, error: Exception | None, failed: int = 0):
        self.processing = False
        self.btn_convert.configure(state="normal", text="   변환   ")
        self.btn_clear.configure(state="normal")
        if error is not None:
            self.progress.configure(value=0)
            self._set_status(f"오류: {error}")
            messagebox.showerror("변환 실패", str(error))
            self._refresh_outputs_from_disk()
        else:
            self.progress.configure(value=self.progress["maximum"])
            if failed:
                self._set_status(
                    f"변환 완료 — {failed}개 파일 실패. 결과 썸네일을 탐색기로 드래그하세요"
                )
            else:
                self._set_status("변환 완료 — 결과 썸네일을 탐색기로 드래그하세요")

    def _set_status(self, text: str):
        self.status.set(text)

    def run(self):
        self.root.mainloop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ChromaPeelApp().run()


if __name__ == "__main__":
    main()
