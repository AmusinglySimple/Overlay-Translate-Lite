Okay, here is the updated README.md in English, incorporating the information about Tesseract installation and the importance of language packs:

--- START OF FILE README.md ---

Overlay Translate

Overlay Translate is a versatile tool for capturing and translating on-screen text using Tesseract OCR. It offers offline translation (via a local server), AI-assisted translation (OpenAI, Ollama, LM Studio), and interactive chat capabilities.

✨ Key Features

Flexible OCR: Utilizes the Tesseract OCR engine for text recognition.

Multiple Capture Methods:

Adjustable screen region capture overlay (F1).

"Snip" tool for quick selections (F4).

Live Translation: Continuous translation mode (F3) for dynamic content.

Integrated Viewer: Displays the captured image with translated text overlaid. Allows adjustment of font, size, and colors for viewing and saving.

Offline Translation: Capable of local translation using a backend server (e.g., Flask with Argos Translate in app.py - requires setup).

AI Translation: Configurable support for AI services:

OpenAI (Requires API Key)

Ollama (Requires local endpoint)

LM Studio (Requires local endpoint, API Key optional)

AI Chat: Chat interface (Ctrl+T) to interact with the configured AI model (contextual translations, questions, etc.).

Customizable Interface:

Overlay opacity adjustment.

"Click-Through" mode (F2) to interact with windows behind the overlay.

Multiple predefined visual Themes and an editor to create custom themes.

System Integration:

Minimize to System Tray.

Global keyboard shortcuts for key functions.

Utilities:

Resource Monitor (App CPU/RAM) in the status bar.

Detailed Logging.

Support Folder (Support on Desktop by default) containing captures, metadata (.txt), and logs. Cleanup option on exit.

⚙️ Requirements

Python: Version 3.8 or higher recommended.

Tesseract OCR Engine:

Essential! You must install Tesseract OCR separately on your operating system. This application is a wrapper around the Tesseract engine.

Windows: Using an official installer (like those from UB Mannheim, linked on the Tesseract Wiki) is recommended. Ensure the installation directory is added to your system's PATH environment variable, or the app will attempt to find common install locations.

macOS: Use Homebrew: brew install tesseract tesseract-lang

Linux (Debian/Ubuntu): sudo apt update && sudo apt install tesseract-ocr tesseract-ocr-all (or install specific language packs like tesseract-ocr-eng, tesseract-ocr-spa, etc.)

Other Linux: Use your distribution's package manager (e.g., yum, dnf).

Language Packs: Crucially, you MUST install the language packs (.traineddata files) for the languages you intend to perform OCR on. This is usually an option during installation (Windows) or requires installing separate packages (Linux/macOS, e.g., tesseract-ocr-eng, tesseract-ocr-jpn, tesseract-ocr-chi-sim, tesseract-ocr-kor). Install packs for all source languages you might use.

Verification: Check Help -> Tesseract Info... within the application to see the detected Tesseract path and installed languages.

Python Dependencies: Install the required libraries using pip:

pip install -r requirements.txt


(Make sure you have the requirements.txt file in the project directory).

🚀 Basic Usage

Start: Run python main.py from your terminal in the project directory.

Adjust: Move and resize the translucent overlay window to cover the screen area you want to capture.

Capture (F1): Press F1 to capture the text within the overlay, perform OCR, and translate. The result will be shown in the viewer.

Snip (F4): Press F4 to activate the Snipping Tool. Drag to select an area; upon release, it will be captured and translated.

Live (F3): Press F3 to toggle Live Translation mode. It will continuously translate content under the overlay. The result appears in the control window or a pop-out window if activated.

Click-Through (F2): Press F2 to allow mouse clicks to pass through the overlay or to make it interactive again.

AI Chat (Ctrl+T): Open the chat window to interact with the configured AI model.

Configure: Use the menus (Settings, Help) to change languages (OCR source and translation target), configure the AI provider, adjust fonts, switch themes, and more.

🔧 Additional Configuration

Local Server (Offline): For offline translation, you need a compatible translation server (like the example in app.py using Flask and Argos Translate) configured and running at http://127.0.0.1:5000.

Artificial Intelligence: Go to Settings -> AI Configuration to select your provider (OpenAI, Ollama, LM Studio) and enter the necessary API Keys or Endpoints. Secure keys are stored using keyring.

Tesseract: If the application cannot find Tesseract, verify your installation and system PATH environment variable. Detected information is shown in Help -> Tesseract Info....

--- END OF FILE README.md ---
