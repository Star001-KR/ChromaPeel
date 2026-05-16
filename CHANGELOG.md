# Changelog

All notable changes to ChromaPeel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **다색 chroma key (Phase 1)** — `remove_color` / `process_folder` 에 `target_colors:
  list[RGB]` 파라미터 추가. 한 이미지 내 여러 배경색을 동시에 제거하며 (그라데이션
  마젠타·이중 배경 등), feather 구간의 decontaminate 는 픽셀별로 가장 가까운 타겟
  색상을 기준으로 적용된다. 기존 단일색 `target_color` API 는 완전한 역호환을 유지
  (둘 다 지정 시 `ValueError`).
- `detect_background_colors()` — 동적 k 자동 다색 감지. 테두리 픽셀의 빈도
  내림차순으로 색상을 모으되 `min_ratio` (기본 5%) 미만의 색은 제외하고, 최빈색
  1개는 비율과 무관하게 반드시 포함. 정렬은 (count desc, R asc, G asc, B asc)
  로 결정론적 tie-break — JS 포트와 byte-for-byte 일치.
- `remove_color` / `process_folder` 의 `auto_detect` 플래그 — 색을 명시하지 않은
  자동 감지에서 다색 감지(`detect_background_colors`)는 `auto_detect=True` (CLI
  `--auto`, GUI "자동 감지") 로 명시 opt-in 해야 적용된다. 인자를 모두 생략한 기본
  호출은 0.2.0 처럼 테두리 최빈색 1개만 단일 감지하므로, 기존 라이브러리 호출자의
  동작이 보존된다.
- CLI `--target-color "R,G,B"` (반복 지정 가능) + `--auto` 플래그.
- Tkinter GUI 색상 영역에 다색 칩 리스트 + "+ 색상 추가" / 행별 "✕" 삭제 버튼.
- Web 다색 UI — `colorsContainer` 가 색 picker 칩을 동적으로 렌더링하며,
  `state.targetColors` 배열로 일원화.

### Removed (BREAKING)
- Drop Python 3.8 and 3.9 support. Floor is now `>=3.10` (both 3.8 and 3.9
  are EOL: 3.8 in 2024-10, 3.9 in 2025-10). CI matrix migrated from
  `3.8 / 3.10 / 3.12` to `3.10 / 3.12 / 3.13`.

### Fixed
- `detect_background_colors()` 의 테두리 픽셀 수집에서 코너 4 개가 두 번 집계되던
  버그 수정 (Python + Web JS 동기 fix). 작은 이미지에서 자동 감지 비율 계산이 약간
  부정확했던 케이스가 사라진다. Python·JS parity 는 유지.
- 웹의 "자동 감지" 토글이 사용자가 수동으로 고른 색 목록을 영구 손실시키던 동작
  수정 — ON 직전 목록을 보관해 OFF 토글 시 자동 복원한다.
- `run.sh` now mirrors `run.bat`'s import precheck — `chromapeel_gui` import
  failures (missing dependency, broken package) surface to the user with the
  full traceback and a recovery hint instead of silently exiting. Closes a
  cross-platform parity gap left after the v0.2.0 launcher fix that only
  covered `run.bat`.

### Changed
- Consolidate the three identical `_stage_clipboard_image` CLI helpers
  (`imageAlpha.py`, `grid_split.py`, `manual_crop.py`) into a single
  `clipboard_utils.stage_clipboard_image_or_exit()` so the
  "no traceback / stderr message / exit 1" policy lives in one place. Three
  focused unit tests guard the wrapper.
- Promote the shared CLI / GUI default chroma-key parameters
  (`_CLI_DEFAULT_*` in `imageAlpha.py`, mirrored as `DEFAULT_*` in
  `chromapeel_gui/app.py`) to public `APP_DEFAULT_*` exported from
  `imageAlpha`. The GUI now imports them, removing a 7-constant value
  duplication that previously had to be kept in lockstep manually.
- Drop the unused `__version__ = "0.2.0"` constant from `grid_split.py`. Only
  `imageAlpha.__version__` is consumed (by the GUI window title and the
  `pyproject.toml` dynamic version), so the second copy was stale and
  guaranteed to drift on the next release bump.
- Modernise typing in `imageAlpha.py` and `grid_split.py` to PEP 585 native
  generics (`list[X]`, `tuple[X, Y]`); `from typing import List, Tuple` is
  removed. `Optional` and `Callable` are retained for clarity.
- Split the 879-LOC `chromapeel_gui/dialogs.py` into a `dialogs/` subpackage:
  `_clipboard.py` (the new `ClipboardPasteMixin` consolidating the duplicated
  paste-trigger / tempdir-cleanup boilerplate), `grid_split.py`
  (GridSplitDialog), `manual_crop.py` (ManualCropDialog), and `__init__.py`
  re-exporting the public symbols. External import path is unchanged
  (`from chromapeel_gui.dialogs import GridSplitDialog, ManualCropDialog`
  still works).
- Web frontend modularised. The 1422-LOC `web/app.js` is split into 12 ESM
  modules (`algorithm` · `zip` · `state` · `dom` · `util` · `chroma` · `grid`
  · `crop` · `clipboard` · `mode` · `main`, plus `package.json` declaring
  `{"type": "module"}`). Largest module is now 354 LOC (`crop.js`). All
  cross-module dependencies are unidirectional; `state` is a singleton via
  ESM module identity. `<script>` switched to `type="module"`; entry point
  renamed `app.js` → `main.js`.
- JS parity runner converted to native ESM (`tests/js_parity_runner.js` →
  `.mjs`) and now imports `web/algorithm.js` directly. The 24-line DOM
  shim block is gone — the runner only polyfills `ImageData`.
- Web smoke and e2e tests now serve `web/` over an ephemeral
  `http://127.0.0.1:<port>/` (helper at `tests/_web_server.js`) since
  Chromium blocks ESM under `file://` due to CORS.
- CI `node --check` widened from `web/app.js` to `web/*.js`.

## [0.2.0] - 2026-05-10

### Added
- `pyproject.toml` for PEP 621 packaging with `chromapeel` (GUI) and `chromapeel-cli` console scripts
- `__version__` exposed from `imageAlpha`; shown in the GUI window title
- GitHub Actions workflow running pytest on Python 3.8 / 3.10 / 3.12 across Ubuntu, Windows, macOS
- MIT `LICENSE` file
- This changelog
- `clipboard_utils` unit tests (12 tests): platform dispatch, macOS symlink-based path safety regression, Linux wl-copy/xclip fallback chain, per-tool failure modes
- `logging` instrumentation in `chromapeel_gui` and `imageAlpha` so previously silent failures (thumbnail load, drag-drop parsing, input cleanup, per-file batch failure) are now diagnosable
- Parallel batch processing via `ThreadPoolExecutor`. `process_folder` accepts a new `max_workers` parameter — `None` (default) auto-sizes to `min(os.cpu_count(), file_count)`, `1` preserves the previous deterministic per-file callback order
- Add auto-trim of transparent edges as post-processing option. `process_folder` / `remove_color` accept `auto_trim` and `trim_padding`; CLI exposes `--auto-trim` / `--trim-padding N`; desktop GUI and web build expose matching controls. All-transparent results skip trim with a warning log (the original is preserved). JS↔Python parity covers both on/off cases.
- Grid split tool: slice a sprite sheet into an N×M grid or fixed-size cells as a standalone mode. New `chromapeel-split` console script supports Rows × Cols (`--rows R --cols C`) and Cell W × H (`--cell-w W --cell-h H`). Desktop GUI adds a "Grid Split" button opening a preview modal; the web UI adds a mode switch with thumbnail results and a ZIP download. Tiles are written to `alpha/{stem}_split/{stem}_r{row}c{col}.png` with 0-indexed coordinates and zero-pad width sized to `max(rows, cols)`. Non-divisible cell sizes clip the trailing row/column with a user-facing notice; alpha is preserved for both RGBA and RGB inputs
- Manual crop tool: select a single rectangular region by mouse/touch drag with 8-handle resize, available as `chromapeel-crop` CLI, desktop GUI right-click modal, and web mode. Single region only (multi-region as future work).
- Clipboard image input across all surfaces. New `clipboard_utils.read_image_from_clipboard()` core helper wraps `PIL.ImageGrab.grabclipboard()` and handles the file-list case (Linux / macOS Finder copy). All three CLIs (`chromapeel-cli`, `chromapeel-split`, `chromapeel-crop`) accept `--from-clipboard`; for split/crop the input arg becomes optional and exactly one of `INPUT` or `--from-clipboard` is required, with clipboard images staged via `clipboard_utils.stage_clipboard_image()` (microsecond + uuid suffix collision protection). Desktop GUI exposes three triggers — `Ctrl/Cmd+V` shortcut, "📋 Paste" button, and right-click menu — across the main input panel, the Grid Split modal, and the Manual Crop modal. The web build adds a global `paste` listener plus a "📋 Paste" button (using `navigator.clipboard.read()`) that routes images to the active mode (Chroma Remove / Grid Split / Crop); mobile browsers fall back to best-effort with explicit error messaging when the API is unavailable or permission is denied.

### Changed
- `process_folder` callback `index` now means "Nth completion", which in parallel mode no longer matches submission order. Pass `max_workers=1` to keep the old strict ordering.
- Main GUI clipboard paste now routes through `clipboard_utils.stage_clipboard_image()` so the staging file naming (microsecond + uuid suffix + retry) and the user-facing error wrapping match the CLI and the dialog paths.
- CLI output messages unified to Korean across `chromapeel-cli` / `chromapeel-split` / `chromapeel-crop` (previously a mix of `완료:`, `Saved N files`, and `saved:`).

### Fixed
- `run.bat` / `run.sh` now invoke `python -m chromapeel_gui` instead of the obsolete `chromapeel_gui.py` path that was orphaned by the package split (commit eb29222), which caused Windows `pythonw.exe` to silently fail. Added `chromapeel_gui/__main__.py`, an import precheck in `run.bat` so future module errors surface to the user instead of disappearing, and a `tests/test_gui_import.py` smoke test guarding the entry point.
- `README.md` / `README.en.md` "Project structure" tree now matches the actual layout (package split into `chromapeel_gui/`, three new core modules, additional tests).
- `.gitignore` widened from `.venv/` to `.venv*/` so platform-specific virtualenvs (`.venv-macos/`, `.venv-linux/`, ...) don't show up as untracked.
- `requirements.txt` header comment no longer claims the list is pinned (versions live in `pyproject.toml`; this file is loose by design for the auto-setup scripts).

## [0.1.0] - 2026-04-27

### Added
- Web port for browsers and mobile (vanilla JS + Canvas, GitHub Pages auto-deploy)
- Cross-platform support for macOS and Linux (clipboard, file reveal, launch scripts)
- Progress bar for desktop batch conversion (per-file callback API)
- User-editable result filename for the After thumbnail (right-click → Rename)
- Background auto-detection from each image's 1-pixel border
- Drag-and-drop GUI with input/output thumbnail panels (Tkinter + tkinterdnd2)
- Continue-on-failure behavior so a single corrupt input does not abort the batch
- pytest unit suite plus Python ↔ JS byte-for-byte parity test

### Changed
- Address review priorities 1-8: race condition fixes in param handling,
  cross-platform filename sanitization, case-insensitive rename safety,
  shell metacharacter escaping in macOS clipboard helper, library output
  decoupled from CLI/GUI/web via callback injection

[Unreleased]: https://github.com/Star001-KR/ChromaPeel/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Star001-KR/ChromaPeel/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Star001-KR/ChromaPeel/releases/tag/v0.1.0
