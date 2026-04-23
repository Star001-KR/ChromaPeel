from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import imageAlpha

DEFAULT_TARGET_COLOR = (255, 37, 255)
DEFAULT_TOLERANCE = 20
DEFAULT_FEATHER = 100
DEFAULT_DECONTAMINATE = True
DEFAULT_EDGE_EROSION = 1

THUMB_SIZE = 96

BASE_DIR = Path("base")
ALPHA_DIR = Path("alpha")


class ThumbnailView(ttk.Frame):
    """Scrollable grid of image thumbnails. Optional drag-out support."""

    def __init__(self, parent, drag_out: bool = False, columns: int = 4, **kwargs):
        super().__init__(parent, **kwargs)
        self.drag_out = drag_out
        self.columns = columns

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


class ChromaPeelApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("ChromaPeel")
        self.root.geometry("940x680")
        self.root.minsize(780, 580)

        BASE_DIR.mkdir(exist_ok=True)
        ALPHA_DIR.mkdir(exist_ok=True)

        self.target_color: tuple[int, int, int] = DEFAULT_TARGET_COLOR
        self.tolerance = tk.IntVar(value=DEFAULT_TOLERANCE)
        self.feather = tk.IntVar(value=DEFAULT_FEATHER)
        self.decontaminate = tk.BooleanVar(value=DEFAULT_DECONTAMINATE)
        self.edge_erosion = tk.IntVar(value=DEFAULT_EDGE_EROSION)

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

        input_lf = ttk.Labelframe(panels, text=" 입력 — PNG를 여기로 드래그 ")
        input_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.input_view = ThumbnailView(input_lf, drag_out=False)
        self.input_view.pack(fill="both", expand=True, padx=4, pady=4)
        self.input_view.show_placeholder("여기에 PNG 파일을 드래그하세요")
        for w in [input_lf, self.input_view, *self.input_view.drop_targets()]:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", self._on_drop)

        output_lf = ttk.Labelframe(panels, text=" 결과 — 썸네일을 탐색기로 드래그하여 가져가기 ")
        output_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.output_view = ThumbnailView(output_lf, drag_out=True)
        self.output_view.pack(fill="both", expand=True, padx=4, pady=4)

        btnrow = ttk.Frame(root, padding=(10, 4))
        btnrow.pack(fill="x")
        self.btn_clear = ttk.Button(btnrow, text="입력 비우기", command=self._clear_inputs)
        self.btn_clear.pack(side="left")
        self.btn_open_out = ttk.Button(btnrow, text="결과 폴더 열기", command=self._open_alpha_dir)
        self.btn_open_out.pack(side="right")
        self.btn_convert = ttk.Button(btnrow, text="   변환   ", command=self._start_conversion)
        self.btn_convert.pack()

        toggle_row = ttk.Frame(root, padding=(10, 2))
        toggle_row.pack(fill="x")
        self.btn_toggle = ttk.Button(toggle_row, text="▸ 고급 설정", command=self._toggle_advanced, width=14)
        self.btn_toggle.pack(side="left")

        self.advanced = ttk.Labelframe(root, text=" 파라미터 ", padding=10)
        self._build_advanced(self.advanced)

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
        ttk.Button(color_row, text="색상 선택", command=self._pick_color).pack(side="left", padx=4)

        tol_row = ttk.Frame(parent)
        tol_row.pack(fill="x", pady=3)
        ttk.Label(tol_row, text="Tolerance:", width=14).pack(side="left")
        ttk.Scale(tol_row, from_=0, to=255, variable=self.tolerance,
                  command=lambda v: self.tolerance.set(int(float(v)))).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(tol_row, textvariable=self.tolerance, width=4).pack(side="left")

        fea_row = ttk.Frame(parent)
        fea_row.pack(fill="x", pady=3)
        ttk.Label(fea_row, text="Feather:", width=14).pack(side="left")
        ttk.Scale(fea_row, from_=0, to=300, variable=self.feather,
                  command=lambda v: self.feather.set(int(float(v)))).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(fea_row, textvariable=self.feather, width=4).pack(side="left")

        edge_row = ttk.Frame(parent)
        edge_row.pack(fill="x", pady=3)
        ttk.Label(edge_row, text="Edge Erosion:", width=14).pack(side="left")
        ttk.Spinbox(edge_row, from_=0, to=10, textvariable=self.edge_erosion, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(edge_row, text="Decontaminate", variable=self.decontaminate).pack(side="left", padx=16)
        ttk.Button(edge_row, text="기본값 복원", command=self._reset_defaults).pack(side="right")

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

    def _reset_defaults(self):
        self.target_color = DEFAULT_TARGET_COLOR
        self.tolerance.set(DEFAULT_TOLERANCE)
        self.feather.set(DEFAULT_FEATHER)
        self.decontaminate.set(DEFAULT_DECONTAMINATE)
        self.edge_erosion.set(DEFAULT_EDGE_EROSION)
        self.color_swatch.configure(bg=self._rgb_to_hex(self.target_color))
        self.color_label.configure(text=str(self.target_color))
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

    def _refresh_inputs_from_disk(self):
        files = self._list_pngs(BASE_DIR)
        self.input_view.clear()
        if not files:
            self.input_view.show_placeholder("여기에 PNG 파일을 드래그하세요")
        else:
            for f in files:
                self.input_view.add_thumbnail(f)

    def _refresh_outputs_from_disk(self):
        files = self._list_pngs(ALPHA_DIR)
        self.output_view.clear()
        if not files:
            self.output_view.show_placeholder("변환 후 여기에 결과가 표시됩니다")
        else:
            for f in files:
                self.output_view.add_thumbnail(f)

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
                pass
        self._refresh_inputs_from_disk()
        self._set_status("입력을 비웠습니다")

    def _open_alpha_dir(self):
        try:
            os.startfile(str(ALPHA_DIR.resolve()))
        except AttributeError:
            messagebox.showinfo("안내", f"결과 폴더: {ALPHA_DIR.resolve()}")
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
        self._set_status(f"0/{len(inputs)} 변환 시작...")

        params = {
            "target_color": self.target_color,
            "tolerance": int(self.tolerance.get()),
            "feather": int(self.feather.get()),
            "decontaminate": bool(self.decontaminate.get()),
            "edge_erosion": int(self.edge_erosion.get()),
        }

        threading.Thread(target=self._run_process, args=(params,), daemon=True).start()

    def _run_process(self, params):
        first_done = [False]

        def cb(i, total, in_path, out_path):
            def ui_update():
                if not first_done[0]:
                    self.output_view.clear()
                    first_done[0] = True
                self.output_view.add_thumbnail(Path(out_path))
                self._set_status(f"{i}/{total} 완료 — {Path(in_path).name}")
            self.root.after(0, ui_update)

        try:
            imageAlpha.process_folder(
                input_dir=str(BASE_DIR),
                output_dir=str(ALPHA_DIR),
                progress_callback=cb,
                **params,
            )
            self.root.after(0, lambda: self._on_done(None))
        except Exception as e:
            err = e
            self.root.after(0, lambda: self._on_done(err))

    def _on_done(self, error: Exception | None):
        self.processing = False
        self.btn_convert.configure(state="normal", text="   변환   ")
        self.btn_clear.configure(state="normal")
        if error is not None:
            self._set_status(f"오류: {error}")
            messagebox.showerror("변환 실패", str(error))
            self._refresh_outputs_from_disk()
        else:
            self._set_status("변환 완료 — 결과 썸네일을 탐색기로 드래그하세요")

    def _set_status(self, text: str):
        self.status.set(text)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ChromaPeelApp().run()
