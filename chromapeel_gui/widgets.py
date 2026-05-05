from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES

logger = logging.getLogger(__name__)

THUMB_SIZE = 96


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
