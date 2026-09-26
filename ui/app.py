# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Main Application Window.
Assembles state, views, and controllers into the central VideoDownloaderGUI class.
"""

import sys
import threading

try:
    import customtkinter as ctk
    from ui import fonts as F
    _GUI_BASE = ctk.CTk
except Exception:
    ctk = None
    F = None
    _GUI_BASE = object

from logger import get_logger
from ui import theme as T
from ui.constants import APP_VERSION

# State Mixin
from ui.state.app_state import AppStateMixin

# View Mixins
from ui.views.shell import ShellViewMixin
from ui.views.film import FilmViewMixin
from ui.views.social import SocialViewMixin
from ui.views.queue import QueueViewMixin
from ui.views.library import LibraryViewMixin
from ui.views.converter import ConverterViewMixin
from ui.views.settings import SettingsViewMixin
from ui.views.modals import ModalsMixin

# Controller Mixins
from ui.controllers.download import DownloadControllerMixin
from ui.controllers.resolve import ResolveControllerMixin
from ui.controllers.social import SocialControllerMixin
from ui.controllers.queue import QueueControllerMixin
from ui.controllers.history import HistoryControllerMixin
from ui.controllers.converter import ConverterControllerMixin
from ui.controllers.dpi import DPIControllerMixin
from ui.controllers.recovery import RecoveryControllerMixin
from ui.controllers.system import SystemControllerMixin

logger = get_logger("ui.app")


class VideoDownloaderGUI(
    AppStateMixin,
    ShellViewMixin,
    FilmViewMixin,
    SocialViewMixin,
    QueueViewMixin,
    LibraryViewMixin,
    ConverterViewMixin,
    SettingsViewMixin,
    ModalsMixin,
    DownloadControllerMixin,
    ResolveControllerMixin,
    SocialControllerMixin,
    QueueControllerMixin,
    HistoryControllerMixin,
    ConverterControllerMixin,
    DPIControllerMixin,
    RecoveryControllerMixin,
    SystemControllerMixin,
    _GUI_BASE,
):
    """
    Central application class combining state, layout, and business logic.
    """

    def __init__(self):
        if F is not None:
            try:
                F.load()
            except Exception:
                logger.debug("[ui.app] F.load() istisnası", exc_info=True)

        if _GUI_BASE is not object:
            super().__init__()
        else:
            pass

        if F is not None:
            try:
                F.detect_families()
            except Exception:
                logger.debug("[ui.app] F.detect_families() istisnası", exc_info=True)

        self._init_app_state()

        if ctk is not None and _GUI_BASE is not object:
            self.title(f"Video Downloader Pro v{APP_VERSION}")
            self.geometry(f"{T.WINDOW_W}x{T.WINDOW_H}")
            self.minsize(T.WINDOW_MIN_W, T.WINDOW_MIN_H)

            try:
                ctk.set_appearance_mode("Dark")
                ctk.set_default_color_theme("blue")
                self.configure(fg_color=T.BG_APP)
            except Exception:
                logger.debug("[ui.app] ctk appearance configure istisnası", exc_info=True)

        self._build_ui()
        self._start_dpi_monitor()
        try:
            import os
            from ui.config import find_desktop_ffmpeg
            ff = find_desktop_ffmpeg()
            if not ff:
                self._log("⚠️ [FFmpeg] Sistemde FFmpeg bulunamadı. Çok kanallı birleştirme veya ses dönüştürme için FFmpeg önerilir.")
            else:
                self._log(f"[✓] FFmpeg medya motoru hazır: {os.path.basename(ff)}")
        except Exception:
            logger.debug("[ui.app] FFmpeg check istisnası", exc_info=True)

        if hasattr(self, "after"):
            try:
                self.after(1200, self._start_crash_recovery_scan)
            except Exception:
                logger.debug("[ui.app] recovery scan after() istisnası", exc_info=True)

        if hasattr(self, "protocol"):
            self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _cancel_pending_after_callbacks(self):
        """Cancel Tcl timer/idle commands before the root interpreter is destroyed."""
        try:
            callback_ids = tuple(self.tk.call("after", "info"))
        except Exception:
            logger.debug("[ui.app] pending after callbacks could not be listed", exc_info=True)
            return

        for callback_id in callback_ids:
            try:
                self.after_cancel(callback_id)
            except Exception:
                logger.debug(
                    "[ui.app] after callback could not be cancelled: %s",
                    callback_id,
                    exc_info=True,
                )

    def destroy(self):
        if getattr(self, "_destroying", False):
            return
        self._destroying = True
        try:
            self._stop_download_timer()
            # CustomTkinter widgets own recurring after() callbacks and cancel
            # them from their destroy() methods. Let children release those
            # commands first, then remove only root/global callbacks that remain.
            for child in list(self.children.values()):
                try:
                    child.destroy()
                except Exception:
                    logger.debug("[ui.app] child widget teardown failed", exc_info=True)
            self._cancel_pending_after_callbacks()
        finally:
            super().destroy()


def main():
    app = VideoDownloaderGUI()
    if hasattr(app, "mainloop"):
        app.mainloop()


if __name__ == "__main__":
    main()
