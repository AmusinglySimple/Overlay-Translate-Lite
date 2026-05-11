# utils/settings_manager.py — Lite version (no keyring, no AI key management)
"""
Centralized settings management for OverlayTranslate Lite.
Handles configuration, theme management with thread safety.
"""

import os
import json
import logging
import threading
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("OverlayTranslateLite")


class SettingsManager:
    """Thread-safe singleton settings manager."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self._settings_lock = threading.RLock()
        self._settings: Dict[str, Any] = {}
        self._config_file_path: Optional[str] = None
        
        self._defaults = {
            "ControlWindow": {},
            "CaptureWidget": {},
            "LiveTranslationWindow": {},
            "TranslatedImageViewer": {},
            "window_positions": {},
            "overlay_settings": {
                "opacity": 0.9,
                "always_on_top": True,
                "font_size": 14
            },
            "font_settings": {
                "size": 20,
                "type": "default"
            },
            "viewer_settings": {},
            "settings": {},
            "active_theme_data": None,
            "active_theme_name": None,
            "ocr_settings": {
                "min_confidence": 0.80,
                "contrast_factor": 1.0
            },
            "translation_settings": {
                "source_language": "auto",
                "target_language": "en"
            },
        }
    
    def initialize(self, config_file_path: str):
        with self._settings_lock:
            self._config_file_path = config_file_path
            self._load_settings()
            logger.info(f"SettingsManager initialized with config: {config_file_path}")
    
    def _load_settings(self):
        if not self._config_file_path:
            self._settings = json.loads(json.dumps(self._defaults))
            return
        
        if not os.path.exists(self._config_file_path):
            self._settings = json.loads(json.dumps(self._defaults))
            self._save_settings()
            return
        
        try:
            with open(self._config_file_path, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
            self._settings = self._merge_with_defaults(loaded_settings)
            logger.info(f"Settings loaded from {self._config_file_path}")
        except Exception as e:
            logger.error(f"Failed to load settings: {e}. Using defaults.", exc_info=True)
            self._settings = json.loads(json.dumps(self._defaults))
    
    def _merge_with_defaults(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        result = json.loads(json.dumps(self._defaults))
        
        def recursive_update(base: dict, updates: dict):
            for key, value in updates.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    recursive_update(base[key], value)
                else:
                    base[key] = value
        
        recursive_update(result, loaded)
        return result
    
    def _save_settings(self):
        if not self._config_file_path:
            return
        
        try:
            config_dir = os.path.dirname(self._config_file_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            temp_path = f"{self._config_file_path}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
            
            if os.path.exists(self._config_file_path):
                os.replace(temp_path, self._config_file_path)
            else:
                os.rename(temp_path, self._config_file_path)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}", exc_info=True)
    
    def get(self, key_path: str, default: Any = None) -> Any:
        with self._settings_lock:
            keys = key_path.split('.')
            value = self._settings
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            return value
    
    def set(self, key_path: str, value: Any, save: bool = True):
        with self._settings_lock:
            keys = key_path.split('.')
            current = self._settings
            for key in keys[:-1]:
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
            current[keys[-1]] = value
            if save:
                self._save_settings()
    
    def get_all(self) -> Dict[str, Any]:
        with self._settings_lock:
            return json.loads(json.dumps(self._settings))
    
    def save(self):
        with self._settings_lock:
            self._save_settings()


def get_settings_manager() -> SettingsManager:
    """Get the singleton SettingsManager instance."""
    return SettingsManager()
