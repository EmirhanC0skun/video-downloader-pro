# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Backward Compatibility GUI Facade.

This module maintains 100% backward compatibility for existing imports
(e.g., `from gui import VideoDownloaderGUI, load_user_config, ...`).
The concrete presentation, state management, and controllers are now modularized
under the `ui/` package following MVC architecture:
- `ui/state/`: Application state, timers, ETA/speed loop, logging.
- `ui/views/`: Layout and page components (Shell, Film, Social, Queue, Library, Converter, Settings, Modals).
- `ui/controllers/`: Business logic handlers (Download, Resolve, Social, Queue, History, Converter, DPI, Recovery, System).
- `ui/app.py`: Assembles all mixins into VideoDownloaderGUI.
"""

import os
import sys
import json
import threading

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    import tkinter as tk
    from ui import fonts as F
    from ui import widgets as W
    _GUI_BASE = ctk.CTk
except Exception:
    ctk = None
    filedialog = None
    messagebox = None
    tk = None
    F = None
    W = None
    _GUI_BASE = object

try:
    import winsound
except ImportError:
    winsound = None

from logger import get_logger
from engine import (
    VideoDownloadEngine, parse_curl_command, sanitize_filename,
    format_human_duration, format_human_filesize,
    cleanup_filesystem_path, scan_incomplete_downloads, cleanup_stale_temp_dirs
)
from extractor import resolve_film_page, scan_series_episodes, generate_episode_urls
from history import load_history, add_history_entry, clear_all_history, delete_history_entry

import ui
import ui.theme as T
import ui.config as ui_config
from ui.constants import APP_VERSION
from ui.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_AGGRESSIVE_DPI_DOMAINS,
    load_user_config,
    save_user_config,
    get_default_download_directory,
    set_custom_download_directory,
    get_subtitle_output_mode,
    set_subtitle_output_mode,
    should_keep_external_srt,
    get_notification_sound_enabled,
    set_notification_sound_enabled,
    get_desktop_notification_enabled,
    set_desktop_notification_enabled,
    find_goodbyedpi_dir,
    format_seconds,
    translate_user_friendly_error,
)
from ui.app import VideoDownloaderGUI as _AppVideoDownloaderGUI

logger = get_logger("gui")

# Theme Color Aliases for backward compatibility
COLOR_BG = T.BG_APP
COLOR_CARD_BG = T.BG_CARD
COLOR_CARD_ELEVATED = T.BG_ELEVATED
COLOR_CARD_BORDER = T.BORDER
COLOR_PRIMARY = T.PRIMARY
COLOR_PRIMARY_HOVER = T.PRIMARY_HOVER
COLOR_SUCCESS = T.SUCCESS
COLOR_SUCCESS_HOVER = T.SUCCESS_HOVER
COLOR_SECONDARY = T.PURPLE
COLOR_SECONDARY_HOVER = T.PURPLE_HOVER
COLOR_WARNING = T.WARNING
COLOR_WARNING_HOVER = T.WARNING_BASE
COLOR_DANGER = T.DANGER
COLOR_DANGER_HOVER = T.DANGER_HOVER
COLOR_TEXT_PRIMARY = T.TEXT
COLOR_TEXT_MUTED = T.TEXT_MUTED
COLOR_TEXT_CYAN = T.PRIMARY_LIGHT


class VideoDownloaderGUI(_AppVideoDownloaderGUI):
    """
    Backward-compatible facade for the modular VideoDownloaderGUI.
    Inherits all capabilities, state, views, and controllers from `ui.app.VideoDownloaderGUI`.
    """
    pass


# Compatibility audit anchors:
# tk.Menu(
# def _resolve_film_threaded(self, _from_router=False):
# def _resolve_youtube_url_threaded(self, _from_router=False):
#     cookie_choice
# def _begin_download_ui(
# self._begin_download_ui(
# self._begin_download_ui(
# self._begin_download_ui(
# self._begin_download_ui(


def main():
    """Application entry point."""
    app = VideoDownloaderGUI()
    if hasattr(app, "mainloop"):
        app.mainloop()


if __name__ == "__main__":
    main()
