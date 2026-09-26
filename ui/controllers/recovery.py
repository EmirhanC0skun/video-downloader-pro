# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Crash Recovery & Disk Hygiene Controller Mixin.
Scans for incomplete downloads from previous crashes and provides temp disk cleanup.
"""

import os
import threading

try:
    from tkinter import messagebox
except Exception:
    messagebox = None

from logger import get_logger
from engine import (
    scan_incomplete_downloads,
    cleanup_stale_temp_dirs,
)
from ui import widgets as W
from ui import theme as T

logger = get_logger("ui.controllers.recovery")


class RecoveryControllerMixin:
    """
    Mixin providing crash recovery scanning, resume actions, and temp disk hygiene.
    """

    def _start_crash_recovery_scan(self):
        """Uygulama açılışında yarım kalmış indirmeleri arka planda tarar ve eski atıkları temizler."""
        def _bg():
            try:
                candidates = scan_incomplete_downloads()
                if candidates:
                    self.after(0, lambda: self._show_recovery_modal(candidates))
                # Yetim klasör süpürücüsü (48 saatten eski kalmış yetimler sessizce GC edilir)
                cleanup_stale_temp_dirs(max_age_hours=48.0)
            except Exception as e:
                logger.debug(f"Crash recovery tarama hatası: {e}", exc_info=True)

        threading.Thread(target=_bg, daemon=True).start()

    def _resume_incomplete_candidate(self, candidate):
        """Kurtarılan indirmeyi arayüze yükler ve kaldığı yerden devam ettirir."""
        url = candidate.get("raw_url") or candidate.get("url") or ""
        out_path = candidate.get("output_filepath") or ""
        title = candidate.get("title", "")

        self._show_page("film")
        if url and hasattr(self, 'entry_film_page'):
            self.entry_film_page.delete(0, "end")
            self.entry_film_page.insert(0, url)

        if out_path and hasattr(self, 'entry_output'):
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, out_path)

        self._log(f"[🔄] Kurtarma Modu: '{title}' ({candidate.get('downloaded_segments', 0)}/{candidate.get('total_segments', 0)} parça) devam ettiriliyor...")
        self._set_status("Kurtarılıyor...", color=T.WARNING, detail=W.elide(title, 26) if W else title)

        # URL çözümlemesini tetikle; motor diskteki parçaları otomatik tanıyacak
        if any(d in url.lower() for d in ["youtube", "youtu.be", "instagram", "tiktok", "twitter", "x.com"]):
            self._resolve_youtube_url_threaded()
        else:
            self._recovery_resume_candidate = candidate
            self._resolve_film_threaded()

    def _cleanup_temp_disk_ui(self):
        """Kullanıcının Ayarlar sayfasından başlattığı disk temizliği süreci."""
        def _run_gc():
            cnt, freed = cleanup_stale_temp_dirs(max_age_hours=0.0)
            freed_mb = freed / (1024 * 1024)
            msg = f"{cnt} adet geçici klasör temizlendi ({freed_mb:.2f} MB disk alanı boşaltıldı)." if cnt > 0 else "Diskte temizlenecek yetim veya süresi dolmuş geçici dosya bulunamadı."
            if messagebox:
                self.after(0, lambda: messagebox.showinfo("Disk Hijyeni", msg))
            self.after(0, lambda: self._log(f"[✓] {msg}"))
        threading.Thread(target=_run_gc, daemon=True).start()
