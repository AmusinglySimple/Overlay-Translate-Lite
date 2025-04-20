import os
import time
import json
import threading
from queue import Queue
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import argostranslate.package
import argostranslate.translate
import argostranslate.settings
import logging

# Configure logging
# Use a basic configuration for simplicity, or integrate with the main app's logging if preferred
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler = logging.StreamHandler(sys.stdout) # Log Flask output to stdout
log_handler.setFormatter(log_formatter)

# Get the Flask logger and add our handler
flask_logger = logging.getLogger('werkzeug') # Werkzeug is the default dev server
flask_logger.setLevel(logging.INFO) # Or DEBUG for more verbosity
# flask_logger.addHandler(log_handler) # Already logs to console by default

# Configure our own app logging
app_logger = logging.getLogger(__name__)
app_logger.setLevel(logging.DEBUG) # Log debug messages from our app routes
app_logger.addHandler(log_handler)
app_logger.propagate = False # Prevent duplicate logging to root logger if main app also logs

# --- Configuration ---
script_dir = os.path.dirname(os.path.abspath(__file__))
argos_data_dir = os.path.join(script_dir, ".argos-translate-data")
argostranslate.settings.data_dir = argos_data_dir
argostranslate.settings.package_data_dir = os.path.join(argos_data_dir, "packages")
os.makedirs(argostranslate.settings.package_data_dir, exist_ok=True)

app_logger.info(f"Argos Translate data directory: {argostranslate.settings.data_dir}")
app_logger.info(f"Argos Translate package directory: {argostranslate.settings.package_data_dir}")

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Download State Management ---
download_status = {}
download_queue = Queue()
download_thread = None

# --- Helper Functions ---

def get_installed_languages_formatted():
    """Gets installed languages suitable for frontend dropdowns."""
    try:
        installed = argostranslate.translate.get_installed_languages()
        return sorted(
            [{"code": lang.code, "name": lang.name} for lang in installed],
            key=lambda x: x["name"]
        )
    except Exception as e:
        app_logger.error(f"Error getting installed languages: {e}")
        return []

def get_installed_models_formatted():
    """Gets installed translation models."""
    try:
        packages = argostranslate.package.get_installed_packages()
        models = []
        for pkg in packages:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code'):
                 models.append({
                     "from_code": pkg.from_code,
                     "to_code": pkg.to_code,
                     "from_name": pkg.from_name,
                     "to_name": pkg.to_name,
                     "package_version": pkg.package_version,
                     "argos_version": pkg.argos_version,
                     "id": f"{pkg.from_code}_{pkg.to_code}"
                 })
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        app_logger.error(f"Error getting installed models: {e}")
        return []

def get_available_models_formatted():
    """Gets available models for download."""
    try:
        app_logger.debug("Updating package index...")
        argostranslate.package.update_package_index()
        app_logger.debug("Package index updated.")
        available = argostranslate.package.get_available_packages()
        app_logger.debug(f"Found {len(available)} available packages.")
        models = []
        installed_ids = {f"{m['from_code']}_{m['to_code']}" for m in get_installed_models_formatted()}

        for pkg in available:
             if hasattr(pkg, 'package_type') and pkg.package_type == "translate" and \
                hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code'):
                model_id = f"{pkg.from_code}_{pkg.to_code}"
                if model_id not in installed_ids:
                    models.append({
                        "from_code": pkg.from_code,
                        "to_code": pkg.to_code,
                        "from_name": pkg.from_name,
                        "to_name": pkg.to_name,
                        "package_version": pkg.package_version,
                        "argos_version": pkg.argos_version,
                        "id": model_id,
                        "_package": pkg # Keep ref for download if needed, but don't JSON serialize
                    })
        app_logger.debug(f"Formatted {len(models)} available models for download.")
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        app_logger.error(f"Error getting available models: {e}")
        # Removed retry logic here as it might hide underlying issues
        return []

def download_worker():
    """Worker thread to process downloads from the queue."""
    global download_status
    while True:
        pkg_info = download_queue.get()
        if pkg_info is None:
            app_logger.info("Download worker thread stopping.")
            break

        model_id = pkg_info['id']
        app_logger.info(f"Starting download process for model: {model_id}")
        download_status[model_id] = {"status": "downloading", "progress": 0, "message": "Starting download..."}

        try:
            app_logger.debug(f"Updating package index before download for {model_id}...")
            argostranslate.package.update_package_index() # Ensure index is fresh
            available_packages = argostranslate.package.get_available_packages()
            package_to_download = None
            for pkg in available_packages:
                 # Check attributes robustly
                 if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
                    f"{pkg.from_code}_{pkg.to_code}" == model_id:
                     package_to_download = pkg
                     break

            if not package_to_download:
                raise ValueError(f"Package {model_id} not found in available list after index update.")

            download_status[model_id] = {"status": "downloading", "progress": 30, "message": "Downloading package..."}
            app_logger.info(f"Calling download for package {model_id}...")
            # The download function now accepts a callback for progress
            # We don't have a simple way to hook that into Flask responses here,
            # so we rely on coarse status updates.
            download_path = package_to_download.download()

            if download_path:
                app_logger.info(f"Download complete for {model_id}, path: {download_path}")
                download_status[model_id] = {"status": "installing", "progress": 70, "message": "Installing package..."}
                argostranslate.package.install_from_path(download_path)
                download_status[model_id] = {"status": "completed", "progress": 100, "message": "Model installed successfully!"}
                app_logger.info(f"Successfully installed model: {model_id}")
                # Clean up downloaded file? ArgosTranslate might do this already. Check its behavior.
                # if os.path.exists(download_path):
                #     os.remove(download_path)
                #     app_logger.debug(f"Removed downloaded package file: {download_path}")
            else:
                raise Exception("Download method returned no path.")

        except Exception as e:
            error_message = f"Error processing model {model_id}: {e}"
            app_logger.error(error_message, exc_info=True)
            download_status[model_id] = {"status": "error", "progress": 0, "message": f"Error: {e}"}
        finally:
            download_queue.task_done()

# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main page."""
    app_logger.info("Serving index.html")
    return render_template('index.html')

@app.route('/api/languages')
def get_languages():
    """Returns list of installed languages."""
    app_logger.info("Request received for /api/languages")
    installed = get_installed_languages_formatted()
    app_logger.info(f"Returning {len(installed)} installed languages.")
    return jsonify({"installed": installed})

@app.route('/api/models/installed')
def get_installed_models_route():
    """Returns list of installed translation models."""
    app_logger.info("Request received for /api/models/installed")
    models = get_installed_models_formatted()
    app_logger.info(f"Returning {len(models)} installed models.")
    return jsonify(models)

@app.route('/api/models/available')
def get_available_models_route():
    """Returns list of available translation models for download."""
    app_logger.info("Request received for /api/models/available")
    models = get_available_models_formatted()
    app_logger.info(f"Returning {len(models)} available models.")
    # Remove internal _package reference before sending JSON
    models_safe = [{k: v for k, v in m.items() if k != '_package'} for m in models]
    return jsonify(models_safe)

@app.route('/api/translate', methods=['POST'])
def translate_text():
    """Handles translation requests."""
    data = request.get_json()
    app_logger.info(f"/api/translate received data: {data}") # Log received data first
    try:
        text = data.get('text', '')
        source_lang_code = data.get('source_lang', '')
        target_lang_code = data.get('target_lang', '')

        if not text or not source_lang_code or not target_lang_code:
            app_logger.warning(f"Missing required fields in /api/translate request: {data}")
            return jsonify({"error": "Missing required fields: text, source_lang, target_lang"}), 400

        # Handle auto-detection if source_lang is 'auto' (though Argos doesn't directly support it)
        # The main app should detect and pass the actual language code
        if source_lang_code == 'auto':
            # If 'auto' is passed, we rely on the main app having detected it.
            # If not, ArgosTranslate cannot handle 'auto'. We might need a default.
            # For now, assume the main app sends a specific language code.
            # If 'auto' *must* be handled here, language detection would be needed.
            # Example (requires langdetect):
            # try:
            #     from langdetect import detect
            #     detected_lang = detect(text[:500]) # Detect based on sample
            #     source_lang_code = detected_lang
            #     app_logger.info(f"Auto-detected source language as: {source_lang_code}")
            # except Exception as detect_err:
            #     app_logger.warning(f"Language auto-detection failed: {detect_err}. Cannot proceed.")
            #     return jsonify({"error": "Language auto-detection failed."}), 400
             app_logger.warning("Received 'auto' source language. ArgosTranslate requires a specific code. Relying on main app detection.")
             # If the main app *always* sends a specific code, this branch might not be needed.
             # If it can send 'auto', this needs logic to handle it (like detection above or erroring out).
             # For now, let's assume the main app handles 'auto' and sends a specific code.
             # If it still gets here as 'auto', it will likely fail below.


        installed_languages = argostranslate.translate.get_installed_languages()
        source_lang = next((lang for lang in installed_languages if lang.code == source_lang_code), None)
        target_lang = next((lang for lang in installed_languages if lang.code == target_lang_code), None)

        if not source_lang:
            msg = f"Source language '{source_lang_code}' not installed."
            app_logger.warning(msg)
            return jsonify({"error": msg}), 404
        if not target_lang:
            msg = f"Target language '{target_lang_code}' not installed."
            app_logger.warning(msg)
            return jsonify({"error": msg}), 404

        app_logger.info(f"Attempting translation from '{source_lang.name}' ({source_lang_code}) to '{target_lang.name}' ({target_lang_code})")
        translation = source_lang.get_translation(target_lang)

        if translation is None:
            msg = f"No translation model installed for {source_lang_code} -> {target_lang_code}"
            app_logger.warning(msg)
            return jsonify({"error": msg}), 404

        translated_text = translation.translate(text)
        app_logger.info(f"Translation successful: '{text[:30]}...' -> '{translated_text[:30]}...'")
        return jsonify({"translated_text": translated_text})

    except Exception as e:
        app_logger.error(f"Exception in /api/translate: {e}", exc_info=True)
        return jsonify({"error": f"An internal server error occurred during translation: {e}"}), 500


@app.route('/api/models/download', methods=['POST'])
def download_model():
    """Initiates model download."""
    global download_thread
    data = request.get_json()
    model_id = data.get('id')
    app_logger.info(f"Request received for /api/models/download: {data}")

    if not model_id:
        app_logger.warning("Missing model ID in download request.")
        return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400

    if model_id in download_status and download_status[model_id]['status'] in ['downloading', 'installing', 'queued']:
         app_logger.warning(f"Download/install already in progress or queued for model: {model_id}")
         return jsonify({"message": f"Model {model_id} download/install already in progress or queued."}), 409 # 409 Conflict

    # Start worker thread if not running
    if download_thread is None or not download_thread.is_alive():
        app_logger.info("Starting download worker thread.")
        download_thread = threading.Thread(target=download_worker, daemon=True)
        download_thread.start()

    # Add package info to queue
    download_queue.put({"id": model_id})
    download_status[model_id] = {"status": "queued", "progress": 0, "message": "Download queued..."}

    app_logger.info(f"Queued download for model: {model_id}")
    return jsonify({"message": f"Download initiated for model {model_id}. Check /api/download/status/{model_id} for progress.", "id": model_id}), 202 # 202 Accepted

@app.route('/api/download/status/<model_id>')
def get_download_status(model_id):
    """Gets the status of a specific download."""
    app_logger.debug(f"Request received for /api/download/status/{model_id}")
    status_info = download_status.get(model_id)
    if status_info:
        app_logger.debug(f"Returning status for {model_id}: {status_info}")
        return jsonify(status_info)
    else:
        app_logger.warning(f"Status not found for model ID: {model_id}")
        return jsonify({"status": "not_found", "message": "Download status not found for this ID."}), 404

@app.route('/api/models/delete', methods=['POST'])
def delete_model():
    """Deletes an installed model."""
    data = request.get_json()
    model_id = data.get('id')
    app_logger.info(f"Request received for /api/models/delete: {data}")

    if not model_id:
        app_logger.warning("Missing model ID in delete request.")
        return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400

    parts = model_id.split('_')
    if len(parts) != 2:
         app_logger.warning(f"Invalid model ID format for deletion: {model_id}")
         return jsonify({"error": "Invalid model 'id' format. Should be 'fromCode_toCode'"}), 400
    from_code, to_code = parts

    try:
        installed_packages = argostranslate.package.get_installed_packages()
        package_to_delete = None
        for pkg in installed_packages:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
               pkg.from_code == from_code and pkg.to_code == to_code:
                package_to_delete = pkg
                break

        if package_to_delete:
            app_logger.info(f"Attempting to uninstall model: {model_id}")
            argostranslate.package.uninstall(package_to_delete)
            # Remove status if it exists
            if model_id in download_status:
                del download_status[model_id]
            app_logger.info(f"Successfully uninstalled model: {model_id}")
            return jsonify({"message": f"Model {model_id} deleted successfully."}), 200
        else:
            app_logger.warning(f"Model {model_id} not found for deletion.")
            return jsonify({"error": f"Model {model_id} not found or is not installed."}), 404

    except Exception as e:
        app_logger.error(f"Error deleting model {model_id}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred while deleting: {e}"}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shuts down the Flask server."""
    app_logger.info("Shutdown endpoint called.")
    shutdown_func = request.environ.get('werkzeug.server.shutdown')
    if shutdown_func is None:
        app_logger.error('Shutdown failed: Not running with the Werkzeug Server')
        return jsonify({"error": "Server shutdown function not available."}), 500

    app_logger.info("Initiating server shutdown...")
    # Run shutdown in a separate thread to allow the response to be sent
    shutdown_thread = threading.Thread(target=shutdown_func, name="FlaskShutdownThread")
    shutdown_thread.start()
    return jsonify({"message": "Shutting down..."}), 200


# --- Main Execution ---
if __name__ == '__main__':
    # Ensure download worker thread is started if not already
    if download_thread is None or not download_thread.is_alive():
        app_logger.info("Starting download worker thread on app start.")
        download_thread = threading.Thread(target=download_worker, daemon=True, name="DownloadWorker")
        download_thread.start()

    # Run Flask app (use_reloader=False is important when run by another script)
    app_logger.info("Starting Flask server...")
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    app_logger.info("Flask server stopped.")
