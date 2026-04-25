# ChromaPeel

[한국어](README.md) | **[English](README.en.md)**

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
- **Thumbnail interactions** — double-click to open in the default viewer; right-click for copy image to clipboard / copy path / reveal in Explorer / (input only) remove
- **Background auto-detection (optional)** — one checkbox detects the background color from each image's border, so batches with mixed backgrounds work in a single pass
- Converts a target color to alpha (chroma key removal)
- **Feather gradient** — soft fade on edge pixels
- **Color Decontamination** — removes background-color tint from semi-transparent pixels
- **Edge Erosion** — fully removes residual fringe
- Batch folder processing (CLI mode)

## Requirements

- Python 3.8+
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

## Usage

### GUI mode (recommended)

Run `run.bat` (Windows) or `./run.sh` (macOS / Linux) to launch the GUI.

1. Drag PNG files into the left **input panel**.
2. Click the **[Convert]** button in the middle.
3. Drag the thumbnails that appear in the right **result panel** out to Explorer / desktop to take them.

**Thumbnail actions**: double-click to open in your default image viewer; right-click for a menu with copy image to clipboard · copy file path · reveal in Explorer · (input panel only) remove this input.

Expanding the "▸ Advanced Settings" toggle lets you adjust target color, tolerance, feather, edge erosion, and decontaminate from the GUI. Enable the **"Auto-detect"** checkbox to skip manual color selection — the background color is extracted from each image's border instead. Use "Reset to Defaults" to restore factory values at any time.

> Internally, inputs are staged in `base/` and outputs are saved to `alpha/`. The "Open Result Folder" button opens `alpha/` in Explorer.

### Web / Mobile mode

The static web build under `web/` runs in any modern browser with no install.

- **Hosted** — pushes to `main` automatically deploy to GitHub Pages at `https://star001-kr.github.io/ChromaPeel/`. Enable *Pages → Source: GitHub Actions* once in repository settings to activate it.
- **Local** — serve the `web/` folder with any static server, e.g. `python3 -m http.server -d web 8000`, then open `http://localhost:8000`.
- **Mobile** — pick an image from your camera roll, tune the sliders with live preview, then tap **Save / Share** to push the transparent PNG to Photos, a chat app, etc.

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

## How it works

1. **(Optional) Auto-detect** — if `target_color=None`, picks the most frequent RGB on the image's 1-pixel border as the target
2. **Distance calculation** — L∞ distance (per-channel max difference) between each pixel color and the target color
3. **Full transparency** — sets alpha to 0 where distance ≤ `tolerance`
4. **Feather fade** — sets alpha as a linear gradient across distance `tolerance`..`tolerance+feather`
5. **Decontamination** — removes target-color component from semi-transparent pixels by inverting the blend formula
   - `observed = t·target + (1-t)·original` → `original = (observed - t·target) / (1-t)`
6. **Edge Erosion** — erodes N pixels of opaque area adjacent to transparent regions using a 3×3 min filter

## Project structure

```
ChromaPeel/
├── .venv/              # Python virtual environment (git-ignored)
├── base/               # Input folder (auto-staged on GUI drop)
├── alpha/              # Output folder
├── chromapeel_gui.py   # GUI entry (Tkinter + tkinterdnd2)
├── clipboard_utils.py  # Clipboard image copy (Win ctypes / mac osascript / Linux xclip·wl-copy)
├── imageAlpha.py       # Processing logic (also runs in CLI mode)
├── requirements.txt    # Python dependencies
├── setup.bat / setup.sh  # Auto-install scripts (Windows / macOS·Linux)
├── run.bat / run.sh      # One-click GUI launchers (Windows / macOS·Linux)
├── web/                  # Mobile / browser web build (vanilla JS + Canvas)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── .github/workflows/deploy-web.yml  # GitHub Pages auto-deploy
└── .gitignore
```

## Tuning guide

| Symptom | Fix |
|---------|-----|
| Background-color fringe remains on edges | Increase `edge_erosion` to 2+, or increase `feather` |
| Thin features (grass blades, stems) disappear | Set `edge_erosion=0` to disable erosion |
| Sprite's own colors shift | Set `decontaminate=False` to disable decontamination |
| Background isn't fully removed | Increase `tolerance` |
