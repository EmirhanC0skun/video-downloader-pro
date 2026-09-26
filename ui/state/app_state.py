# -*- coding: utf-8 -*-
"""
Video Downloader Pro — UI Application State Mixin.
Manages download states, queues, timers, real-time speed/ETA metrics, and logging.
"""

import time
import threading
from logger import get_logger
from engine import VideoDownloadEngine
from ui import theme as T
from ui.config import format_seconds

logger = get_logger("ui.state")


class AppStateMixin:
    """
    Mixin providing application state variables, timers, logging hooks, and status indicators.
    Designed to be mixed into VideoDownloaderGUI.
    """

    def _init_app_state(self):
        # Yonlendirici ve durum makinesi
        self.current_page = "film"
        self._film_state = "bos"
        self._social_state = "bos"

        self.engine = VideoDownloadEngine()
        self.social_engine = VideoDownloadEngine()
        self.queue_engine = VideoDownloadEngine()
        self.download_thread = None
        self.is_downloading = False
        self.is_paused = False
        self.custom_headers = {}
        self.resolved_film_data = None

        # Zaman & Süre Takip Sayaçları
        self.download_start_time = 0.0
        self.download_elapsed_accumulated = 0.0
        self.download_timer_id = None
        self.download_is_yt = False

        # Kuyruk Durumları
        self._queue_lock = threading.RLock()
        self.download_queue = []
        self.is_queue_running = False
        self.is_queue_paused = False
        self.queue_thread = None
        self.queue_row_widgets = {}
        self.current_queue_item_id = None

        # DPI Mod Takibi
        self.current_dpi_mode = 0

        # UI Güncelleme Throttle (pencere kaydırma akıcılığı)
        self._last_ui_update_time = 0.0
        self._ui_update_min_interval = 0.08  # 80ms

    @staticmethod
    def _update_log_hint(textbox, panel):
        """Katlanır günlük başlığındaki `N satır` rozetini tazeler."""
        try:
            lines = textbox.get("1.0", "end-1c").count(chr(10)) + 1
            panel.set_hint(f"{lines} satır")
        except Exception:
            logger.debug("[ui.state] _update_log_hint() sessiz istisna yutuldu",
                         exc_info=True)

    def _log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        def update():
            try:
                self.txt_logs.configure(state="normal")
                self.txt_logs.insert("end", formatted)
                self.txt_logs.see("end")
                self.txt_logs.configure(state="disabled")
                self._update_log_hint(self.txt_logs, self.log_film)
            except Exception:
                logger.debug("[ui.state] _log.update() sessiz istisna yutuldu", exc_info=True)
        try:
            self.after_idle(update)
        except Exception:
            logger.debug("[ui.state] _log() sessiz istisna yutuldu", exc_info=True)

    def _log_yt(self, message):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        def update():
            try:
                self.txt_yt_logs.configure(state="normal")
                self.txt_yt_logs.insert("end", formatted)
                self.txt_yt_logs.see("end")
                self.txt_yt_logs.configure(state="disabled")
                self._update_log_hint(self.txt_yt_logs, self.log_social)
            except Exception:
                logger.debug("[ui.state] _log_yt.update() sessiz istisna yutuldu", exc_info=True)
        try:
            self.after_idle(update)
        except Exception:
            logger.debug("[ui.state] _log_yt() sessiz istisna yutuldu", exc_info=True)

    def _log_conv(self, message):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        def update():
            try:
                self.txt_conv_logs.configure(state="normal")
                self.txt_conv_logs.insert("end", formatted)
                self.txt_conv_logs.see("end")
                self.txt_conv_logs.configure(state="disabled")
                self._update_log_hint(self.txt_conv_logs, self.log_conv)
            except Exception:
                logger.debug("[ui.state] _log_conv.update() sessiz istisna yutuldu", exc_info=True)
        try:
            self.after_idle(update)
        except Exception:
            logger.debug("[ui.state] _log_conv() sessiz istisna yutuldu", exc_info=True)

    def _clear_film_logs(self):
        try:
            self.txt_logs.configure(state="normal")
            self.txt_logs.delete("1.0", "end")
            self.txt_logs.configure(state="disabled")
        except Exception:
            logger.debug("[ui.state] _clear_film_logs() sessiz istisna yutuldu", exc_info=True)

    def _set_status(self, text, color=T.SUCCESS, detail=None):
        """Sidebar'daki canlı durum kartını günceller."""
        def update():
            try:
                subtitle = detail if detail is not None else "Ağ koruması aktif"
                self.status_card.set_status(text, subtitle, color)
            except Exception:
                logger.debug("[ui.state] _set_status.update() sessiz istisna yutuldu",
                             exc_info=True)
        try:
            self.after(0, update)
        except Exception:
            logger.debug("[ui.state] _set_status() sessiz istisna yutuldu", exc_info=True)

    def _start_download_timer(self, is_yt=False):
        self._stop_download_timer()
        self.download_start_time = time.time()
        self.download_elapsed_accumulated = 0.0
        self.download_is_yt = is_yt
        self._live_prog_state = None
        self._prog_ui_timer = None
        self._tick_download_timer()
        self._tick_progress_ui()

    def _stop_download_timer(self):
        if self.download_timer_id is not None:
            try:
                self.after_cancel(self.download_timer_id)
            except Exception:
                logger.debug("[ui.state] _stop_download_timer() sessiz istisna yutuldu", exc_info=True)
            self.download_timer_id = None
        if getattr(self, "_prog_ui_timer", None) is not None:
            try:
                self.after_cancel(self._prog_ui_timer)
            except Exception:
                logger.debug("[ui.state] _stop_download_timer() sessiz istisna yutuldu", exc_info=True)
            self._prog_ui_timer = None

    def _pause_download_timer(self):
        if hasattr(self, 'download_start_time') and self.download_start_time > 0:
            self.download_elapsed_accumulated += (time.time() - self.download_start_time)
            self.download_start_time = 0.0

    def _resume_download_timer(self):
        self.download_start_time = time.time()
        self._tick_download_timer()
        self._tick_progress_ui()

    def _tick_progress_ui(self):
        """İndirme thread'lerini GIL kilitlerinden kurtaran periyodik (200ms) bağımsız UI render motoru."""
        if not self.is_downloading and not self.is_paused:
            return
        state = getattr(self, "_live_prog_state", None)
        if state:
            completed, total, total_bytes, speed_bps = state
            ratio = completed / total if total > 0 else 0.0
            elapsed = self.download_elapsed_accumulated + (time.time() - self.download_start_time) if self.download_start_time > 0 else self.download_elapsed_accumulated
            
            eta_str = "--:--"
            if ratio >= 1.0 or completed >= total:
                eta_str = "00:00"
            elif ratio > 0.005 and elapsed > 0.5:
                if speed_bps > 20000 and total_bytes > 0 and completed > 0:
                    est_tot_bytes = (total_bytes / completed) * total
                    rem_bytes = max(0, est_tot_bytes - total_bytes)
                    eta_secs = rem_bytes / speed_bps
                else:
                    eta_secs = (elapsed / completed) * (total - completed)
                eta_str = format_seconds(eta_secs)

            try:
                self.progress_bar.set(ratio)
                self.lbl_progress_text.configure(text=f"{ratio*100:.0f}%")
                self.lbl_status_metric.configure(text=f"{completed} / {total} parça")
                self.lbl_speed_text.configure(text=f"{speed_bps/(1024*1024):.2f} MB/s")
                self.lbl_size_text.configure(text=f"{total_bytes/(1024*1024):.1f} MB")
                if hasattr(self, 'lbl_elapsed_time'):
                    self.lbl_elapsed_time.configure(text=f"{format_seconds(elapsed)}")
                if hasattr(self, 'lbl_eta_time'):
                    self.lbl_eta_time.configure(text=f"{eta_str}")
            except Exception:
                logger.debug("[ui.state] _tick_progress_ui() sessiz istisna yutuldu", exc_info=True)
        self._prog_ui_timer = self.after(200, self._tick_progress_ui)

    def _tick_download_timer(self):
        if not self.is_downloading and not getattr(self, 'is_yt_downloading', False):
            return
        if self.is_paused:
            self.download_timer_id = self.after(1000, self._tick_download_timer)
            return

        elapsed = self.download_elapsed_accumulated + (time.time() - self.download_start_time)
        elapsed_str = format_seconds(elapsed)

        try:
            if getattr(self, 'download_is_yt', False):
                if hasattr(self, 'lbl_yt_elapsed'):
                    self.lbl_yt_elapsed.configure(text=f"{elapsed_str}")
            else:
                if hasattr(self, 'lbl_elapsed_time'):
                    self.lbl_elapsed_time.configure(text=f"{elapsed_str}")
        except Exception:
            logger.debug("[ui.state] _tick_download_timer() sessiz istisna yutuldu", exc_info=True)

        self.download_timer_id = self.after(1000, self._tick_download_timer)
