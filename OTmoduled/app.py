# app.py
import os

# --- Set environment variable FIRST ---
# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
# Define the project-local data directory
project_argos_data_dir = os.path.join(script_dir, ".argos-translate-data")
# Set the environment variable
os.environ['ARGOSTRANSLATE_DATA_DIR'] = project_argos_data_dir
# Ensure the directory exists (though the library might do this, it's safer)
os.makedirs(os.path.join(project_argos_data_dir, "packages"), exist_ok=True)
# --- END Set environment variable ---

from langdetect import detect as langdetect_detect, LangDetectException # Import langdetect

import time
import json
import threading
from queue import Queue
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
# Imports for argostranslate should come *after* setting the environment variable
import argostranslate.package
import argostranslate.translate
import argostranslate.settings
# Removed: import argostranslate.cached_package
import logging

# Configure logging (set back to INFO if desired, or keep DEBUG)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
# These lines *should* now be redundant because of the environment variable,
# but we can keep them as a fallback or for clarity if desired.
# argos_data_dir = os.path.join(script_dir, ".argos-translate-data")
# argostranslate.settings.data_dir = argos_data_dir
# argostranslate.settings.package_data_dir = os.path.join(argos_data_dir, "packages")
# os.makedirs(argostranslate.settings.package_data_dir, exist_ok=True)

# Log the directory Argos is actually using *after* settings/env vars are applied
logging.info(f"Argos Translate effective data directory: {argostranslate.settings.data_dir}")
logging.info(f"Argos Translate effective package directory: {argostranslate.settings.package_data_dir}")
logging.info(f"Argos Translate data directory (from env): {os.environ.get('ARGOSTRANSLATE_DATA_DIR')}")


# --- Flask App Initialization ---
app = Flask(__name__)

# --- Download State Management ---
download_status = {}
download_queue = Queue()
download_thread = None

# --- Global cache for available packages ---
# This cache is still useful to avoid hitting the network index every time the menu is opened
last_available_packages_cache = []

# --- Helper Functions ---

def get_installed_languages_formatted():
    """Gets installed languages suitable for frontend dropdowns."""
    try:
        # load_installed_languages() no longer needs force=True
        argostranslate.translate.load_installed_languages()
        installed = argostranslate.translate.get_installed_languages()
        logging.info(f"Found {len(installed)} installed language objects.")
        formatted_list = []
        for lang in installed:
            if hasattr(lang, 'code') and hasattr(lang, 'name'):
                formatted_list.append({"code": lang.code, "name": lang.name})
            else:
                logging.warning(f"Skipping installed language due to missing attributes: {lang}")
        return sorted(formatted_list, key=lambda x: x["name"])
    except Exception as e:
        logging.error(f"Error getting installed languages: {e}", exc_info=True)
        return []

# --- SIMPLIFIED get_installed_models_formatted ---
def get_installed_models_formatted():
    """Gets installed translation models, focusing only on essential codes."""
    models = []
    try:
        packages = argostranslate.package.get_installed_packages()
        logging.info(f"get_installed_models_formatted: Found {len(packages)} raw packages.")
        for i, pkg in enumerate(packages):
            try:
                # ONLY check for from_code and to_code
                if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code'):
                    from_code = pkg.from_code
                    to_code = pkg.to_code
                    # Use codes as names if real names are missing
                    from_name = getattr(pkg, 'from_name', from_code)
                    to_name = getattr(pkg, 'to_name', to_code)

                    models.append({
                        "from_code": from_code,
                        "to_code": to_code,
                        "from_name": from_name,
                        "to_name": to_name,
                        "package_version": getattr(pkg, 'package_version', 'N/A'),
                        "argos_version": getattr(pkg, 'argos_version', 'N/A'),
                        "id": f"{from_code}_{to_code}"
                    })
                    logging.debug(f" Simplified processing added installed package {i}: {from_code}_{to_code}")
                else:
                    # Log why it was skipped in more detail
                    reason = []
                    if not hasattr(pkg, 'from_code'): reason.append("missing from_code")
                    if not hasattr(pkg, 'to_code'): reason.append("missing to_code")
                     # Only log warning if it's a potential translate package missing codes
                    if reason and getattr(pkg, 'package_type', None) == "translate":
                         logging.warning(f" Skipping installed package {i} ({getattr(pkg, 'metadata', pkg)}) because: {', '.join(reason)}")

            except Exception as inner_e:
                logging.error(f" Error processing installed package {i}: {inner_e}", exc_info=True)
                continue

        logging.info(f"get_installed_models_formatted: Returning {len(models)} models after simplified processing.")
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        logging.error(f"Error in get_installed_packages() itself: {e}", exc_info=True)
        return []
# --- END SIMPLIFIED ---


# --- REVERTED get_available_models_formatted (uses installed_ids set) ---
def get_available_models_formatted():
    """Gets available models and updates the global cache."""
    global last_available_packages_cache

    models_for_frontend = []
    # Use the SIMPLIFIED get_installed_models_formatted now
    installed_models_list = get_installed_models_formatted()
    installed_ids = {m['id'] for m in installed_models_list}
    logging.info(f"Found {len(installed_ids)} unique installed model IDs for filtering: {installed_ids}")

    current_available_packages = []

    try:
        logging.info("Attempting to update package index...")
        # No need for force=True, environment variable handles location
        argostranslate.package.update_package_index()
        logging.info("Package index updated successfully.")
        logging.info("Attempting to get available packages...")
        current_available_packages = argostranslate.package.get_available_packages()
        logging.info(f"Found {len(current_available_packages)} raw available packages.")
        last_available_packages_cache = current_available_packages

    except Exception as e:
        logging.error(f"Error updating/getting package index: {e}", exc_info=True); last_available_packages_cache = []; return []

    if not current_available_packages:
         logging.warning("No available packages found after index update.")
         last_available_packages_cache = []
         return []

    logging.info("Filtering available packages against installed IDs...")
    packages_processed_count = 0; packages_added_count = 0

    for pkg_available in current_available_packages:
         packages_processed_count += 1; model_id_available = "N/A"
         try:
            # Check basic attributes needed
            # Removed package_type check for available packages
            if hasattr(pkg_available, 'from_code') and hasattr(pkg_available, 'to_code') and \
               hasattr(pkg_available, 'from_name') and hasattr(pkg_available, 'to_name'):

                model_id_available = f"{pkg_available.from_code}_{pkg_available.to_code}"

                # Check efficiently against the set of installed IDs
                if model_id_available not in installed_ids:
                    logging.debug(f"  '{model_id_available}' is NOT installed. Adding to available list.")
                    packages_added_count += 1
                    models_for_frontend.append({
                        "from_code": pkg_available.from_code,
                        "to_code": pkg_available.to_code,
                        "from_name": pkg_available.from_name,
                        "to_name": pkg_available.to_name,
                        "package_version": getattr(pkg_available, 'package_version', 'N/A'),
                        "argos_version": getattr(pkg_available, 'argos_version', 'N/A'),
                        "id": model_id_available
                    })
                else:
                     logging.debug(f"  '{model_id_available}' is already installed. Skipping.")

            else:
                 missing_attrs = []
                 if not hasattr(pkg_available, 'from_code'): missing_attrs.append('from_code')
                 if not hasattr(pkg_available, 'to_code'): missing_attrs.append('to_code')
                 # Add others if needed for debugging
                 if missing_attrs:
                    logging.debug(f"  Skipping available pkg #{packages_processed_count} due to missing attributes: {', '.join(missing_attrs)}")

         except Exception as pkg_proc_err:
             logging.warning(f"Error processing available package #{packages_processed_count} ('{model_id_available}'): {pkg_proc_err}", exc_info=True)
             continue

    logging.info(f"Processed {packages_processed_count} available packages. Added {packages_added_count} to the final list.")
    return sorted(models_for_frontend, key=lambda x: (x["from_name"], x["to_name"]))


# --- Final download_worker (No cache clearing calls, reliance on env var) ---
def download_worker():
    """Worker thread to process downloads using package object from queue."""
    global download_status
    while True:
        queue_item = download_queue.get()
        if queue_item is None: break
        model_id = queue_item.get('id'); package_to_download = queue_item.get('package_obj')
        if not model_id or not package_to_download:
            logging.error(f"Worker received invalid queue item: {queue_item}"); download_queue.task_done(); continue

        logging.info(f"Starting download process for model: {model_id}")
        download_status[model_id] = {"status": "downloading", "progress": 0, "message": "Starting download..."}
        download_path = None
        try:
            download_status[model_id] = {"status": "downloading", "progress": 30, "message": "Downloading package..."}
            logging.info(f"[{model_id}] Calling package download method...")
            # The package_to_download object knows its download links and where it *should* go based on settings/env var
            download_path = package_to_download.download()
            if not download_path or not os.path.exists(download_path): raise Exception("Download failed. Path not returned or file does not exist.")
            logging.info(f"[{model_id}] Download successful. Path: {download_path}")
            download_status[model_id] = {"status": "installing", "progress": 70, "message": "Installing package..."}
            logging.info(f"[{model_id}] Installing package from path: {download_path}")
            # The install function should use the data directory set by the environment variable
            argostranslate.package.install_from_path(download_path)
            logging.info(f"Successfully installed model: {model_id}")

            # --- Force language reload after successful install ---
            # This should refresh the *in-memory* list of installed languages/models
            try:
                logging.info(f"[{model_id}] Forcing reload of installed languages...")
                argostranslate.translate.load_installed_languages() # Removed force=True
                logging.info(f"[{model_id}] Languages reloaded.")
            except Exception as reload_err:
                logging.warning(f"[{model_id}] Error reloading languages after install: {reload_err}", exc_info=True)
            # --- End Force reload ---

            download_status[model_id] = {"status": "completed", "progress": 100, "message": "Model installed successfully!"}
        except Exception as e:
            error_message = f"Error processing model {model_id}: {e}"
            logging.error(error_message, exc_info=True); user_error_msg = f"Error: {e}"
            if "Connection refused" in str(e): user_error_msg = "Error: Connection refused (server down?)"
            if "Network is unreachable" in str(e): user_error_msg = "Error: Network unreachable."
            if isinstance(e, ValueError) and "metadata not found" in str(e): user_error_msg = "Error: Model details not found (index refresh needed?)"
            download_status[model_id] = {"status": "error", "progress": 0, "message": user_error_msg}
        finally:
            if download_path and os.path.exists(download_path):
                try: os.remove(download_path); logging.info(f"[{model_id}] Removed downloaded package file: {download_path}")
                except Exception as rm_err: logging.warning(f"[{model_id}] Failed to remove downloaded package file {download_path}: {rm_err}")
            download_queue.task_done(); package_to_download = None


# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/languages')
def get_languages():
    installed = get_installed_languages_formatted()
    return jsonify({"installed": installed})

@app.route('/api/models/installed')
def get_installed_models_route():
    return jsonify(get_installed_models_formatted())

@app.route('/api/models/available')
def get_available_models_route():
    logging.info("Route /api/models/available requested.")
    available_models = get_available_models_formatted()
    logging.info(f"Route /api/models/available returning {len(available_models)} models.")
    return jsonify(available_models)

# app.py
# ... (other imports) ...
from langdetect import detect as langdetect_detect, LangDetectException # Import langdetect

# ... (Flask app setup, helpers, workers etc.) ...

@app.route('/api/translate', methods=['POST'])
def translate_text():
    """Handles translation requests, including auto-detect."""
    detected_language_name = None # Variable to store detected language name
    try:
        data = request.get_json()
        text = data.get('text', '')
        source_lang_code = data.get('source_lang', '') # Keep original request code
        target_lang_code = data.get('target_lang', '')

        if not text or not source_lang_code or not target_lang_code:
            logging.error(f"Translate request missing fields: text={bool(text)}, src={source_lang_code}, tgt={target_lang_code}")
            return jsonify({"error": "Missing required fields: text, source_lang, target_lang"}), 400

        logging.info(f"Received translation request: {source_lang_code} -> {target_lang_code}, text length: {len(text)}")

        actual_source_code = source_lang_code # Start with the requested code

        # --- Auto Detection Logic ---
        if source_lang_code == 'auto':
            if len(text.strip()) < 10: # Too short for reliable detection
                logging.warning("Text too short for auto-detection. Cannot translate.")
                # Return error or default to English? Let's return error for now.
                return jsonify({"error": "Input text too short for language auto-detection."}), 400
            try:
                # Limit text length sent to detection for performance
                text_to_detect = text[:1000]
                detected_code = langdetect_detect(text_to_detect)
                actual_source_code = detected_code # Use the detected code for translation
                # Try to get the full name for display (best effort)
                try:
                    all_langs = argostranslate.translate.get_installed_languages()
                    detected_lang_obj = next((l for l in all_langs if l.code == detected_code), None)
                    if detected_lang_obj:
                         detected_language_name = f"{detected_lang_obj.name} ({detected_code})"
                    else:
                         detected_language_name = f"Code: {detected_code}" # Fallback if full name not found
                except Exception: # Ignore errors getting full name
                     detected_language_name = f"Code: {detected_code}"

                logging.info(f"Auto-detected source language: {detected_language_name}")

            except LangDetectException:
                logging.error("Language detection failed. Cannot translate with 'auto'.")
                return jsonify({"error": "Language detection failed. Please select a source language."}), 400
            except Exception as detect_err:
                logging.error(f"Unexpected error during language detection: {detect_err}", exc_info=True)
                return jsonify({"error": f"Internal error during language detection: {detect_err}"}), 500
        # --- End Auto Detection ---

        # Proceed with translation using actual_source_code
        installed_languages = argostranslate.translate.get_installed_languages()
        source = next((lang for lang in installed_languages if lang.code == actual_source_code), None)
        target = next((lang for lang in installed_languages if lang.code == target_lang_code), None)

        if not source:
             logging.error(f"Required source language '{actual_source_code}' not installed.")
             # Provide a more specific error if auto-detect was used
             if source_lang_code == 'auto':
                 err_msg = f"Detected language ({detected_language_name or actual_source_code}) model not installed."
             else:
                 err_msg = f"Source language ({actual_source_code}) model not installed."
             return jsonify({"error": err_msg}), 404
        if not target:
             logging.error(f"Target language '{target_lang_code}' not installed.")
             return jsonify({"error": f"Target language ({target_lang_code}) model not installed."}), 404

        translation = source.get_translation(target)
        if translation is None:
            logging.error(f"No translation model installed for {actual_source_code} -> {target_lang_code}")
            return jsonify({"error": f"No translation model installed for {actual_source_code} -> {target_lang_code}"}), 404

        translated_text = translation.translate(text)
        logging.info(f"Translation successful ({actual_source_code} -> {target_lang_code}), output length: {len(translated_text)}")

        # Return detected language info if auto was used
        response_data = {"translated_text": translated_text}
        if source_lang_code == 'auto' and detected_language_name:
            response_data["detected_language"] = detected_language_name

        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Translation error: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred during translation: {e}"}), 500


@app.route('/api/models/download', methods=['POST'])
def download_model():
    global download_thread, download_status, download_queue, last_available_packages_cache
    data = request.get_json(); model_id = data.get('id')
    if not model_id: logging.error("Download request missing model 'id'"); return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400
    if not isinstance(model_id, str) or '_' not in model_id: logging.error(f"Download request received invalid model id format: {model_id}"); return jsonify({"error": "Invalid model 'id' format."}), 400
    current_status = download_status.get(model_id, {}).get('status')
    if current_status in ['queued', 'downloading', 'installing']: logging.warning(f"Model {model_id} download/install already in progress (Status: {current_status})."); return jsonify({"message": f"Model {model_id} {current_status}."}), 409
    package_to_queue = None
    logging.debug(f"Searching for model '{model_id}' in cached list of {len(last_available_packages_cache)} available packages.")
    for pkg in last_available_packages_cache:
        if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id: package_to_queue = pkg; logging.info(f"Found package object for '{model_id}' in cache."); break
    if not package_to_queue:
        logging.error(f"Could not find package object for '{model_id}' in the cached available list. Refreshing cache once...")
        get_available_models_formatted()
        logging.debug(f"Refreshed cache. Searching again for model '{model_id}' in cached list of {len(last_available_packages_cache)} packages.")
        for pkg in last_available_packages_cache:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id: package_to_queue = pkg; logging.info(f"Found package object for '{model_id}' after refreshing cache."); break
        if not package_to_queue: logging.error(f"Still could not find package object for '{model_id}' after refresh."); return jsonify({"error": f"Model '{model_id}' metadata not found. Please refresh the model list and try again."}), 404
    if download_thread is None or not download_thread.is_alive(): logging.info("Starting download worker thread."); download_thread = threading.Thread(target=download_worker, daemon=True); download_thread.start()
    queue_item = {"id": model_id, "package_obj": package_to_queue}
    download_queue.put(queue_item); download_status[model_id] = {"status": "queued", "progress": 0, "message": "Download queued..."}
    logging.info(f"Queued download for model: {model_id}")
    return jsonify({"message": f"Download initiated for model {model_id}. Check status endpoint.", "id": model_id}), 202

@app.route('/api/download/status/<model_id>')
def get_download_status(model_id):
    status_info = download_status.get(model_id)
    if status_info: return jsonify(status_info)
    else: logging.debug(f"Status request for unknown/completed model ID: {model_id}"); return jsonify({"status": "not_found", "message": "Status not found for this ID."}), 404

@app.route('/api/models/delete', methods=['POST'])
def delete_model():
    try:
        data = request.get_json(); model_id = data.get('id')
        if not model_id: logging.error("Delete model request missing 'id'"); return jsonify({"error": "Missing model 'id' (e.g., 'en_es')"}), 400
        parts = model_id.split('_');
        if len(parts) != 2: logging.error(f"Delete model request invalid id format: {model_id}"); return jsonify({"error": "Invalid model 'id' format. Should be 'fromCode_toCode'"}), 400
        from_code, to_code = parts
        installed_packages = argostranslate.package.get_installed_packages()
        package_to_delete = None
        for pkg in installed_packages:
            if hasattr(pkg, 'package_type') and pkg.package_type == "translate" and \
               hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
               pkg.from_code == from_code and pkg.to_code == to_code: package_to_delete = pkg; break
        if package_to_delete:
            logging.info(f"Attempting to uninstall model: {model_id}"); argostranslate.package.uninstall(package_to_delete)
            # Force language reload after uninstall
            try: argostranslate.translate.load_installed_languages(); logging.info(f"[{model_id}] Languages reloaded after delete.")
            except Exception as reload_err: logging.warning(f"[{model_id}] Error reloading languages after delete: {reload_err}", exc_info=True)
            if model_id in download_status: del download_status[model_id]
            logging.info(f"Successfully uninstalled model: {model_id}"); return jsonify({"message": f"Model {model_id} deleted successfully."}), 200
        else: logging.warning(f"Model {model_id} not found for deletion."); return jsonify({"error": f"Model {model_id} not found or is not installed."}), 404
    except Exception as e: logging.error(f"Error deleting model {model_id}: {e}", exc_info=True); return jsonify({"error": f"An internal error occurred while deleting: {e}"}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    logging.info("Shutdown endpoint requested.")
    global download_queue
    if download_queue: download_queue.put(None)
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None: logging.error('Not running with the Werkzeug Server. Cannot shutdown programmatically.'); return jsonify({"error": "Server cannot be shut down programmatically."}), 500
    shutdown_thread = threading.Thread(target=func, name="FlaskShutdownThread"); shutdown_thread.start()
    logging.info("Flask server shutdown initiated."); return jsonify({"message": "Shutting down server..."})

# --- Main Execution ---
if __name__ == '__main__':
    if download_thread is None or not download_thread.is_alive():
        logging.info("Starting download worker thread on app start.")
        download_thread = threading.Thread(target=download_worker, daemon=True)
        download_thread.start()

    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)