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
- Python 3.9 or higher
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
├── main.py                # Entry point of the application
├── models/                # LLM model folder (GGUF format)
├── Support/               # Temporary captures and translations
├── window_positions.json  # Stores UI state and window geometry
├── requirements.txt       # Python dependencies
└── ...                    # Additional support files
```

---

## requirements.txt

```
PyQt5>=5.15.7
paddleocr>=2.7.0 # Or latest stable version
transformers>=4.30.0
torch>=1.13.0
Pillow>=9.2.0
opencv-python>=4.6.0
langdetect>=1.0.9
requests>=2.28.1
libretranslate>=1.5.3
llama-cpp-python>=0.2.20 # Or latest stable version
```

---

## Additional Notes

- Captures and translations are stored temporarily in the `Support` folder on your desktop.
- The LLM model is optional, but improves translation quality.
- It is strongly recommended to run LibreTranslate locally for full offline functionality.

---

## License

This project is for personal use only. Do not redistribute without permission from the original author.

---

## Contact

Andrea - Master Hobby

