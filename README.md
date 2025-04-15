# Overlay Translate

Overlay Translate is an offline tool to capture on-screen text, translate it live, and display it in a non-intrusive overlay. Ideal for translating content in videos, games, software, or documents without needing an internet connection.

---

## Features

- ✨ Live translations from a floating region
- 📸 Static screen capture for instant translation
- 🔍 Offline OCR with PaddleOCR
- ⚖ Offline translations using LibreTranslate
- 🔧 Optional enhancement of translations using local LLMs
- 🌐 Multilingual support with auto-detection
- ✅ Font, opacity, and contrast customization
- ✂️ Built-in snipping tool support

---

## System Requirements

- Windows 10/11
- Python 3.8 
- No GPU required (recommended for faster OCR)
- Minimum 4 GB RAM (8 GB recommended)

---

## Installation

1. Clone this repository or copy the files into a folder.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Make sure you have the following:
   - A GGUF LLM model inside the `models/` folder (e.g. `Phi-3.1-mini-128k-instruct-Q4_K_M.gguf`)
   - LibreTranslate installed and running on `http://127.0.0.1:5000`

4. Run the application:

```bash
python main.py
```

---

## Quick Usage

- `F1`: Capture screen and translate
- `F2`: Toggle click-through on the floating region
- `F4`: Activate Snipping Tool
- `F5`: Toggle high-contrast theme
- `F6`: Open local LibreTranslate server
- `F8`: Toggle translation enhancement (requires LLM)

Language settings can be configured in the *Settings* menu.

---

## Folder Structure

```
OverlayTranslate/
├── db/ (generated at runtime)
├── assets/
│   ├── icon.png
├── window_positions.json (generated at runtime)
├── Support/ (generated at runtime on Desktop)
└── your_script.py
```

---

## requirements.txt

```
PySide6
paddlepaddle
paddleocr
Pillow
opencv-python
langdetect
requests
libretranslate
numpy
keyring

```

---

## Additional Notes

- Captures and translations are stored temporarily in the `Support` folder on your desktop.
- The AI API is optional, but it can improve translation quality based on context.
- It is strongly recommended to run LibreTranslate locally for full offline functionality.

---

## License

This project is for personal use only. Do not redistribute without permission from the original author.

---

## Contact

Andrea - Master Hobby

