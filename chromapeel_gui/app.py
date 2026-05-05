from __future__ import annotations

import logging
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, simpledialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

import imageAlpha
from imageAlpha import __version__
from clipboard_utils import copy_image_to_clipboard

from . import ALPHA_DIR, BASE_DIR, _open_path, _reveal_path
from .dialogs import GridSplitDialog, ManualCropDialog
from .widgets import ThumbnailView

logger = logging.getLogger(__name__)

DEFAULT_TARGET_COLOR = (255, 37, 255)
DEFAULT_TOLERANCE = 20
DEFAULT_FEATHER = 100
DEFAULT_DECONTAMINATE = True
DEFAULT_EDGE_EROSION = 1
DEFAULT_AUTO_DETECT_BG = False
DEFAULT_AUTO_TRIM = False
DEFAULT_TRIM_PADDING = 0


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
        self.auto_trim = tk.BooleanVar(value=DEFAULT_AUTO_TRIM)
        self.trim_padding = tk.IntVar(value=DEFAULT_TRIM_PADDING)

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

        trim_row = ttk.Frame(parent)
        trim_row.pack(fill="x", pady=3)
        ttk.Label(trim_row, text="자동 트림:", width=14).pack(side="left")
        ttk.Checkbutton(trim_row, text="투명 외곽 자동 자르기", variable=self.auto_trim).pack(side="left", padx=4)
        ttk.Label(trim_row, text="Padding:").pack(side="left", padx=(16, 4))
        ttk.Spinbox(trim_row, from_=0, to=200, textvariable=self.trim_padding, width=5).pack(side="left")

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
        self.auto_trim.set(DEFAULT_AUTO_TRIM)
        self.trim_padding.set(DEFAULT_TRIM_PADDING)
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
            "auto_trim": bool(self.auto_trim.get()),
            "trim_padding": int(self.trim_padding.get()),
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
