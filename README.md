---

# Overlay Translate

Overlay Translate is a powerful tool for capturing and translating on-screen text using Tesseract OCR. It supports offline translation through a local server, AI-assisted translation (OpenAI, Ollama, LM Studio), and even offers interactive AI chat capabilities.

---

## ✨ Key Features

- **Flexible OCR**  
  Utilizes the Tesseract OCR engine for highly accurate text recognition.

- **Multiple Capture Methods**
  - **Overlay Capture (F1):** Capture adjustable screen regions.
  - **Snip Tool (F4):** Quickly select any part of the screen.
  - **Live Translation (F3):** Continuously translate dynamic content.

- **Integrated Viewer**
  - View captured images with overlaid translations.
  - Customize font, size, and colors.
  - Save captures easily.

- **Offline Translation**
  - Translate locally using a backend server (e.g., Flask + Argos Translate).
  - Requires setup (see below).

- **AI Translation**
  - Seamless integration with AI services:
    - **OpenAI** (requires API key)
    - **Ollama** (requires local endpoint)
    - **LM Studio** (local endpoint, API key optional)

- **AI Chat (Ctrl+T)**
  - Chat interface to interact with your configured AI model.
  - Useful for contextual translations, questions, and more.

- **Customizable Interface**
  - Adjust overlay opacity.
  - "Click-Through" mode (F2) to interact with windows behind the overlay.
  - Multiple visual themes and a theme editor.

- **System Integration**
  - Minimize to system tray.
  - Global keyboard shortcuts for key functions.

- **Utilities**
  - Resource monitor (CPU/RAM usage) in the status bar.
  - Detailed logging for troubleshooting.
  - Support folder containing captures, metadata, and logs.
  - Option to clean support files on exit.

---

## ⚙️ Requirements

- **Python:** Version 3.8 or higher recommended.

- **Tesseract OCR Engine:**  
  *Essential! Overlay Translate depends on Tesseract being installed.*

  - **Windows:**  
    Install using an official installer (e.g., UB Mannheim builds recommended).  
    ➔ Ensure the Tesseract installation directory is added to your system's PATH variable.  
    ➔ The app also tries to auto-detect common installation locations.

  - **macOS:**  
    ```bash
    brew install tesseract tesseract-lang
    ```

  - **Linux (Debian/Ubuntu):**  
    ```bash
    sudo apt update
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```
    (Or install specific language packs, e.g., `tesseract-ocr-eng`, `tesseract-ocr-jpn`, etc.)

  - **Other Linux distros:**  
    Use your package manager (e.g., yum, dnf).

  - **Language Packs:**  
    ➔ You must install `.traineddata` files for all languages you intend to OCR.  
    ➔ Verify installed languages via the app (Help ➔ Tesseract Info).

- **Python Dependencies:**  
  Install all required libraries:
  ```bash
  pip install -r requirements.txt
  ```

---

## 🚀 Basic Usage

1. **Start the App:**  
   Run:
   ```bash
   python main.py
   ```
   from the project directory.

2. **Adjust the Overlay:**  
   Move and resize the translucent window to cover the text you want to capture.

3. **Capture Options:**  
   - **Overlay Capture (F1):** Captures text inside the overlay.
   - **Snip Tool (F4):** Drag and capture any area.
   - **Live Translation (F3):** Continuously translate the selected area.

4. **Other Shortcuts:**
   - **Click-Through Mode (F2):** Enable or disable click-through behavior.
   - **AI Chat (Ctrl+T):** Open the AI chat window.

5. **Settings:**  
   Configure OCR source languages, translation targets, AI providers, fonts, themes, and more via the menu.

---

## 🔧 Additional Configuration

- **Offline Local Server:**  
  To enable offline translation, run a local server like the example in `app.py` (Flask + Argos Translate) accessible at:
  ```
  http://127.0.0.1:5000
  ```

- **AI Providers:**  
  Go to **Settings ➔ AI Configuration** to set up:
  - OpenAI (API key required)
  - Ollama (local endpoint)
  - LM Studio (local endpoint)

  Secure storage for API keys is handled via `keyring`.

- **Tesseract Info:**  
  If Tesseract is not detected, verify your installation and PATH environment variable.  
  Check detected Tesseract info inside the app under **Help ➔ Tesseract Info**.

---

## 📂 Folder Structure

- **Support Folder:**  
  Located on your Desktop by default. It contains:
  - Screenshots
  - Metadata files (`.txt`)
  - Application logs

- **Cleanup:**  
  You can enable automatic cleanup on exit in the settings.

---

## 🛠️ Troubleshooting

- **OCR issues?**  
  Ensure correct installation of Tesseract and all necessary language packs.

- **Server not found?**  
  Verify your local translation server is running and available at the configured address.

- **Keyboard shortcuts not working?**  
  Make sure the app window is focused or check system settings for global hotkey conflicts.

---

Overlay Translate is under active development — feedback and contributions are welcome!

---
