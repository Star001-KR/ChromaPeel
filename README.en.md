# ChromaPeel

[한국어](README.md) | **[English](README.en.md)**

[![Test](https://github.com/Star001-KR/ChromaPeel/actions/workflows/test.yml/badge.svg)](https://github.com/Star001-KR/ChromaPeel/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A batch tool that makes a specific background color (chroma key) transparent in PNG images. It also cleanly removes color fringes on anti-aliased edges.

## Example

Result of processing a sprite sheet with a magenta `(255, 37, 255)` background.

| Before (input) | After (output) |
|:---:|:---:|
| <img src="docs/before.png" width="400"/> | <img src="docs/after.png" width="400"/> |
| Magenta background | Transparent background + fringe removed |

> The combination of Feather gradient + Color Decontamination + Edge Erosion cleanly handles even anti-aliased edges.

## Features

- **Desktop app (Win/Mac/Linux)** + **Web app (mobile / desktop browser)** — pick whichever fits the workflow
- **Drag-and-drop GUI** — drag PNGs into the window to register them, click the button to convert, then drag the result thumbnails out to Explorer
- **Clipboard image input** — paste images straight from the clipboard with `Ctrl/Cmd+V`, the "📋 Paste" button, or the right-click menu (CLI exposes a `--from-clipboard` flag; the web build uses a global `paste` listener plus an explicit Paste button)
- **Thumbnail interactions** — double-click to open in the default viewer; right-click for copy image to clipboard / copy path / reveal in Explorer / **(output) rename** / (input) remove
- **Batch progress bar** — tracks N/M progress during multi-file conversion
- **Background auto-detection (optional)** — one checkbox detects the background color from each image's border, so batches with mixed backgrounds work in a single pass
- Converts a target color to alpha (chroma key removal)
- **Feather gradient** — soft fade on edge pixels
- **Color Decontamination** — removes background-color tint from semi-transparent pixels
- **Edge Erosion** — fully removes residual fringe
- **Auto-trim (optional)** — automatically crops the transparent outer area of the result via the alpha bbox (with optional padding)
- **Continue on partial failure** — a single corrupt input no longer aborts the rest of the batch
- Batch folder processing (CLI mode)
- **Grid Split** — slice a sprite sheet into an N×M grid or fixed-size cells, saved as multiple PNGs (an independent tool, separate from chroma removal)

## Requirements

- Python 3.10+
- Pillow, numpy, tkinterdnd2
- (Linux only) `xclip` (X11) or `wl-clipboard` (Wayland) for image clipboard copy

## Installation

**Windows**: double-click or run `setup.bat`

```bat
setup.bat
```

**macOS / Linux**: run `setup.sh` from a terminal

```bash
./setup.sh
```

It automatically:

1. Creates a `.venv` virtual environment (if missing)
2. Upgrades pip and installs dependencies
3. Creates `base/` and `alpha/` folders

**Developer install (pip editable)**: to run the test suite or use the `chromapeel` / `chromapeel-cli` console scripts, run:

```bash
pip install -e ".[dev]"
```

## Usage

### GUI mode (recommended)

Run `run.bat` (Windows) or `./run.sh` (macOS / Linux) to launch the GUI.

1. Drag PNG files into the left **input panel**.
2. Click the **[Convert]** button in the middle.
3. Drag the thumbnails that appear in the right **result panel** out to Explorer / desktop to take them.

**Thumbnail actions**: double-click to open in your default image viewer; right-click for a menu with copy image to clipboard · copy file path · reveal in Explorer · **(output panel) Rename...** · (input panel) remove this input. Rename auto-appends `.png` and rejects characters that are illegal on Windows.

**Clipboard input**: register an image copied from a screenshot tool / image editor straight into the input panel via any of three triggers:

- Shortcut `Ctrl+V` (Win/Linux) / `Cmd+V` (macOS)
- The **"📋 Paste"** button in the input panel's button row
- The input-panel right-click menu **"📋 Paste from clipboard"**

Pasted images are saved as `base/clipboard_YYYYMMDD_HHMMSS.png`. The same three triggers work inside the Grid Split and Manual Crop modals. If the clipboard does not hold an image, the status bar (main window) or an info dialog (modals) reports it.

Expanding the "▸ Advanced Settings" toggle lets you adjust target color, tolerance, feather, edge erosion, decontaminate, and **auto-trim / padding** from the GUI. Enable the **"Auto-detect"** checkbox to skip manual color selection — the background color is extracted from each image's border instead. Enable **"Auto-trim"** to crop the result to the alpha bbox (with optional padding). Use "Reset to Defaults" to restore factory values at any time.

> Internally, inputs are staged in `base/` and outputs are saved to `alpha/`. The "Open Result Folder" button opens `alpha/` in Explorer.

### Web / Mobile mode

The static web build under `web/` runs in any modern browser with no install.

- **Hosted** — pushes to `main` automatically deploy to GitHub Pages at `https://star001-kr.github.io/ChromaPeel/`. Enable *Pages → Source: GitHub Actions* once in repository settings to activate it.
- **Local** — serve the `web/` folder with any static server, e.g. `python3 -m http.server -d web 8000`, then open `http://localhost:8000`.
- **Mobile** — pick an image from your camera roll, tune the sliders with live preview, then tap **Save / Share** to push the transparent PNG to Photos, a chat app, etc.
- **Clipboard input** — `Ctrl/Cmd+V` anywhere on the page (a global `paste` listener) or the **"📋 Paste"** button in the action row will use the clipboard image as the input for the active mode (Chroma Remove / Grid Split / Crop). The button calls `navigator.clipboard.read()` so the browser may show a permission prompt; some mobile browsers only support the paste event or do not support the Clipboard API at all, so it is best-effort (failures surface in the status area).
- **Output filename** — auto-populates as `{stem}_alpha`; freely editable just before save.
- **Image size cap** — images above ~16 MP (≈ 4096×4096) are rejected to protect mobile memory.

The web version targets single-image editing, and all processing runs locally in the browser — the image is never uploaded.

### CLI mode

1. Put the PNG images to process into the `base/` folder.
2. Run the script:

```bash
# Windows
.venv\Scripts\python.exe imageAlpha.py

# macOS / Linux
.venv/bin/python imageAlpha.py
```

3. Find the results in the `alpha/` folder.

CLI flags:

| Flag | Description |
|------|-------------|
| `--auto-trim` | Crop the transparent outer area using the alpha bbox just before saving |
| `--trim-padding N` | Extra pixels added to each side of the `--auto-trim` bbox (default 0) |
| `--from-clipboard` | Save the clipboard image as `base/clipboard_YYYYMMDD_HHMMSS.png` and process only that file (other files in `base/` are ignored) |

## Grid Split

A standalone tool for slicing a single sprite sheet into multiple smaller PNGs. It runs as its own mode, independent from chroma removal, and accepts both RGBA and RGB inputs (alpha is preserved on output).

### Two input modes

1. **Rows × Cols mode** — specify the number of rows and columns and the image is split evenly. Integer division is used, so any leftover pixels at the last row/column are clipped (cropped and ignored).
2. **Cell W × H mode** — specify the cell width and height in pixels and the image is sliced from the top-left, cell by cell. When the image size is not a clean multiple, the trailing row/column is discarded; the GUI and web UI display a "last X×Y px clipped" notice so the loss is visible.

### Output filename convention

- Pattern: `{stem}_r{row}c{col}.png` (row/col numbers are 0-indexed)
- Output location: an `alpha/{stem}_split/` subfolder is created automatically.
- **Zero-pad width** is sized to the digit count of `max(rows, cols)`:
  - `max(rows, cols) < 10` → 1 digit, e.g. `cat_r0c0.png`
  - `10 <= max(rows, cols) < 100` → 2 digits, e.g. `cat_r03c12.png`
  - `max(rows, cols) >= 100` → 3 digits, e.g. `cat_r042c128.png`

### CLI (`chromapeel-split`)

After `pip install -e ".[dev]"`, the `chromapeel-split` console script is on your PATH.

```bash
# Rows × Cols mode: split evenly into 4 rows × 4 columns
chromapeel-split input.png --rows 4 --cols 4

# Cell W × H mode: slice top-left into 64×64 px cells
chromapeel-split input.png --cell-w 64 --cell-h 64

# Custom output folder: my_output/{stem}_split/{stem}_r0c0.png ...
chromapeel-split input.png -o my_output/ --rows 2 --cols 3

# Use the clipboard image as input (input_path and --from-clipboard are mutually exclusive — exactly one is required)
chromapeel-split --from-clipboard --rows 2 --cols 2
```

### Desktop GUI

Click the **[Grid Split]** button at the top of the main window to open a dedicated modal. Pick an image, choose the mode (Rows × Cols / Cell W × H), enter the numbers, and the preview overlays a grid. Hit **[Split]** and the result folder (`alpha/{stem}_split/`) opens automatically.

### Web / Mobile

The web build's main screen exposes a **mode switch** between "Chroma Remove" and "Grid Split". In Grid Split mode you upload an image, choose the mode and values, confirm the preview grid, click **[Split]**, and receive each tile as a thumbnail you can download individually — or use **[Download All as ZIP]** to grab everything at once.

## Parameters

Adjust via the advanced settings toggle in GUI mode, or via the `process_folder()` call at the bottom of `imageAlpha.py` in CLI mode.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `input_dir` | Input folder | `"base"` |
| `output_dir` | Output folder | `"alpha"` |
| `target_color` | Color to remove (R, G, B). Pass `None` to auto-detect the most common color on each image's border | `(255, 37, 255)` (magenta) |
| `tolerance` | Tolerance for full transparency | `20` |
| `feather` | Semi-transparent fade range | `100` |
| `decontaminate` | Remove background-color tint | `True` |
| `edge_erosion` | Number of erosion pixels on edges | `1` |
| `auto_trim` | Crop transparent edges via alpha bbox before saving (skipped with a warning if the whole image is transparent) | `False` |
| `trim_padding` | Extra pixels added to each side of the `auto_trim` bbox | `0` |

## How it works

1. **(Optional) Auto-detect** — if `target_color=None`, picks the most frequent RGB on the image's 1-pixel border as the target
2. **Distance calculation** — L∞ distance (per-channel max difference) between each pixel color and the target color
3. **Full transparency** — sets alpha to 0 where distance ≤ `tolerance`
4. **Feather fade** — sets alpha as a linear gradient across distance `tolerance`..`tolerance+feather`
5. **Decontamination** — removes target-color component from semi-transparent pixels by inverting the blend formula
   - `observed = t·target + (1-t)·original` → `original = (observed - t·target) / (1-t)`
6. **Edge Erosion** — erodes N pixels of opaque area adjacent to transparent regions using a 3×3 min filter
7. **(Optional) Auto-trim** — when `auto_trim=True`, crops the result to the bbox of pixels with alpha > 0. If the image is fully transparent, trim is skipped with a warning log (the original is saved as-is)

## Manual Crop

An **independent tool** that crops a single rectangular region out of an image. It runs independently of chroma-key removal; results are saved as `alpha/{stem}_crop.png`.

### CLI

The `chromapeel-crop` console script takes the four box coordinates as a comma-separated list of integers.

```bash
chromapeel-crop INPUT --crop X,Y,W,H

# Use the clipboard image as input (INPUT and --from-clipboard are mutually exclusive — exactly one is required)
chromapeel-crop --from-clipboard --crop 0,0,128,128
```

- `X,Y`: top-left pixel coordinate of the box (image origin is `(0, 0)`)
- `W,H`: box width / height in pixels
- Boxes extending past the image are clamped to the image bounds; `W` or `H` ≤ 0 exits with an error.

### Desktop GUI

**Right-click an input thumbnail → "Crop..."** to open the crop modal. From the modal you can:

- Drag a new box, or grab an existing box and drag to move it
- Resize via **8 handles** (4 corners + 4 edges)
- Type values directly into the `X` / `Y` / `W` / `H` fields for precise adjustment

Confirming the modal saves the result to `alpha/{stem}_crop.png`.

### Web

Switch to **"Crop"** in the top mode selector to enable the crop canvas. Draw a box with a mouse or touch drag, resize via the 8 handles, then tap **[Crop]** to save the resulting PNG.

### Multi-region

Only single-region cropping is supported today; multi-region selection is left as future work.

> Automated tests only cover the core crop function; GUI / web interactions (drag, handles, touch) are outside the automated test scope and are verified manually.

## Project structure

```
ChromaPeel/
├── .venv/                   # Python virtual environment (git-ignored)
├── base/                    # Input folder (auto-staged on GUI drop / paste)
├── alpha/                   # Output folder
├── imageAlpha.py            # Chroma-key core + chromapeel-cli entry point
├── grid_split.py            # Grid-split core + chromapeel-split entry point
├── manual_crop.py           # Manual-crop core + chromapeel-crop entry point
├── clipboard_utils.py       # Clipboard read/copy/staging (Win ctypes / mac osascript / Linux xclip·wl-copy)
├── chromapeel_gui/          # Desktop Tkinter GUI package
│   ├── __init__.py          #   Package constants (BASE_DIR, ALPHA_DIR) + platform helpers
│   ├── __main__.py          #   `python -m chromapeel_gui` entry point
│   ├── app.py               #   Main window / conversion workflow
│   ├── dialogs/             #   Grid-split / manual-crop modal package
│   │   ├── __init__.py      #     re-export (preserves external import path)
│   │   ├── _clipboard.py    #     ClipboardPasteMixin (paste triggers + tempdir isolation)
│   │   ├── grid_split.py    #     GridSplitDialog
│   │   └── manual_crop.py   #     ManualCropDialog
│   └── widgets.py           #   Thumbnail grid widget
├── pyproject.toml           # PEP 621 metadata (registers 4 console scripts)
├── requirements.txt         # Dependency list for the auto-setup scripts
├── setup.bat / setup.sh     # Auto-install scripts (Windows / macOS·Linux)
├── run.bat / run.sh         # One-click GUI launchers (Windows / macOS·Linux)
├── web/                     # Mobile / browser web build (vanilla JS ESM + Canvas)
│   ├── index.html
│   ├── styles.css
│   ├── package.json         #   {"type": "module"} — node treats web/*.js as ESM
│   ├── main.js              #   Entry point — DOMContentLoaded → init*()
│   ├── algorithm.js         #   Chroma-key algorithm core (Python parity)
│   ├── chroma.js            #   Chroma mode (loadFile, saveOrShare, ...)
│   ├── grid.js              #   Grid-split mode (drawGridPreview, runGridSplit, ...)
│   ├── crop.js              #   Manual-crop mode (drag/resize, applyCrop, ...)
│   ├── clipboard.js         #   Global paste + 📋 button routing
│   ├── mode.js              #   Tab switch (chroma / grid / crop)
│   ├── zip.js               #   Store-mode ZIP builder
│   ├── state.js             #   Shared chroma + grid state (singleton)
│   ├── dom.js               #   $ helper · setStatus / setCropStatus
│   └── util.js              #   Filename sanitisation
├── tests/                   # pytest + JS parity + Playwright web tests
│   ├── conftest.py
│   ├── test_image_alpha.py
│   ├── test_grid_split.py
│   ├── test_manual_crop.py
│   ├── test_clipboard_utils.py
│   ├── test_gui_import.py
│   ├── test_js_parity.py
│   ├── js_parity_runner.mjs #   Python↔JS byte-parity runner (imports algorithm.js)
│   ├── _web_server.js       #   Ephemeral http server for smoke / e2e (ESM blocked under file://)
│   ├── web_smoke.js         #   Web boot smoke test (Playwright)
│   └── web_e2e.js           #   Web golden-path e2e (Playwright)
├── .github/workflows/
│   ├── test.yml             #   3 OS × 3 Python matrix + web e2e
│   └── deploy-web.yml       #   GitHub Pages auto-deploy
├── CHANGELOG.md
├── LICENSE
└── .gitignore
```

## Tuning guide

| Symptom | Fix |
|---------|-----|
| Background-color fringe remains on edges | Increase `edge_erosion` to 2+, or increase `feather` |
| Thin features (grass blades, stems) disappear | Set `edge_erosion=0` to disable erosion |
| Sprite's own colors shift | Set `decontaminate=False` to disable decontamination |
| Background isn't fully removed | Increase `tolerance` |

## Tests

Algorithm unit tests plus a byte-for-byte JS↔Python parity test live under `tests/`.

```bash
pip install -e ".[dev]"   # once, includes pytest
pytest -v
```

The JS parity test runs only when `node` is available; otherwise it's auto-skipped. Every push and pull request is verified by GitHub Actions across Ubuntu / Windows / macOS × Python 3.10 / 3.12 / 3.13.
