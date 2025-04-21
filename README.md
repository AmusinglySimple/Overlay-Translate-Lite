# Overlay Translate 🌌

Overlay Translate provides a seamless way to capture text directly from your screen using an overlay or snipping tool and instantly translate it using offline (Argos Translate) or online AI (OpenAI, Ollama, LM Studio) models.

**(Optional: Add a Screenshot or GIF Here)**
<!-- ![Overlay Translate Screenshot](link/to/your/screenshot.png) -->

## ✨ Features

*   **Screen Capture:** Capture text within a defined overlay area (`F1`).
*   **Snipping Tool:** Select a specific screen region for capture (`F4`).
*   **Live Translation:** Continuously capture and translate text in the overlay area (`F3`).
*   **Offline Translation:** Uses a local [Argos Translate](https://www.argosopentech.com/) backend (via Flask) for privacy-focused translation.
*   **AI Translation:** Integrate with OpenAI, Ollama, or LM Studio APIs for advanced translation (requires configuration).
*   **AI Chat:** Open a dedicated chat window to interact with your configured AI model (`Ctrl+T`).
*   **Customizable Overlay:**
    *   Adjustable position and size.
    *   Variable opacity (`Opacity Slider`).
    *   Click-through mode (`F2` or low opacity).
*   **Theming:** Customize the application's appearance via Theme Settings.
*   **Font Selection:** Choose fonts and sizes for translated text display in the viewer.
*   **Pop-out Window:** Display live translations in a separate, movable window.
*   **Tray Icon:** Minimize the application to the system tray for easy access.
*   **Support Folder:** Automatically saves captured images, translated images (with text overlay), and translation details (`.txt`) to a dedicated folder on your Desktop.

## 💻 Technology Stack

*   **Python:** 3.8
*   **GUI:** PySide6 (Qt 6)
*   **OCR:** PaddleOCR
*   **Offline Translation:** Argos Translate, Flask
*   **Core Libraries:** Pillow, OpenCV-Python, Requests, NumPy, Langdetect-py, Keyring

## 🚀 Installation

1.  **Prerequisites:**
    *   Python 3.8 or higher installed.
    *   `pip` (Python package installer).
    *   Git (for cloning).

2.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/overlay-translate.git # Replace with your repo URL
    cd overlay-translate
    ```

3.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

**Folder Structure** 
```bash
overlay-translate/
├── assets/
│   ├── icons/
│   │   ├── capture.svg
│   │   ├── click.svg
│   │   ├── launch.svg
│   │   ├── live.svg
│   │   ├── send.svg
│   │   ├── snip.svg
│   │   ├── stop.svg
│   │   ├── zoom_in.svg
│   │   └── zoom_out.svg
│   └── icon.png
├── gui/
│   ├── __init__.py
│   ├── control_window.py
│   ├── capture_widget.py
│   ├── snipping_tool.py
│   ├── dialogs.py           # Contains Intro, Theme, Chat, Live, Viewer dialogs
│   ├── custom_widgets.py    # Contains ColorBarPicker, DraggableResizableWidget
│   └── resource_monitor.py  # New widget for CPU/RAM
├── utils/
│   ├── __init__.py
│   ├── config.py           # Constants, logging setup, theme defaults
│   ├── helpers.py          # Font finding, config load/save, theme generation
│   └── ocr_utils.py        # PaddleOCR initialization and management
├── workers.py              # All QThread worker classes
├── app.py                  # Your Flask application (unchanged)
├── main.py                 # Main application entry point
└── requirements.txt        # Project dependencies
  ```

    
    *   **Note on PaddlePaddle:** The `requirements.txt` includes the standard `paddlepaddle`. If you have a compatible NVIDIA GPU and want GPU acceleration for OCR (which can be significantly faster), you might need to install the GPU version separately. Refer to the [PaddlePaddle installation guide](https://www.paddlepaddle.org.cn/install/quick) for specific instructions based on your CUDA version.

5.  **Argos Translate Models:** Language models for offline translation are typically downloaded automatically by the backend server (`app.py`) on first use or can be managed via the server's web UI (see Usage).

## ▶️ Usage

1.  **Run the Application:**
    ```bash
    python OverlayTranslateNewServer.py
    ```
    *   The main control window and the semi-transparent capture overlay will appear.
    *   The local Flask translation server will start in the background.

2.  **Position the Overlay:** Drag and resize the overlay window to cover the area of the screen you want to capture text from.

3.  **Capture and Translate:**
    *   **Single Capture (`F1`):** Press `F1` or click the "Capture" button. The text within the overlay will be captured and translated. A viewer window will pop up showing the original image with the translated text overlaid. Close the viewer to automatically save the translated image and a `.txt` file with details to the `Support` folder on your Desktop.
    *   **Snipping Tool (`F4`):** Press `F4` or click "Snip". The screen will dim. Click and drag to select a specific region. Release the mouse to capture and translate that region. The viewer window will appear as with a normal capture. Press `Esc` or right-click to cancel snipping.
    *   **Live Mode (`F3`):** Press `F3` or click "Live" to toggle continuous capture and translation of the overlay area. The translation will appear in the "Live Translation Preview" section of the control window or in the pop-out window if activated. Press `F3` again to stop. *(Note: AI translation is disabled in Live Mode)*.

4.  **Overlay Controls:**
    *   **Opacity:** Use the slider in the control window to adjust the overlay's transparency.
    *   **Click-Through (`F2`):** Press `F2` or click the toggle button to make the overlay ignore mouse clicks (allowing interaction with windows underneath). Click-through is automatically enabled at very low opacity levels.

5.  **AI Configuration (Optional):**
    *   Go to `Settings -> AI Configuration -> Configure AI Provider...` in the menu bar.
    *   Select your provider (OpenAI, Ollama, LM Studio) and enter the required details (API Key, Endpoint). API keys are stored securely in your system's keyring, **not** in the configuration file.
    *   Enable AI translation using the toggle button in the main window or via `Settings -> AI Configuration -> Toggle AI Translation`. (Not available in Live Mode).

6.  **AI Chat (`Ctrl+T`):**
    *   Open the chat window to directly converse with your configured AI model. Requires AI to be configured first.

7.  **Translation Server UI:**
    *   Go to `Settings -> Open Translation Server UI`. This will open `http://127.0.0.1:5000` in your web browser, where you can manage installed Argos Translate language models.

8.  **Support Folder:**
    *   Access captured/translated images and logs via `Help -> Open Support Folder`.

9.  **Minimize/Exit:**
    *   Click the minimize button or `File -> Minimize to Tray` to hide windows and keep the app running in the system tray. Click the tray icon to restore.
    *   Use `File -> Exit` or the tray icon's Exit option to close the application properly. You will be asked if you want to delete the `Support` folder contents upon exit.

## ⚙️ Configuration

*   Window positions, theme settings, viewer preferences, and AI provider info (excluding keys) are saved in `window_positions.json` in the application's root directory.
*   Captured images, translated images, text data, and logs are stored in the `Support` folder created on your Desktop.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs, feature requests, or suggestions.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details (You'll need to create a LICENSE file, typically containing the standard MIT license text).
