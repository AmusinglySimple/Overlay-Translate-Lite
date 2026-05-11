"""
Translation Manager for Overlay Translate GUI Internationalization (i18n)

This module provides centralized translation management using Qt's translation system.
Supports multiple languages with fallback to English, language switching without restart,
and Right-to-Left (RTL) layout support for Arabic/Hebrew.

Part of Item 49: Multi-Language UI (i18n for GUI)
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import QTranslator, QLocale, QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

# Import QLibraryInfo early — needed by load_language() for Qt standard translations
try:
    from PySide6.QtCore import QLibraryInfo
except ImportError:
    # Fallback dummy class for exotic PySide6 builds missing QLibraryInfo
    class QLibraryInfo:
        TranslationsPath = 0
        @staticmethod
        def location(path_type):
            return ""

logger = logging.getLogger(__name__)

# Supported languages with ISO 639-1 codes and native names
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "rtl": False},
    "es": {"name": "Spanish", "native": "Español", "rtl": False},
    "fr": {"name": "French", "native": "Français", "rtl": False},
    "de": {"name": "German", "native": "Deutsch", "rtl": False},
    "zh_CN": {"name": "Chinese (Simplified)", "native": "简体中文", "rtl": False},
    "zh_TW": {"name": "Chinese (Traditional)", "native": "繁體中文", "rtl": False},
    "ja": {"name": "Japanese", "native": "日本語", "rtl": False},
    "ko": {"name": "Korean", "native": "한국어", "rtl": False},
    "pt": {"name": "Portuguese", "native": "Português", "rtl": False},
    "ru": {"name": "Russian", "native": "Русский", "rtl": False},
    "ar": {"name": "Arabic", "native": "العربية", "rtl": True},
    "he": {"name": "Hebrew", "native": "עברית", "rtl": True},
    "it": {"name": "Italian", "native": "Italiano", "rtl": False},
    "nl": {"name": "Dutch", "native": "Nederlands", "rtl": False},
    "pl": {"name": "Polish", "native": "Polski", "rtl": False},
    "tr": {"name": "Turkish", "native": "Türkçe", "rtl": False},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "rtl": False},
    "th": {"name": "Thai", "native": "ไทย", "rtl": False},
    "hi": {"name": "Hindi", "native": "हिन्दी", "rtl": False},
    "uk": {"name": "Ukrainian", "native": "Українська", "rtl": False},
}


class TranslationManager:
    """
    Manages application translations with dynamic language switching.
    
    Features:
    - Load translations from .qm files
    - Switch languages without restart
    - RTL layout support
    - Fallback to English
    - Language preference persistence
    
    Usage:
        manager = TranslationManager()
        manager.load_language("es")  # Switch to Spanish
        manager.get_available_languages()  # List available translations
    """
    
    def __init__(self, app: QApplication):
        """
        Initialize translation manager.
        
        Args:
            app: QApplication instance to install translators on
        """
        self.app = app
        self.current_language = "en"
        self.translator = None
        self.qt_translator = None  # For Qt standard dialogs
        
        # Translation files directory
        from utils.config import PROJECT_ROOT
        self.translations_dir = os.path.join(PROJECT_ROOT, "translations")
        
        logger.info(f"TranslationManager initialized, translations dir: {self.translations_dir}")
    
    def load_language(self, lang_code: str) -> bool:
        """
        Load and apply a language translation.
        
        Args:
            lang_code: ISO 639-1 language code (e.g., "es", "zh_CN")
        
        Returns:
            True if translation loaded successfully, False otherwise
        """
        if lang_code not in SUPPORTED_LANGUAGES:
            logger.warning(f"Language '{lang_code}' not supported, falling back to English")
            lang_code = "en"
        
        # Remove previous translator if exists
        if self.translator:
            self.app.removeTranslator(self.translator)
            self.translator = None
        
        if self.qt_translator:
            self.app.removeTranslator(self.qt_translator)
            self.qt_translator = None
        
        # English is default, no translation file needed
        if lang_code == "en":
            self.current_language = "en"
            self._set_layout_direction("en")
            logger.info("Loaded language: English (default)")
            return True
        
        # Load application translation
        translation_file = os.path.join(self.translations_dir, f"overlay_translate_{lang_code}.qm")
        
        if not os.path.exists(translation_file):
            logger.warning(f"Translation file not found: {translation_file}, using English")
            self.current_language = "en"
            return False
        
        self.translator = QTranslator()
        if self.translator.load(translation_file):
            self.app.installTranslator(self.translator)
            self.current_language = lang_code
            logger.info(f"Loaded translation: {SUPPORTED_LANGUAGES[lang_code]['name']} ({lang_code})")
        else:
            logger.error(f"Failed to load translation file: {translation_file}")
            self.translator = None
            self.current_language = "en"
            return False
        
        # Load Qt standard translations (for dialogs like QMessageBox, QFileDialog)
        qt_translations_dir = QLibraryInfo.location(QLibraryInfo.TranslationsPath) if hasattr(QLibraryInfo, 'location') else ""
        
        if qt_translations_dir:
            qt_translation_file = f"qt_{lang_code}"
            self.qt_translator = QTranslator()
            if self.qt_translator.load(qt_translation_file, qt_translations_dir):
                self.app.installTranslator(self.qt_translator)
                logger.debug(f"Loaded Qt standard translations for {lang_code}")
            else:
                logger.debug(f"Qt standard translations not available for {lang_code}")
                self.qt_translator = None
        
        # Set layout direction for RTL languages
        self._set_layout_direction(lang_code)
        
        return True
    
    def _set_layout_direction(self, lang_code: str):
        """
        Set application layout direction based on language.
        
        Args:
            lang_code: Language code to check for RTL
        """
        is_rtl = SUPPORTED_LANGUAGES.get(lang_code, {}).get("rtl", False)
        
        if is_rtl:
            self.app.setLayoutDirection(Qt.RightToLeft)
            logger.info(f"Set layout direction: RTL for {lang_code}")
        else:
            self.app.setLayoutDirection(Qt.LeftToRight)
            logger.debug(f"Set layout direction: LTR for {lang_code}")
    
    def get_current_language(self) -> str:
        """Get currently active language code."""
        return self.current_language
    
    def get_current_language_name(self) -> str:
        """Get currently active language display name."""
        return SUPPORTED_LANGUAGES.get(self.current_language, {}).get("name", "English")
    
    def get_available_languages(self) -> List[Tuple[str, str, str]]:
        """
        Get list of all supported languages.
        
        Returns:
            List of tuples (code, name, native_name)
            Example: [("en", "English", "English"), ("es", "Spanish", "Español")]
        """
        languages = []
        for code, info in sorted(SUPPORTED_LANGUAGES.items(), key=lambda x: x[1]["name"]):
            languages.append((code, info["name"], info["native"]))
        return languages
    
    def get_installed_languages(self) -> List[Tuple[str, str, str]]:
        """
        Get list of languages with available translation files.
        
        Returns:
            List of tuples (code, name, native_name) for installed translations
        """
        installed = [("en", "English", "English")]  # English always available
        
        if not os.path.exists(self.translations_dir):
            return installed
        
        for code, info in SUPPORTED_LANGUAGES.items():
            if code == "en":
                continue
            
            translation_file = os.path.join(self.translations_dir, f"overlay_translate_{code}.qm")
            if os.path.exists(translation_file):
                installed.append((code, info["name"], info["native"]))
        
        return sorted(installed, key=lambda x: x[1])
    
    def is_rtl_language(self, lang_code: Optional[str] = None) -> bool:
        """
        Check if a language uses Right-to-Left layout.
        
        Args:
            lang_code: Language code to check, or None for current language
        
        Returns:
            True if RTL, False otherwise
        """
        code = lang_code or self.current_language
        return SUPPORTED_LANGUAGES.get(code, {}).get("rtl", False)
    
    def detect_system_language(self) -> str:
        """
        Detect system language and return closest supported language code.
        
        Returns:
            Language code (e.g., "es") or "en" if no match found
        """
        system_locale = QLocale.system()
        system_lang = system_locale.name()  # e.g., "es_ES", "zh_CN"
        
        logger.debug(f"System locale detected: {system_lang}")
        
        # Try exact match first (e.g., "zh_CN")
        if system_lang in SUPPORTED_LANGUAGES:
            return system_lang
        
        # Try language prefix match (e.g., "es" from "es_ES")
        lang_prefix = system_lang.split("_")[0]
        if lang_prefix in SUPPORTED_LANGUAGES:
            return lang_prefix
        
        # Check for regional variants (e.g., "zh" -> "zh_CN")
        for code in SUPPORTED_LANGUAGES:
            if code.startswith(lang_prefix + "_"):
                return code
        
        logger.debug(f"No match for system language {system_lang}, defaulting to English")
        return "en"
    
    def save_language_preference(self, lang_code: str):
        """
        Save language preference to settings.
        
        Args:
            lang_code: Language code to save
        """
        try:
            from utils.helpers import load_settings, save_settings
            
            settings = load_settings()
            settings["language"] = lang_code
            save_settings(settings)
            logger.info(f"Saved language preference: {lang_code}")
        except Exception as e:
            logger.error(f"Failed to save language preference: {e}")
    
    def load_language_preference(self) -> str:
        """
        Load saved language preference or detect system language.
        
        Returns:
            Language code from settings, system, or "en" as fallback
        """
        try:
            from utils.helpers import load_settings
            
            settings = load_settings()
            saved_lang = settings.get("language")
            
            if saved_lang and saved_lang in SUPPORTED_LANGUAGES:
                logger.info(f"Loaded language preference: {saved_lang}")
                return saved_lang
        except Exception as e:
            logger.warning(f"Failed to load language preference: {e}")
        
        # Fall back to system language detection
        return self.detect_system_language()


# QLibraryInfo import moved to top of file (before class definition)


# Global translation manager instance (initialized in main.py)
_translation_manager: Optional[TranslationManager] = None


def init_translation_manager(app: QApplication) -> TranslationManager:
    """
    Initialize global translation manager instance.
    
    Args:
        app: QApplication instance
    
    Returns:
        TranslationManager instance
    """
    global _translation_manager
    _translation_manager = TranslationManager(app)
    return _translation_manager


def get_translation_manager() -> Optional[TranslationManager]:
    """
    Get global translation manager instance.
    
    Returns:
        TranslationManager instance or None if not initialized
    """
    return _translation_manager


def tr(text: str, context: str = "Global") -> str:
    """
    Translate text using current language.
    
    This is a convenience function for non-QObject contexts.
    For QObject-derived classes, use self.tr() instead.
    
    Args:
        text: Text to translate
        context: Translation context (typically class name)
    
    Returns:
        Translated text or original if translation not found
    """
    return QCoreApplication.translate(context, text)
