# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Centralized Component Logging System.
Provides structured logging, rotating file logs, and in-memory UI callbacks.
"""

import os
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler

# Log directory configuration
LOG_DIR = os.path.join(os.path.expanduser("~"), ".video_downloader_logs")
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    LOG_DIR = os.getcwd()

LOG_FILE = os.path.join(LOG_DIR, "video_downloader.log")

# Root namespace for the project
ROOT_LOGGER_NAME = "video_downloader"

# Custom log format
LOG_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_is_configured = False
_ui_callbacks = []
_ui_callbacks_lock = threading.RLock()


class UICallbackHandler(logging.Handler):
    """Dispatches log records to registered GUI / Mobile UI log listeners."""
    def emit(self, record):
        try:
            msg = self.format(record)
            with _ui_callbacks_lock:
                listeners = list(_ui_callbacks)
            for cb in listeners:
                try:
                    cb(record.levelname, msg, record.getMessage())
                except Exception:
                    self.handleError(record)
        except Exception:
            self.handleError(record)


def is_debug_enabled() -> bool:
    """
    Ayrintili tani gunlugu (DEBUG) yalnizca VDP_DEBUG ortam degiskeni ile acilir.
    Kapaliyken logger.debug() cagrilari erken donerek sicak indirme dongusunde
    olcülebilir bir maliyet yaratmaz.
    """
    return str(os.environ.get("VDP_DEBUG", "")).strip().lower() in ("1", "true", "yes", "on", "evet")


def configure_logging(level=logging.INFO, log_to_file=True):
    """
    Configures root application logger with console, file, and UI handlers.
    """
    global _is_configured
    if _is_configured:
        return logging.getLogger(ROOT_LOGGER_NAME)

    debug_mode = is_debug_enabled()
    root_logger = logging.getLogger(ROOT_LOGGER_NAME)
    # Kok seviye en dusuk handler seviyesine cekilir; filtreleme handler'larda yapilir.
    # Aksi halde file_handler'in DEBUG seviyesi hicbir zaman devreye giremez.
    root_logger.setLevel(logging.DEBUG if debug_mode else level)
    root_logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler
    console_stream = sys.stdout
    if console_stream is not None and hasattr(console_stream, "reconfigure"):
        try:
            # Windows cp1254 consoles cannot encode emoji used by platform logs.
            # Preserve the active codepage while making unsupported glyphs safe.
            console_stream.reconfigure(errors="backslashreplace")
        except Exception:
            # Some redirected/test streams expose reconfigure but reject changes.
            pass
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler (Max 5 MB per file, keeps 3 backups)
    if log_to_file:
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not create log file handler: {e}\n")

    # 3. UI Callback Handler
    ui_handler = UICallbackHandler()
    ui_handler.setLevel(logging.INFO)
    ui_handler.setFormatter(formatter)
    root_logger.addHandler(ui_handler)

    _is_configured = True
    return root_logger


def get_logger(component_name: str) -> logging.Logger:
    """
    Returns a child logger for a specific component (e.g. 'engine', 'extractor').
    """
    if not _is_configured:
        configure_logging()
    
    full_name = f"{ROOT_LOGGER_NAME}.{component_name}" if component_name else ROOT_LOGGER_NAME
    return logging.getLogger(full_name)


def register_ui_log_listener(callback):
    """
    Registers a callable callback(level: str, formatted_msg: str, raw_msg: str)
    for real-time GUI / Mobile UI log feeds.
    """
    with _ui_callbacks_lock:
        if callback not in _ui_callbacks:
            _ui_callbacks.append(callback)


def unregister_ui_log_listener(callback):
    """Removes a registered UI log listener."""
    with _ui_callbacks_lock:
        if callback in _ui_callbacks:
            _ui_callbacks.remove(callback)
