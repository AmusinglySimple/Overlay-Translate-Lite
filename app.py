# app.py — Lite version (no performance metrics, no psutil)
import os
import sys
import configparser
import logging
import time
import json
import threading
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, Future
from flask import Flask, render_template, request, jsonify, Response
from functools import lru_cache, wraps
from utils.config import DEFAULT_MAX_INPUT_CHARS
from utils.validators import (
    validate_language_code,
    sanitize_text_input,
    validate_json_safe_string
)

# --- Application Start Time ---
start_time = time.time()

# --- Configuration Loading ---
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.ini')

DEFAULT_DATA_DIR = os.path.join(script_dir, ".argos-translate-data")
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2
DEFAULT_CACHE_SIZE = 256

config = configparser.ConfigParser()

if not os.path.exists(config_path):
    logging.info(f"Configuration file not found at {config_path}. Creating default config.")
    try:
        config['General'] = {
            '# data_dir': ''
        }
        config['Downloads'] = {
            'max_concurrent_downloads': str(DEFAULT_MAX_CONCURRENT_DOWNLOADS)
        }
        config['Translation'] = {
            'max_input_chars': str(DEFAULT_MAX_INPUT_CHARS),
            'lru_cache_size': str(DEFAULT_CACHE_SIZE)
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        config = configparser.ConfigParser()
    except OSError as e:
        logging.error(f"Failed to create default config: {e}")
        config = configparser.ConfigParser()

try:
    config.read(config_path)
except configparser.Error as e:
    logging.error(f"Error reading config: {e}")
    config = configparser.ConfigParser()

def get_config_value(section, key, default):
    return config.get(section, key, fallback=default)

# --- Determine effective_data_dir ---
env_data_dir = os.environ.get('ARGOSTRANSLATE_DATA_DIR')
config_data_dir = get_config_value('General', 'data_dir', None)

if env_data_dir:
    effective_data_dir = env_data_dir
elif config_data_dir:
    effective_data_dir = config_data_dir
else:
    effective_data_dir = DEFAULT_DATA_DIR

os.environ['ARGOSTRANSLATE_DATA_DIR'] = effective_data_dir
package_data_dir = os.path.join(effective_data_dir, "packages")

try:
    os.makedirs(package_data_dir, exist_ok=True)
    if not os.access(effective_data_dir, os.W_OK) or not os.access(package_data_dir, os.W_OK):
        raise OSError(f"Data directory '{effective_data_dir}' is not writable.")
except OSError as e:
    sys.exit(f"Error: {e}.")

# --- Imports dependent on environment variable ---
from langdetect import detect as langdetect_detect
try:
    from langdetect.lang_detect_exception import LangDetectException
except ImportError:
    LangDetectException = Exception

import argostranslate.package
import argostranslate.translate
import argostranslate.settings

try:
    from argostranslate.package import PackageFormatError
except ImportError:
    PackageFormatError = None

# --- Global Variables & Threading ---
app = Flask(__name__)

# Suppress Flask/Werkzeug noise
for _log_name in ('werkzeug', 'flask.cli', 'flask.app'):
    logging.getLogger(_log_name).propagate = False

download_status = {}
download_status_lock = threading.Lock()

max_workers_str = get_config_value('Downloads', 'max_concurrent_downloads', str(DEFAULT_MAX_CONCURRENT_DOWNLOADS))
try:
    max_workers = int(max_workers_str)
    if max_workers <= 0:
        max_workers = DEFAULT_MAX_CONCURRENT_DOWNLOADS
except ValueError:
    max_workers = DEFAULT_MAX_CONCURRENT_DOWNLOADS

download_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='DownloadWorker')
active_futures = {}
last_available_packages_cache = []

cache_size_str = get_config_value('Translation', 'lru_cache_size', str(DEFAULT_CACHE_SIZE))
try:
    translation_cache_size = int(cache_size_str)
    if translation_cache_size < 0:
        translation_cache_size = 0
except ValueError:
    translation_cache_size = DEFAULT_CACHE_SIZE

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
ERR_PACKAGE_FORMAT = "PACKAGE_FORMAT_ERROR"


# --- Helper Functions ---

def update_download_status(model_id, status, progress, message):
    with download_status_lock:
        download_status[model_id] = {"status": status, "progress": progress, "message": message}

def get_installed_languages_formatted():
    try:
        argostranslate.translate.load_installed_languages()
        installed = argostranslate.translate.get_installed_languages()
        formatted_list = []
        for lang in installed:
            if hasattr(lang, 'code') and hasattr(lang, 'name'):
                formatted_list.append({"code": lang.code, "name": lang.name})
        return sorted(formatted_list, key=lambda x: x["name"])
    except Exception as e:
        logging.error(f"Error getting installed languages: {e}", exc_info=True)
        return []

def get_installed_models_formatted():
    models = []
    try:
        packages = argostranslate.package.get_installed_packages()
        for pkg in packages:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code'):
                models.append({
                    "from_code": pkg.from_code, "to_code": pkg.to_code,
                    "from_name": getattr(pkg, 'from_name', pkg.from_code),
                    "to_name": getattr(pkg, 'to_name', pkg.to_code),
                    "package_version": getattr(pkg, 'package_version', 'N/A'),
                    "id": f"{pkg.from_code}_{pkg.to_code}"
                })
        return sorted(models, key=lambda x: (x["from_name"], x["to_name"]))
    except Exception as e:
        logging.error(f"Error processing installed packages: {e}", exc_info=True)
        return []

def get_available_models_formatted():
    global last_available_packages_cache
    models_for_frontend = []
    installed_ids = {m['id'] for m in get_installed_models_formatted()}

    try:
        argostranslate.package.update_package_index()
        current_available_packages = argostranslate.package.get_available_packages()
        last_available_packages_cache = current_available_packages
    except Exception as e:
        logging.error(f"Error updating package index: {e}", exc_info=True)
        last_available_packages_cache = []
        return []

    for pkg_available in current_available_packages:
        try:
            if hasattr(pkg_available, 'from_code') and hasattr(pkg_available, 'to_code'):
                model_id = f"{pkg_available.from_code}_{pkg_available.to_code}"
                if model_id not in installed_ids:
                    models_for_frontend.append({
                        "from_code": pkg_available.from_code, "to_code": pkg_available.to_code,
                        "from_name": pkg_available.from_name, "to_name": pkg_available.to_name,
                        "package_version": getattr(pkg_available, 'package_version', 'N/A'),
                        "id": model_id, "size_mb": None
                    })
        except Exception:
            continue

    return sorted(models_for_frontend, key=lambda x: (x["from_name"], x["to_name"]))


# --- Download Worker ---
def download_and_install_package(model_id, package_to_download):
    global active_futures
    thread_name = threading.current_thread().name
    logging.info(f"[{thread_name}][{model_id}] Starting download.")
    update_download_status(model_id, "downloading", 0, "Starting download...")
    download_path = None
    try:
        update_download_status(model_id, "downloading", 10, "Downloading package...")

        download_done = threading.Event()
        def _pulse_progress():
            tick = 0
            while not download_done.is_set():
                progress = 10 + min(38, int(tick * 1.5))
                update_download_status(model_id, "downloading", progress, "Downloading package...")
                download_done.wait(2.0)
                tick += 1

        pulse_thread = threading.Thread(target=_pulse_progress, daemon=True)
        pulse_thread.start()
        download_path = package_to_download.download()
        download_done.set()
        pulse_thread.join(timeout=2)

        if not download_path or not os.path.exists(download_path):
            raise FileNotFoundError("Download finished but package file not found.")

        update_download_status(model_id, "installing", 60, "Installing model...")
        argostranslate.package.install_from_path(download_path)

        update_download_status(model_id, "installing", 90, "Loading language data...")
        try:
            argostranslate.translate.load_installed_languages()
        except Exception as reload_err:
            logging.warning(f"Error reloading languages: {reload_err}")

        update_download_status(model_id, "completed", 100, "Model installed successfully!")
        return True

    except Exception as e:
        logging.error(f"Error processing model {model_id}: {e}", exc_info=True)
        update_download_status(model_id, "error", 0, f"Error: {e}")
        return False
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass
        with download_status_lock:
            if model_id in active_futures:
                del active_futures[model_id]


# --- Flask Routes ---

@app.route('/')
def index():
    max_chars_str = get_config_value('Translation', 'max_input_chars', str(DEFAULT_MAX_INPUT_CHARS))
    try:
        max_chars = int(max_chars_str)
    except ValueError:
        max_chars = DEFAULT_MAX_INPUT_CHARS
    return render_template('index.html', max_input_chars=max_chars)

@app.route('/api/languages')
def get_languages():
    return jsonify({"installed": get_installed_languages_formatted()})

@app.route('/api/models/installed')
def get_installed_models_route():
    return jsonify(get_installed_models_formatted())

@app.route('/api/models/available')
def get_available_models_route():
    return jsonify(get_available_models_formatted())

# --- Translation Cache ---
@lru_cache(maxsize=translation_cache_size)
def perform_translation_cached(from_code, to_code, text):
    installed_languages = argostranslate.translate.get_installed_languages()
    source = next((lang for lang in installed_languages if lang.code == from_code), None)
    target = next((lang for lang in installed_languages if lang.code == to_code), None)
    if not source or not target:
        raise ValueError(f"Source ({from_code}) or Target ({to_code}) language not found.")
    translation = source.get_translation(target)
    if translation is None:
        raise ValueError(f"Translation model {from_code}->{to_code} not found.")
    return translation.translate(text)


@app.route('/api/translate', methods=['POST'])
def translate_text():
    detected_language_name = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400

        text = data.get('text', '')
        source_lang_code = data.get('source_lang', '')
        target_lang_code = data.get('target_lang', '')

        if not all([text, source_lang_code, target_lang_code]):
            missing = [k for k, v in {'text': text, 'source_lang': source_lang_code, 'target_lang': target_lang_code}.items() if not v]
            return jsonify({"error_code": ERR_MISSING_FIELD, "message": f"Missing: {', '.join(missing)}"}), 400

        valid_text, text_error = validate_json_safe_string(text, max_length=10000)
        if not valid_text:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": f"Invalid text: {text_error}"}), 400

        text = sanitize_text_input(text, max_length=10000, allow_newlines=True, strip_html=False)

        valid_source, source_error = validate_language_code(source_lang_code)
        if not valid_source and source_lang_code != 'auto':
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": f"Invalid source language: {source_error}"}), 400

        valid_target, target_error = validate_language_code(target_lang_code)
        if not valid_target:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": f"Invalid target language: {target_error}"}), 400

        max_chars_str = get_config_value('Translation', 'max_input_chars', str(DEFAULT_MAX_INPUT_CHARS))
        try:
            max_chars = int(max_chars_str)
        except ValueError:
            max_chars = DEFAULT_MAX_INPUT_CHARS
        if len(text) > max_chars:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": f"Input exceeds {max_chars} chars."}), 413

        actual_source_code = source_lang_code

        if source_lang_code == 'auto':
            if len(text.strip()) < 10:
                return jsonify({"error_code": ERR_LANG_DETECT_FAILED, "message": "Text too short for auto-detect."}), 400
            try:
                detected_code = langdetect_detect(text[:1000])
                actual_source_code = detected_code
                try:
                    langs = argostranslate.translate.get_installed_languages()
                    obj = next((l for l in langs if l.code == detected_code), None)
                    detected_language_name = f"{obj.name} ({detected_code})" if obj else f"Code: {detected_code}"
                except (StopIteration, AttributeError):
                    detected_language_name = f"Code: {detected_code}"
            except LangDetectException:
                return jsonify({"error_code": ERR_LANG_DETECT_FAILED, "message": "Detection failed."}), 400

        langs = argostranslate.translate.get_installed_languages()
        source = next((l for l in langs if l.code == actual_source_code), None)
        target = next((l for l in langs if l.code == target_lang_code), None)

        if not source:
            return jsonify({"error_code": ERR_LANG_NOT_INSTALLED, "message": f"Source model ({actual_source_code}) not installed."}), 404
        if not target:
            return jsonify({"error_code": ERR_LANG_NOT_INSTALLED, "message": f"Target model ({target_lang_code}) not installed."}), 404

        if source.get_translation(target) is None:
            return jsonify({"error_code": ERR_MODEL_NOT_INSTALLED, "message": f"Model {actual_source_code}->{target_lang_code} not installed."}), 404

        if translation_cache_size > 0:
            translated_text = perform_translation_cached(actual_source_code, target_lang_code, text)
        else:
            translation = source.get_translation(target)
            translated_text = translation.translate(text)

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
    if not data:
        return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400
    model_id = data.get('id')
    if not model_id or not isinstance(model_id, str) or '_' not in model_id:
        return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid model 'id'."}), 400

    with download_status_lock:
        current_status = download_status.get(model_id, {}).get('status')
        is_active = model_id in active_futures and not active_futures[model_id].done()

    if current_status in ['queued', 'downloading', 'installing'] or is_active:
        return jsonify({"error_code": ERR_ALREADY_DOWNLOADING, "message": f"Model {model_id} already processing."}), 409

    package_to_queue = None
    for pkg in last_available_packages_cache:
        if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id:
            package_to_queue = pkg
            break

    if not package_to_queue:
        get_available_models_formatted()
        for pkg in last_available_packages_cache:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and f"{pkg.from_code}_{pkg.to_code}" == model_id:
                package_to_queue = pkg
                break

    if not package_to_queue:
        return jsonify({"error_code": ERR_MODEL_NOT_FOUND, "message": f"Model '{model_id}' not found."}), 404

    try:
        update_download_status(model_id, "queued", 0, "Download queued...")
        future = download_executor.submit(download_and_install_package, model_id, package_to_queue)
        with download_status_lock:
            active_futures[model_id] = future
        return jsonify({"message": f"Download initiated for {model_id}.", "id": model_id}), 202
    except Exception as e:
        update_download_status(model_id, "error", 0, f"Failed to start: {e}")
        return jsonify({"error_code": ERR_SERVER_ERROR, "message": f"Failed to start: {e}"}), 500


@app.route('/api/download/status/<model_id>')
def get_download_status(model_id):
    with download_status_lock:
        status_info = download_status.get(model_id)
        is_active = model_id in active_futures and not active_futures[model_id].done()
    if status_info:
        return jsonify(status_info)
    elif is_active:
        return jsonify({"status": "downloading", "progress": 0, "message": "Processing..."})
    else:
        return jsonify({"status": "not_found", "message": "Status not found."}), 404


@app.route('/api/download/stream/<model_id>')
def stream_download_status(model_id):
    def generate():
        yield "data: " + json.dumps({'status': 'connected', 'progress': 0, 'message': 'Connecting...'}) + "\n\n"
        last_sent = None
        elapsed = 0
        interval = 0.8
        while elapsed < 300:
            with download_status_lock:
                status_info = download_status.get(model_id)
                is_active = model_id in active_futures and not active_futures[model_id].done()
            current = json.dumps(status_info) if status_info else None
            if current and current != last_sent:
                last_sent = current
                yield "data: " + current + "\n\n"
                if status_info and status_info.get('status') in ('completed', 'error'):
                    break
            elif not status_info and not is_active and elapsed > 3:
                yield "data: " + json.dumps({'status': 'not_found', 'progress': 0, 'message': 'No active download'}) + "\n\n"
                break
            time.sleep(interval)
            elapsed += interval

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})


@app.route('/api/models/delete', methods=['POST'])
def delete_model():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid JSON"}), 400
        model_id = data.get('id')
        if not model_id:
            return jsonify({"error_code": ERR_MISSING_FIELD, "message": "Missing 'id'"}), 400
        parts = model_id.split('_')
        if len(parts) != 2:
            return jsonify({"error_code": ERR_INVALID_INPUT, "message": "Invalid 'id'"}), 400
        from_code, to_code = parts

        installed_packages = argostranslate.package.get_installed_packages()
        package_to_delete = None
        for pkg in installed_packages:
            if hasattr(pkg, 'from_code') and hasattr(pkg, 'to_code') and pkg.from_code == from_code and pkg.to_code == to_code:
                package_to_delete = pkg
                break

        if package_to_delete:
            argostranslate.package.uninstall(package_to_delete)
            try:
                argostranslate.translate.load_installed_languages()
            except Exception:
                pass
            with download_status_lock:
                if model_id in download_status:
                    del download_status[model_id]
                if model_id in active_futures:
                    del active_futures[model_id]
            if translation_cache_size > 0:
                perform_translation_cached.cache_clear()
            return jsonify({"message": f"Model {model_id} deleted."}), 200
        else:
            return jsonify({"error_code": ERR_MODEL_NOT_FOUND, "message": f"Model {model_id} not found."}), 404
    except Exception as e:
        logging.error(f"Error deleting model {model_id}: {e}", exc_info=True)
        return jsonify({"error_code": ERR_DELETE_FAILED, "message": f"Error: {e}"}), 500


@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "ok",
        "uptime_seconds": int(time.time() - start_time),
        "active_downloads": len([f for f in active_futures.values() if not f.done()]),
        "argos_data_dir": str(argostranslate.settings.data_dir),
    })
