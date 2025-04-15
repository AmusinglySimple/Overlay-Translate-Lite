Below is an updated version of your `README.md` for **Overlay Translate**, tailored to reflect the features and structure of your `otfull.py` script. The update maintains the original structure, improves clarity, and incorporates details from the provided code, such as the system tray integration, AI API configuration, and the modern UI. It also corrects minor inaccuracies (e.g., the script name, hotkeys, and requirements) and enhances the documentation to be more user-friendly and professional.

---

# Overlay Translate

Overlay Translate is a powerful offline tool designed to capture on-screen text, translate it in real-time, and display translations in a customizable, non-intrusive overlay. Perfect for translating text in videos, games, software, documents, or any on-screen content without an internet connection.

---

## Features

- ✨ **Live Translation**: Stream translations in real-time from a floating capture region.
- 📸 **Static Capture**: Take instant screenshots for quick translations.
- 🔍 **Offline OCR**: Powered by PaddleOCR for accurate text recognition.
- ⚖ **Offline Translation**: Uses LibreTranslate for reliable, internet-free translations.
- 🤖 **AI-Enhanced Translation**: Optional integration with local or remote LLMs (e.g., OpenAI, Ollama, LM Studio) for context-aware translations.
- 🌐 **Multilingual Support**: Auto-detects source languages and supports multiple target languages.
- 🎨 **Customization**: Adjust font size, type, colors, opacity, and contrast for the overlay and translated text.
- ✂️ **Snipping Tool**: Built-in tool for precise region selection.
- 🖥️ **Modern UI**: Sleek, futuristic interface with animations and system tray integration.
- ⚙️ **Flexible Settings**: Configure AI APIs, save window positions, and toggle click-through mode.
- 💬 **AI Chat**: Interactive terminal for conversing with AI models.

---

## System Requirements

- **Operating System**: Windows 10/11, macOS, or Linux
- **Python**: 3.8 
- **Hardware**:
  - No GPU required (CPU-based OCR and translation)
  - Minimum 4 GB RAM (8 GB recommended for AI features)
- **Disk Space**: ~500 MB for dependencies and temporary files

---

## Installation

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd OverlayTranslate
   ```

2. **Install Dependencies**:
   Create a virtual environment (optional but recommended) and install the required packages:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set Up LibreTranslate**:
   - Install LibreTranslate locally for offline translation:
     ```bash
     pip install libretranslate
    
     ```
   - LibreTranslate will be running only during the session on `http://127.0.0.1:5000` after starting the application.

4. **Optional - Configure AI Models**:
   - For AI-enhanced translations or chat, configure an AI provider (OpenAI, Ollama, or LM Studio) via the *Settings > Configure AI API* menu.
   - For local LLMs, ensure models like `llama3.2` (for Ollama) are installed and running locally.

5. **Run the Application**:
   ```bash
   python OT - API Requests.py
   ```

---

## Quick Usage

- **Hotkeys**:
  - `F1`: Capture screen and translate
  - `F2`: Toggle click-through mode for the capture region
  - `F4`: Activate the snipping tool for custom region selection
- **Menu Options**:
  - *Settings > Source Language*: Set the source language (default: auto-detect)
  - *Settings > Target Language*: Choose the target language (default: English)
  - *Settings > Configure AI API*: Set up AI providers for enhanced translations
  - *Tools > Pop Out Live Translation*: Display live translations in a separate window
  - *Tools > Chat with AI*: Open an interactive AI chat terminal
- **System Tray**:
  - Minimize to tray for background operation
  - Restore or exit via the tray icon

---

## Folder Structure

```
OverlayTranslate/
├── assets/
│   ├── icons/              # Icons for buttons (e.g., capture.svg, live.svg)
│   └── icon.png            # System tray icon
├── Support/                # Runtime folder on Desktop for captures and translations
├── window_positions.json   # Stores window positions and settings (generated)
├── otfull.py               # Main application script
└── requirements.txt        # Dependency list
```

---

## requirements.txt

```
PySide6>=6.0.0
paddlepaddle>=2.5.0
paddleocr>=2.7.0
Pillow>=10.0.0
opencv-python>=4.8.0
langdetect>=1.0.9
requests>=2.31.0
libretranslate>=1.5.0
numpy>=1.24.0
keyring>=24.2.0
```

---

## Additional Notes

- **Temporary Files**: Captures and translated images are saved in the `~/Desktop/Support` folder and deleted on application exit.
- **AI Translation**: Requires configuration of an AI provider (e.g., OpenAI with an API key or Ollama running locally). AI translations are disabled during live capture for performance.
- **Font Customization**: Choose from system fonts like Roboto, MS YaHei (Chinese/Japanese), or Malgun Gothic (Korean) for translated text.
- **Performance Tips**:
  - Use a GPU for faster OCR if available (configure PaddleOCR with `use_gpu=True`).
  - For local AI models, ensure sufficient RAM (16 GB+ for large models).
- **Troubleshooting**:
  - Ensure LibreTranslate is running before launching the app.
  - Check logs in `overlay_translate.log` for errors.
  - Verify font paths in `otfull.py` match your system.

---

## License

This project is for personal use only. Redistribution or commercial use is prohibited without explicit permission from the author.

---

## Contact

Andrea - Master Hobby  
For support or inquiries, open an issue on the repository or contact the author directly.

---

### Changelog

- **v1.0 (Initial Release)**:
  - Offline OCR and translation
  - Live and static capture modes
  - Customizable UI with system tray support
  - AI integration for enhanced translations and chat

---
