# app.py
import os
import sys
import configparser
import logging
import time
import json
import threading
from queue import Queue, Empty # Import Empty for timeout handling
from concurrent.futures import ThreadPoolExecutor, Future
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

# --- Basic Logging Setup (before config) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

# --- Configuration Loading ---
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.ini')

# Default settings
DEFAULT_DATA_DIR = os.path.join(script_dir, ".argos-translate-data")
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2
DEFAULT_MAX_INPUT_CHARS = 5000

# --- Auto-create config.ini if it doesn't exist ---
config = configparser.ConfigParser()

if not os.path.exists(config_path):
    logging.info(f"Configuration file not found at {config_path}. Creating default config.")
    try:
        config['General'] = {
            '# data_dir_comment0': '; Set the location for Argos Translate data and models.',
            '# data_dir_comment1': f'; If this line is commented out or empty, the app will use the default directory:',
            '# data_dir_comment2': f'; \'{DEFAULT_DATA_DIR}\' (relative to the script location).',
            '# data_dir_comment3': f'; To use a different location, uncomment the line below and set the path.',
            '# data_dir_comment4': f'; NOTE: The ARGOSTRANSLATE_DATA_DIR environment variable takes highest precedence.',
            '# data_dir': ''
        }
        config['Downloads'] = {
            '# max_concurrent_downloads_comment': '; Maximum number of model downloads to run concurrently.',
            'max_concurrent_downloads': str(DEFAULT_MAX_CONCURRENT_DOWNLOADS)
        }
        config['Translation'] = {
             '# max_input_chars_comment': '; Character limit for input text (primarily enforced by frontend)',
             'max_input_chars': str(DEFAULT_MAX_INPUT_CHARS)
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        logging.info(f"Default configuration file created at {config_path}")
        config = configparser.ConfigParser() # Re-initialize to read it properly

    except OSError as e:
        logging.error(f"Failed to create default configuration file at {config_path}: {e}. Proceeding with built-in defaults.")
        config = configparser.ConfigParser()

# --- Read config (whether pre-existing or just created) ---
try:
    files_read = config.read(config_path)
    if files_read:
         logging.info(f"Loaded configuration from {config_path}")
    elif not os.path.exists(config_path):
         logging.warning(f"Config file {config_path} not found and creation might have failed. Using built-in defaults.")
    else:
         logging.warning(f"Config file {config_path} exists but could not be read or is empty. Using built-in defaults.")
except configparser.Error as e:
    logging.error(f"Error reading configuration file {config_path}: {e}. Using built-in defaults.")
    config = configparser.ConfigParser()

# Helper to get config value with fallback
def get_config_value(section, key, default):
    return config.get(section, key, fallback=default)

# --- Determine effective_data_dir ---
env_data_dir = os.environ.get('ARGOSTRANSLATE_DATA_DIR')
config_data_dir = get_config_value('General', 'data_dir', None)

if env_data_dir:
    effective_data_dir = env_data_dir
    logging.info("Using ARGOSTRANSLATE_DATA_DIR from environment variable.")
elif config_data_dir:
    effective_data_dir = config_data_dir
    logging.info(f"Using data_dir from config.ini: {effective_data_dir}")
else:
    effective_data_dir = DEFAULT_DATA_DIR
    logging.info(f"Using default data directory: {effective_data_dir}")

os.environ['ARGOSTRANSLATE_DATA_DIR'] = effective_data_dir
package_data_dir = os.path.join(effective_data_dir, "packages")

# Ensure the directory exists and is writable
try:
    os.makedirs(package_data_dir, exist_ok=True)
    if not os.access(effective_data_dir, os.W_OK) or \
       not os.access(package_data_dir, os.W_OK):
        raise OSError(f"Data directory '{effective_data_dir}' or its 'packages' subdirectory is not writable.")
    logging.info(f"Confirmed data directory is writable: {effective_data_dir}")
except OSError as e:
    logging.error(f"CRITICAL ERROR: Data directory setup failed: {e}", exc_info=True)
    sys.exit(f"Error: {e}. Please ensure the directory exists and the application has write permissions.")

# --- Imports dependent on environment variable ---
from langdetect import detect as langdetect_detect

try:
    # Para versiones donde existe lang_detect_exception
    from langdetect.lang_detect_exception import LangDetectException
except ImportError:
    # Si no existe, usamos Exception normal
    LangDetectException = Exception
import argostranslate.package
import argostranslate.translate
import argostranslate.settings

# Log effective settings AFTER imports
logging.info(f"Argos Translate effective data directory: {argostranslate.settings.data_dir}")
logging.info(f"Argos Translate effective package directory: {argostranslate.settings.package_data_dir}")

# --- Global Variables & Threading ---
app = Flask(__name__)
download_status = {}
download_status_lock = threading.Lock()

max_workers_str = get_config_value('Downloads', 'max_concurrent_downloads', str(DEFAULT_MAX_CONCURRENT_DOWNLOADS))
try:
    max_workers = int(max_workers_str)
    if max_workers <= 0:
        logging.warning(f"Invalid max_concurrent_downloads value ({max_workers_str}), defaulting to {DEFAULT_MAX_CONCURRENT_DOWNLOADS}.")
        max_workers = DEFAULT_MAX_CONCURRENT_DOWNLOADS
except ValueError:
    logging.warning(f"Non-integer max_concurrent_downloads value ('{max_workers_str}'), defaulting to {DEFAULT_MAX_CONCURRENT_DOWNLOADS}.")
    max_workers = DEFAULT_MAX_CONCURRENT_DOWNLOADS

logging.info(f"Initializing download executor with max_workers={max_workers}")
download_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='DownloadWorker')
active_futures = {}
shutdown_signal_queue = Queue()
last_available_packages_cache = []

# --- Error Codes ---
ERR_MISSING_FIELD = "MISSING_FIELD"
ERR_TRANSLATION_FAILED = "TRANSLATION_FAILED"
ERR_LANG_DETECT_FAILED = "LANG_DETECT_FAILED"
ERR_LANG_NOT_INSTALLED = "LANG_NOT_INSTALLED"
ERR_MODEL_NOT_INSTALLED = "MODEL_NOT_INSTALLED"
ERR_MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
ERR_DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
ERR_INSTALL_FAILED = "INSTALL_FAILED"
ERR_DELETE_FAILED = "DELETE_FAILED"
ERR_INVALID_INPUT = "INVALID_INPUT"
ERR_SERVER_ERROR = "SERVER_ERROR"
ERR_ALREADY_DOWNLOADING = "ALREADY_DOWNLOADING"
ERR_WRITE_PERMISSION = "WRITE_PERMISSION"

# --- Helper Functions ---

def update_download_status(model_id, status, progress, message):
    with download_status_lock:
        download_status[model_id] = {"status": status, "progress": progress, "message": message}
    logging.debug(f"Status updated for {model_id}: {status} - {progress}% - {message}")

def get_installed_languages_formatted():
    try:
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

def get_installed_models_formatted():
    models = []
    try:
        packages = argostranslate.package.get_installed_packages()
        logging.info(f"get_installed_models_formatted: Found {len(packages)} raw packages.")
        processed_count = 0
        added_count = 0
        for i, pkg in enumerate(packages):
            processed_count += 1
            # --- CORRECTION: Relaxed filtering condition ---
            # Only require from_code and to_code for it to be considered a listable model
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code'):
                from_code = pkg.from_code
                to_code = pkg.to_code
                from_name = getattr(pkg, 'from_name', from_code)
                to_name = getattr(pkg, 'to_name', to_code)

                models.append({
                    "from_code": from_code, "to_code": to_code,
                    "from_name": from_name, "to_name": to_name,
                    "package_version": getattr(pkg, 'package_version', 'N/A'),
                    "argos_version": getattr(pkg, 'argos_version', 'N/A'),
                    "id": f"{from_code}_{to_code}"
                })
                added_count += 1
                # logging.debug(f" Added installed package {i}: {from_code}_{to_code}") # Keep logging minimal unless debugging
            else:
                # Log if a package was skipped despite being found
                # Avoid logging too much if many non-translate packages exist (e.g., embeddings)
                if not hasattr(pkg, 'from_code') and not hasattr(pkg, 'to_code'):
                     logging.debug(f" Skipping installed package {i} (likely not a translate model): {getattr(pkg, 'metadata', pkg)}")
                else:
                    missing = [a for a in ['from_code', 'to_code'] if not hasattr(pkg, a)]
                    logging.warning(f" Skipping installed package {i} ({getattr(pkg, 'metadata', pkg)}) due to missing: {', '.join(missing)}")


        logging.info(f"get_installed_models_formatted: Processed {processed_count} raw packages, returning {added_count} models.")
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        logging.error(f"Error processing installed packages: {e}", exc_info=True)
        return []


def get_available_models_formatted():
    global last_available_packages_cache
    models_for_frontend = []
    installed_models_list = get_installed_models_formatted()
    installed_ids = {m['id'] for m in installed_models_list}
    logging.info(f"Found {len(installed_ids)} unique installed model IDs for filtering.")

    current_available_packages = []
    try:
        logging.info("Updating package index...")
        argostranslate.package.update_package_index()
        logging.info("Getting available packages...")
        current_available_packages = argostranslate.package.get_available_packages()
        logging.info(f"Found {len(current_available_packages)} raw available packages.")
        last_available_packages_cache = current_available_packages
    except Exception as e:
        logging.error(f"Error updating/getting package index: {e}", exc_info=True)
        last_available_packages_cache = []
        return []

    if not current_available_packages:
         logging.warning("No available packages found after index update.")
         last_available_packages_cache = []
         return []

    logging.info("Filtering available packages...")
    packages_processed_count = 0
    packages_added_count = 0

    for pkg_available in current_available_packages:
         packages_processed_count += 1
         model_id_available = "N/A"
         try:
            # --- CORRECTION: Relaxed filtering condition ---
            # Only require from/to code and names. Don't mandate package_type == "translate".
            if hasattr(pkg_available, 'from_code') and hasattr(pkg_available, 'to_code') and \
               hasattr(pkg_available, 'from_name') and hasattr(pkg_available, 'to_name'):

                model_id_available = f"{pkg_available.from_code}_{pkg_available.to_code}"

                if model_id_available not in installed_ids:
                    pkg_size_mb = None # Placeholder for size
                    # logging.debug(f"  '{model_id_available}' is available. Adding to list.") # Keep logs minimal
                    packages_added_count += 1
                    models_for_frontend.append({
                        "from_code": pkg_available.from_code, "to_code": pkg_available.to_code,
                        "from_name": pkg_available.from_name, "to_name": pkg_available.to_name,
                        "package_version": getattr(pkg_available, 'package_version', 'N/A'),
                        "argos_version": getattr(pkg_available, 'argos_version', 'N/A'),
                        "id": model_id_available, "size_mb": pkg_size_mb
                    })
                # else:
                #    logging.debug(f"  '{model_id_available}' is already installed. Skipping.") # Keep logs minimal

            else:
                 # Log skipped available packages if they seem like they should have worked
                 missing_attrs = [attr for attr in ['from_code', 'to_code', 'from_name', 'to_name'] if not hasattr(pkg_available, attr)]
                 if missing_attrs:
                    logging.debug(f"  Skipping available pkg #{packages_processed_count} due to missing attributes: {', '.join(missing_attrs)} - Pkg: {getattr(pkg_available, 'metadata', pkg_available)}")


         except Exception as pkg_proc_err:
             logging.warning(f"Error processing available package #{packages_processed_count} ('{model_id_available}'): {pkg_proc_err}", exc_info=True)
             continue

    logging.info(f"Processed {packages_processed_count} available packages. Added {packages_added_count} to the final list.")
    return sorted(models_for_frontend, key=lambda x: (x["from_name"], x["to_name"]))

# --- Download Worker Function (for ThreadPoolExecutor) ---
def download_and_install_package(model_id, package_to_download):
    global active_futures
    thread_name = threading.current_thread().name
    logging.info(f"[{thread_name}][{model_id}] Starting download process.")
    update_download_status(model_id, "downloading", 0, "Starting download...")
    download_path = None
    try:
        update_download_status(model_id, "downloading", 30, "Downloading package...")
        logging.info(f"[{thread_name}][{model_id}] Calling package download method...")
        download_path = package_to_download.download()
        if not download_path or not os.path.exists(download_path):
             raise Exception("Download failed or package file not found.")
        logging.info(f"[{thread_name}][{model_id}] Download successful. Path: {download_path}")

        update_download_status(model_id, "installing", 70, "Installing package...")
        logging.info(f"[{thread_name}][{model_id}] Installing package from path: {download_path}")
        argostranslate.package.install_from_path(download_path)
        logging.info(f"[{thread_name}][{model_id}] Successfully installed model.")

        try:
            logging.info(f"[{thread_name}][{model_id}] Reloading installed languages...")
            argostranslate.translate.load_installed_languages() # No force=True
            logging.info(f"[{thread_name}][{model_id}] Languages reloaded.")
        except Exception as reload_err:
            logging.warning(f"[{thread_name}][{model_id}] Error reloading languages after install: {reload_err}", exc_info=True)

        update_download_status(model_id, "completed", 100, "Model installed successfully!")
        return True
    except Exception as e:
        error_message = f"Error processing model {model_id}: {e}"
        logging.error(f"[{thread_name}]{error_message}", exc_info=True)
        user_error_msg = f"Error: {e}"
        if "Connection refused" in str(e) or "timed out" in str(e): user_error_msg = "Error: Connection failed"
        elif "Network is unreachable" in str(e): user_error_msg = "Error: Network unreachable."
        elif isinstance(e, ValueError) and "metadata not found" in str(e): user_error_msg = "Error: Model details missing"
        elif "Permission denied" in str(e) or isinstance(e, OSError) and e.errno == 13: user_error_msg = "Error: Permission denied during install."
        elif "No space left on device" in str(e) or isinstance(e, OSError) and e.errno == 28: user_error_msg = "Error: No space left on device."
        update_download_status(model_id, "error", 0, user_error_msg)
        return False
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
                logging.info(f"[{thread_name}][{model_id}] Removed downloaded package file: {download_path}")
            except Exception as rm_err:
                logging.warning(f"[{thread_name}][{model_id}] Failed to remove {download_path}: {rm_err}")
        with download_status_lock:
             if model_id in active_futures: del active_futures[model_id]


# --- Flask Routes ---

@app.route('/')
def index():
    max_chars_str = get_config_value('Translation', 'max_input_chars', str(DEFAULT_MAX_INPUT_CHARS))
    try: max_chars = int(max_chars_str)
    except ValueError: max_chars = DEFAULT_MAX_INPUT_CHARS
    return render_template('index.html', max_input_chars=max_chars)

@app.route('/api/languages')
def get_languages():
    return jsonify({"installed": get_installed_languages_formatted()})

@app.route('/api/models/installed')
def get_installed_models_route():
    return jsonify(get_installed_models_formatted())

@app.route('/api/models/available')
def get_available_models_route():
    logging.info("Route /api/models/available requested.")
    available = get_available_models_formatted()
    logging.info(f"Route /api/models/available returning {len(available)} models.")
    return jsonify(available)

@app.route('/api/translate', methods=['POST'])
def translate_text():
    detected_language_name = None
    try:
        data = request.get_json()
        if not data: return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400

        text = data.get('text', '')
        source_lang_code = data.get('source_lang', '')
        target_lang_code = data.get('target_lang', '')

        if not all([text, source_lang_code, target_lang_code]):
            missing = [k for k, v in {'text': text, 'source_lang': source_lang_code, 'target_lang': target_lang_code}.items() if not v]
            return jsonify({"error_code": ERR_MISSING_FIELD, "message": f"Missing: {', '.join(missing)}"}), 400

        max_chars_str = get_config_value('Translation', 'max_input_chars', str(DEFAULT_MAX_INPUT_CHARS))
        try: max_chars = int(max_chars_str)
        except ValueError: max_chars = DEFAULT_MAX_INPUT_CHARS
        if len(text) > max_chars:
             return jsonify({"error_code": ERR_INVALID_INPUT, "message": f"Input exceeds {max_chars} chars."}), 413

        logging.info(f"Translate request: {source_lang_code} -> {target_lang_code}, len: {len(text)}")
        actual_source_code = source_lang_code

        if source_lang_code == 'auto':
            if len(text.strip()) < 10: return jsonify({"error_code": ERR_LANG_DETECT_FAILED, "message": "Text too short for auto-detect."}), 400
            try:
                detected_code = langdetect_detect(text[:1000])
                actual_source_code = detected_code
                try:
                    langs = argostranslate.translate.get_installed_languages()
                    obj = next((l for l in langs if l.code == detected_code), None)
                    detected_language_name = f"{obj.name} ({detected_code})" if obj else f"Code: {detected_code}"
                except Exception: detected_language_name = f"Code: {detected_code}"
                logging.info(f"Auto-detected: {detected_language_name}")
            except LangDetectException: return jsonify({"error_code": ERR_LANG_DETECT_FAILED, "message": "Detection failed."}), 400
            except Exception as e: logging.error(f"Detection error: {e}", exc_info=True); return jsonify({"error_code": ERR_SERVER_ERROR, "message": "Detection internal error."}), 500

        langs = argostranslate.translate.get_installed_languages()
        source = next((l for l in langs if l.code == actual_source_code), None)
        target = next((l for l in langs if l.code == target_lang_code), None)

        if not source:
             msg = f"Source model ({detected_language_name or actual_source_code}) not installed." if source_lang_code == 'auto' else f"Source model ({actual_source_code}) not installed."
             return jsonify({"error_code": ERR_LANG_NOT_INSTALLED, "message": msg}), 404
        if not target: return jsonify({"error_code": ERR_LANG_NOT_INSTALLED, "message": f"Target model ({target_lang_code}) not installed."}), 404

        translation = source.get_translation(target)
        if translation is None: return jsonify({"error_code": ERR_MODEL_NOT_INSTALLED, "message": f"Model {actual_source_code}->{target_lang_code} not installed."}), 404

        translated_text = translation.translate(text)
        logging.info(f"Translation success ({actual_source_code}->{target_lang_code}), output len: {len(translated_text)}")
        response_data = {"translated_text": translated_text}
        if source_lang_code == 'auto' and detected_language_name:
            response_data["detected_language"] = detected_language_name
        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Translate error: {e}", exc_info=True)
        return jsonify({"error_code": ERR_TRANSLATION_FAILED, "message": f"Internal translation error: {e}"}), 500


@app.route('/api/models/download', methods=['POST'])
def download_model():
    global last_available_packages_cache, active_futures
    data = request.get_json()
    if not data: return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400
    model_id = data.get('id')
    if not model_id: return jsonify({"error_code": ERR_MISSING_FIELD, "message": "Missing model 'id'"}), 400
    if not isinstance(model_id, str) or '_' not in model_id: return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid model 'id' format."}), 400

    with download_status_lock:
        current_status_info = download_status.get(model_id, {})
        current_status = current_status_info.get('status')
        is_active = model_id in active_futures and not active_futures[model_id].done()

    if current_status in ['queued', 'downloading', 'installing'] or is_active:
        logging.warning(f"Model {model_id} already processing (Status: {current_status}, Active: {is_active}).")
        return jsonify({"error_code": ERR_ALREADY_DOWNLOADING, "message": f"Model {model_id} {current_status or 'processing'}."}), 409

    package_to_queue = None
    for pkg in last_available_packages_cache:
        # No package_type check here anymore for flexibility
        if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id:
            package_to_queue = pkg; break

    if not package_to_queue:
        logging.warning(f"Model '{model_id}' not in cache, refreshing...")
        get_available_models_formatted() # Refresh cache
        for pkg in last_available_packages_cache:
             if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id:
                 package_to_queue = pkg; break

    if not package_to_queue:
        logging.error(f"Model '{model_id}' not found after refresh.")
        return jsonify({"error_code": ERR_MODEL_NOT_FOUND, "message": f"Model '{model_id}' metadata not found."}), 404

    try:
        logging.info(f"Submitting download task for model: {model_id}")
        update_download_status(model_id, "queued", 0, "Download queued...")
        future = download_executor.submit(download_and_install_package, model_id, package_to_queue)
        with download_status_lock: active_futures[model_id] = future
        logging.info(f"Queued download for model: {model_id}")
        return jsonify({"message": f"Download initiated for {model_id}.", "id": model_id}), 202
    except Exception as e:
        logging.error(f"Failed to submit download task for {model_id}: {e}", exc_info=True)
        update_download_status(model_id, "error", 0, f"Failed to start download: {e}")
        return jsonify({"error_code": ERR_SERVER_ERROR, "message": f"Failed to start task: {e}"}), 500

@app.route('/api/download/status/<model_id>')
def get_download_status(model_id):
    with download_status_lock:
        status_info = download_status.get(model_id)
        is_active = model_id in active_futures and not active_futures[model_id].done()
    if status_info:
        if status_info.get('status') in ['completed', 'error'] and is_active:
            logging.warning(f"Status for {model_id} is {status_info.get('status')} but future active? Stale?")
        return jsonify(status_info)
    else:
        if is_active: return jsonify({"status": "downloading", "progress": 0, "message": "Processing..."}) # Best guess
        else: return jsonify({"status": "not_found", "message": "Status not found."}), 404

@app.route('/api/models/delete', methods=['POST'])
def delete_model():
    try:
        data = request.get_json();
        if not data: return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400
        model_id = data.get('id')
        if not model_id: return jsonify({"error_code": ERR_MISSING_FIELD, "message": "Missing model 'id'"}), 400
        parts = model_id.split('_')
        if len(parts) != 2: return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid 'id' format"}), 400
        from_code, to_code = parts

        installed_packages = argostranslate.package.get_installed_packages() # No force=True
        package_to_delete = None
        for pkg in installed_packages:
            # Relaxed check - just need matching codes
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and \
               pkg.from_code == from_code and pkg.to_code == to_code:
                package_to_delete = pkg; break

        if package_to_delete:
            logging.info(f"Attempting to uninstall model: {model_id}")
            argostranslate.package.uninstall(package_to_delete)
            try:
                argostranslate.translate.load_installed_languages() # No force=True
                logging.info(f"[{model_id}] Languages reloaded after delete.")
            except Exception as reload_err:
                logging.warning(f"[{model_id}] Error reloading languages after delete: {reload_err}", exc_info=True)
            with download_status_lock:
                if model_id in download_status: del download_status[model_id]
                if model_id in active_futures: del active_futures[model_id]
            logging.info(f"Successfully uninstalled model: {model_id}")
            return jsonify({"message": f"Model {model_id} deleted."}), 200
        else:
            logging.warning(f"Model {model_id} not found for deletion.")
            return jsonify({"error_code": ERR_MODEL_NOT_FOUND, "message": f"Model {model_id} not found."}), 404
    except OSError as e:
         if e.errno == 13: msg = f"Permission denied deleting model {model_id}."
         else: msg = f"File system error deleting: {e}"
         logging.error(f"{msg} - {e}", exc_info=True)
         return jsonify({"error_code": ERR_DELETE_FAILED, "message": msg}), 500
    except Exception as e:
        logging.error(f"Error deleting model {model_id}: {e}", exc_info=True)
        return jsonify({"error_code": ERR_DELETE_FAILED, "message": f"Internal error deleting: {e}"}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    logging.info("Shutdown endpoint requested.")
    werkzeug_shutdown = request.environ.get('werkzeug.server.shutdown')
    if werkzeug_shutdown is None:
        return jsonify({"error_code": ERR_SERVER_ERROR, "message": "Not running with Werkzeug dev server."}), 500

    def do_shutdown():
        logging.info("Initiating graceful shutdown...")
        logging.info("Shutting down download executor (waiting for tasks)...")
        try:
            download_executor.shutdown(wait=True, cancel_futures=False)
            logging.info("Download executor shut down.")
        except Exception as e: logging.error(f"Executor shutdown error: {e}")
        logging.info("Calling Werkzeug server shutdown...")
        werkzeug_shutdown()
        logging.info("Werkzeug shutdown called.")
        shutdown_signal_queue.put(True)

    threading.Thread(target=do_shutdown, name="ShutdownHandlerThread").start()
    return jsonify({"message": "Shutting down server..."})

# --- Main Execution ---
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    try:
        shutdown_completed = shutdown_signal_queue.get(timeout=30)
        if shutdown_completed: logging.info("Main thread confirms graceful shutdown.")
    except Empty: logging.warning("Main thread timeout waiting for shutdown signal.")
    logging.info("Exiting main thread.")
