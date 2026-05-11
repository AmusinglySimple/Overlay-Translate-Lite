# Overlay Translate Lite

A lightweight version of Overlay Translate — screen OCR and translation with overlay display.

[!IMPORTANT]
Special thanks to my friend and collaborator Kappuchuu for his invaluable help with testing and quality assurance during the development of this software.

## What's Included

- **Screen Capture** (F1) — Capture the overlay area and translate text
- **Live Translation** (F3) — Continuous capture with change detection
- **Snipping Tool** (F4) — Select a custom area to capture
- **Overlay Display** — Resizable, semi-transparent overlay with click-through (F2)
- **Translation Image Viewer** — Zoom, annotations, font/color customization, export
- **Pop-out Live Translation** — Floating window with pin, opacity, and font controls
- **5 Themes** — Default Neon, Dark Cyber, Standard Dark, Standard Light, Ocean Depth
- **Theme Editor** — Full color customization with live preview
- **Multi-monitor Support** — Capture works correctly across multiple displays
- **Tray Icon** — Minimize to system tray
- **PaddleOCR** — Offline OCR (English, Chinese, Japanese, Korean, and more)
- **Argos Translate** — Offline translation via local Flask/Waitress server
- **Internationalization** — UI translated via Qt i18n

## What's NOT Included (vs Full Version)

- AI translation providers (OpenAI, Anthropic, Gemini, Ollama, LM Studio)
- AI Chat window
- API key management / keyring
- Onboarding wizard
- Window presets / Window manager
- Notification system / Toast notifications
- Operation history / Undo-Redo
- Resource monitor / Memory profiler
- Performance metrics
- Centralized Settings dialog
- Theme scheduling / Auto-switch
- Theme import/export/preview

## Quick Start

1. Install Python 3.9+ and create a virtual environment
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   python main.py
   ```
   Or on Windows, double-click `RUN.bat`.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F1  | Capture and translate |
| F2  | Toggle click-through overlay |
| F3  | Toggle live translation |
| F4  | Snipping tool |

## Requirements

- Python >= 3.9
- PySide6, PaddleOCR, Argos Translate, Flask, Waitress
- See `requirements.txt` for full list
