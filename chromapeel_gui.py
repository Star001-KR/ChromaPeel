from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import imageAlpha
from imageAlpha import __version__
from clipboard_utils import copy_image_to_clipboard
from grid_split import split_image_grid

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
        self.btn_grid_split = ttk.Button(btnrow, text="격자 분할...", command=self._open_grid_split_dialog)
        self.btn_grid_split.pack(side="left", padx=(8, 0))
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

    def _open_grid_split_dialog(self):
        if self.processing:
            self._set_status("변환 중에는 격자 분할을 열 수 없습니다")
            return
        GridSplitDialog(self.root)

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
