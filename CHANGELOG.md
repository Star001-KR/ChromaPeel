# Changelog

All notable changes to ChromaPeel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pyproject.toml` for PEP 621 packaging with `chromapeel` (GUI) and `chromapeel-cli` console scripts
- `__version__` exposed from `imageAlpha`; shown in the GUI window title
- GitHub Actions workflow running pytest on Python 3.8 / 3.10 / 3.12 across Ubuntu, Windows, macOS
- MIT `LICENSE` file
- This changelog

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

[Unreleased]: https://github.com/Star001-KR/ChromaPeel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Star001-KR/ChromaPeel/releases/tag/v0.1.0
