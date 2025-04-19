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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
# Set cache/data directory within the project for portability (optional)
script_dir = os.path.dirname(os.path.abspath(__file__))
argos_data_dir = os.path.join(script_dir, ".argos-translate-data")
argostranslate.settings.data_dir = argos_data_dir
argostranslate.settings.package_data_dir = os.path.join(argos_data_dir, "packages")
os.makedirs(argostranslate.settings.package_data_dir, exist_ok=True)

logging.info(f"Argos Translate data directory: {argostranslate.settings.data_dir}")
logging.info(f"Argos Translate package directory: {argostranslate.settings.package_data_dir}")

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
        logging.error(f"Error getting installed languages: {e}")
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
        logging.error(f"Error getting installed models: {e}")
        return []

def get_available_models_formatted():
    """Gets available models for download."""
    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
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
                        "_package": pkg
                    })
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        logging.error(f"Error getting available models: {e}")
        try:
            logging.info("Retrying package index update...")
            argostranslate.package.update_package_index(force=True)
        except Exception as retry_e:
            logging.error(f"Retry failed: {retry_e}")
        return []

def download_worker():
    """Worker thread to process downloads from the queue."""
    global download_status
    while True:
        pkg_info = download_queue.get()
        if pkg_info is None:
            break

        model_id = pkg_info['id']
        logging.info(f"Starting download for model: {model_id}")
        download_status[model_id] = {"status": "downloading", "progress": 0, "message": "Starting download..."}

        try:
            argostranslate.package.update_package_index()
            available_packages = argostranslate.package.get_available_packages()
            package_to_download = None
            for pkg in available_packages:
                 if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
                    f"{pkg.from_code}_{pkg.to_code}" == model_id:
                     package_to_download = pkg
                     break

            if not package_to_download:
                raise ValueError(f"Package {model_id} not found in available list.")

            download_status[model_id] = {"status": "downloading", "progress": 30, "message": "Downloading package..."}
            download_path = package_to_download.download()

            if download_path:
                download_status[model_id] = {"status": "installing", "progress": 70, "message": "Installing package..."}
                argostranslate.package.install_from_path(download_path)
                download_status[model_id] = {"status": "completed", "progress": 100, "message": "Model installed successfully!"}
                logging.info(f"Successfully installed model: {model_id}")
            else:
                raise Exception("Download failed, path not returned.")

        except Exception as e:
            error_message = f"Error processing model {model_id}: {e}"
            logging.error(error_message)
            download_status[model_id] = {"status": "error", "progress": 0, "message": f"Error: {e}"}
        finally:
            download_queue.task_done()

# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main page."""
    return render_template('index.html')

@app.route('/api/languages')
def get_languages():
    """Returns list of installed languages."""
    installed = get_installed_languages_formatted()
    return jsonify({"installed": installed})

@app.route('/api/models/installed')
def get_installed_models_route():
    """Returns list of installed translation models."""
    return jsonify(get_installed_models_formatted())

@app.route('/api/models/available')
def get_available_models_route():
    """Returns list of available translation models for download."""
    return jsonify(get_available_models_formatted())

@app.route('/api/translate', methods=['POST'])
def translate_text():
    """Handles translation requests."""
    try:
        data = request.get_json()
        text = data.get('text', '')
        source_lang = data.get('source_lang', '')
        target_lang = data.get('target_lang', '')

        if not text or not source_lang or not target_lang:
            return jsonify({"error": "Missing required fields: text, source_lang, target_lang"}), 400

        installed_languages = argostranslate.translate.get_installed_languages()
        source = next((lang for lang in installed_languages if lang.code == source_lang), None)
        target = next((lang for lang in installed_languages if lang.code == target_lang), None)

        if not source or not target:
             return jsonify({"error": f"Source ({source_lang}) or Target ({target_lang}) language not installed."}), 404

        translation = source.get_translation(target)

        if translation is None:
            return jsonify({"error": f"No translation model installed for {source_lang} -> {target_lang}"}), 404

        translated_text = translation.translate(text)
        return jsonify({"translated_text": translated_text})

    except Exception as e:
        logging.error(f"Translation error: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred: {e}"}), 500

@app.route('/api/models/download', methods=['POST'])
def download_model():
    """Initiates model download."""
    global download_thread
    data = request.get_json()
    model_id = data.get('id')

    if not model_id:
        return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400

    if model_id in download_status and download_status[model_id]['status'] in ['downloading', 'installing']:
         return jsonify({"message": f"Model {model_id} download/install already in progress."}), 409

    if download_thread is None or not download_thread.is_alive():
        logging.info("Starting download worker thread.")
        download_thread = threading.Thread(target=download_worker, daemon=True)
        download_thread.start()

    download_queue.put({"id": model_id})
    download_status[model_id] = {"status": "queued", "progress": 0, "message": "Download queued..."}

    logging.info(f"Queued download for model: {model_id}")
    return jsonify({"message": f"Download initiated for model {model_id}. Check /api/download/status/{model_id} for progress.", "id": model_id}), 202

@app.route('/api/download/status/<model_id>')
def get_download_status(model_id):
    """Gets the status of a specific download."""
    status_info = download_status.get(model_id)
    if status_info:
        return jsonify(status_info)
    else:
        return jsonify({"status": "not_found", "message": "Download status not found for this ID."}), 404

@app.route('/api/models/delete', methods=['POST'])
def delete_model():
    """Deletes an installed model."""
    try:
        data = request.get_json()
        model_id = data.get('id')

        if not model_id:
            return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400

        parts = model_id.split('_')
        if len(parts) != 2:
             return jsonify({"error": "Invalid model 'id' format. Should be 'fromCode_toCode'"}), 400
        from_code, to_code = parts

        installed_packages = argostranslate.package.get_installed_packages()
        package_to_delete = None
        for pkg in installed_packages:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
               pkg.from_code == from_code and pkg.to_code == to_code:
                package_to_delete = pkg
                break

        if package_to_delete:
            logging.info(f"Attempting to uninstall model: {model_id}")
            argostranslate.package.uninstall(package_to_delete)
            if model_id in download_status:
                del download_status[model_id]
            logging.info(f"Successfully uninstalled model: {model_id}")
            return jsonify({"message": f"Model {model_id} deleted successfully."}), 200
        else:
            logging.warning(f"Model {model_id} not found for deletion.")
            return jsonify({"error": f"Model {model_id} not found or is not installed."}), 404

    except Exception as e:
        logging.error(f"Error deleting model {model_id}: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred while deleting: {e}"}), 500

# New shutdown endpoint
@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shuts down the Flask server."""
    def shutdown_server():
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

    shutdown_thread = threading.Thread(target=shutdown_server)
    shutdown_thread.start()
    return jsonify({"message": "Shutting down..."})

# --- Main Execution ---
if __name__ == '__main__':
    if download_thread is None or not download_thread.is_alive():
        logging.info("Starting download worker thread on app start.")
        download_thread = threading.Thread(target=download_worker, daemon=True)
        download_thread.start()

    app.run(host='127.0.0.1', port=5000, debug=True)