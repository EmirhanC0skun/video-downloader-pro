# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Social Media Controller Mixin.
Handles YouTube / social media resolution via yt-dlp, browser cookies, and video/audio downloads.
"""

import os
import re
import time
import threading
try:
    from tkinter import filedialog, messagebox
except Exception:
    filedialog = None
    messagebox = None

from logger import get_logger
from engine import format_human_duration, format_human_filesize
from history import add_history_entry
from ui import widgets as W
from ui import theme as T
from ui.config import (
    format_seconds,
    translate_user_friendly_error,
    get_default_download_directory,
    set_custom_download_directory,
)

logger = get_logger("ui.controllers.social")


class SocialControllerMixin:
    """
    Mixin managing social media operations (yt-dlp extraction, download, cancel).
    """

    def _paste_yt_url(self):
        try:
            t = self.clipboard_get()
            val = t.strip()
            self.entry_yt_url.delete(0, "end")
            self.entry_yt_url.insert(0, val)
            self._check_smart_mode_suggestion(val)
        except Exception:
            logger.debug("[ui.controllers.social] _paste_yt_url() sessiz istisna yutuldu", exc_info=True)

    def _browse_yt_dir(self):
        cur_dir = self.entry_yt_dir.get().strip() if hasattr(self, 'entry_yt_dir') else ""
        if not cur_dir or not os.path.exists(cur_dir):
            cur_dir = get_default_download_directory()
        if filedialog:
            d = filedialog.askdirectory(initialdir=cur_dir, title="Kayıt Klasörünü Seçin")
            if d:
                set_custom_download_directory(d)
                self.entry_yt_dir.delete(0, "end")
                self.entry_yt_dir.insert(0, d)
                if hasattr(self, 'entry_output'):
                    cur_fname = os.path.basename(self.entry_output.get().strip()) or "film.mp4"
                    self.entry_output.delete(0, "end")
                    self.entry_output.insert(0, os.path.join(d, cur_fname))
                if hasattr(self, 'btn_header_folder'):
                    self.btn_header_folder.configure(text=f"{W.icon_text('folder')}  {os.path.basename(d) or 'VideoDownloaderPro'}")
                if hasattr(self, 'row_download_dir') and hasattr(self.row_download_dir, 'desc'):
                    self.row_download_dir.desc.configure(text=d)

    def _browse_cookie_file(self):
        if filedialog:
            f = filedialog.askopenfilename(
                filetypes=[("Çerez / Metin Dosyası", "*.txt"), ("Tüm Dosyalar", "*.*")],
                title="cookies.txt Dosyasını Seçin"
            )
            if f:
                self.entry_cookie_file.delete(0, "end")
                self.entry_cookie_file.insert(0, f)
                self.opt_yt_cookies.set("📁 Çerez Dosyası (.txt)")

    def _on_yt_cookie_changed(self, choice):
        if "Çerez Dosyası" in choice:
            if not self.entry_cookie_file.get().strip():
                self._browse_cookie_file()

    def _open_yt_folder(self):
        d = self.entry_yt_dir.get().strip() or os.getcwd()
        if os.path.exists(d):
            self._reveal_in_file_manager(d)

    def _resolve_youtube_url_threaded(self, _from_router=False):
        url = self.entry_yt_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen bir YouTube veya sosyal medya bağlantısı girin.")
            return

        cookie_choice = self.opt_yt_cookies.get()
        browser_choice = None
        if "Chrome" in cookie_choice:
            browser_choice = "chrome"
        elif "Edge" in cookie_choice:
            browser_choice = "edge"
        elif "Firefox" in cookie_choice:
            browser_choice = "firefox"
        elif "Brave" in cookie_choice:
            browser_choice = "brave"
        raw_cookie_path = self.entry_cookie_file.get().strip().strip('"').strip("'")
        cookies_file = os.path.normpath(raw_cookie_path) if (raw_cookie_path and os.path.exists(os.path.normpath(raw_cookie_path))) else None

        self.btn_yt_resolve.configure(state="disabled", text="⏳ Çözülüyor...")
        self._set_status("Çözümleniyor", color=T.PRIMARY_LIGHT,
                         detail="Medya bilgileri sorgulanıyor")
        self._log_yt(f"Çözümleme başlatıldı: {url}")

        def run():
            try:
                info = self.social_engine.extract_youtube_info(
                    media_url=url,
                    browser_cookies=browser_choice,
                    cookies_file=cookies_file,
                    log_callback=self._log_yt
                )
                title = info.get("title", "Video")
                duration = info.get("duration", 0)
                dur_str = f" ({format_seconds(duration)})" if duration else ""
                qualities = info.get("qualities", [])

                def on_success():
                    self.btn_yt_resolve.configure(state="normal", text="Çözümle")
                    self.lbl_yt_title.configure(text=W.elide(f"{title}{dur_str}", 52))
                    self.lbl_yt_resolved_url.configure(
                        text=W.elide(self.entry_yt_url.get().strip(), 68))
                    self._set_social_state("cozumlendi")
                    if qualities:
                        self.opt_yt_format.configure(values=qualities)
                        self.opt_yt_format.set(qualities[0])
                    self._log_yt(f"✅ Çözümleme tamamlandı: {title}")

                    best_q = qualities[0] if qualities else "🌟 En Yüksek Kalite"
                    sz_sum = f"{dur_str.strip(' ()')} Süre" if dur_str else "Dinamik Akış"
                    aud_sum = "Evrensel AAC (Kayıpsız / Muxed)"

                    self.after(60, lambda: self._show_resolution_modal(
                        title=title,
                        media_type="Sosyal Medya",
                        quality_summary=f"{best_q} ({len(qualities)} format)",
                        size_summary=sz_sum,
                        audio_summary=aud_sum,
                        on_download=self._start_youtube_download_threaded,
                        on_queue=self._add_current_yt_to_queue
                    ))

                self.after(0, on_success)
            except Exception as e:
                err_msg = str(e)
                friendly_msg = translate_user_friendly_error(err_msg)
                def on_error():
                    self.btn_yt_resolve.configure(state="normal", text="🔍 Çözümle")
                    self._set_status("Çözümleme hatası", color=T.DANGER,
                                     detail=err_msg[:40])
                    self._log_yt(f"[HATA] Çözümleme başarısız: {err_msg}")
                    if messagebox:
                        messagebox.showerror("Çözümleme Hatası", friendly_msg)

                self.after(0, on_error)

        threading.Thread(target=run, daemon=True).start()

    def _start_youtube_download_threaded(self):
        url = self.entry_yt_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen bir link girin.")
            return

        out_dir = self.entry_yt_dir.get().strip() or os.getcwd()
        fmt_choice = self.opt_yt_format.get().lower()
        if "mp3" in fmt_choice:
            fmt = "mp3"
        elif "m4a" in fmt_choice or "aac" in fmt_choice:
            fmt = "m4a"
        else:
            height_match = re.search(r'(\d+)p', fmt_choice)
            if height_match:
                fmt = f"{height_match.group(1)}p"
            elif "2160" in fmt_choice or "4k" in fmt_choice:
                fmt = "2160p"
            elif "1440" in fmt_choice or "2k" in fmt_choice:
                fmt = "1440p"
            elif "1080" in fmt_choice:
                fmt = "1080p"
            elif "720" in fmt_choice:
                fmt = "720p"
            elif "480" in fmt_choice:
                fmt = "480p"
            elif "360" in fmt_choice:
                fmt = "360p"
            else:
                fmt = "best"

        cookie_choice = self.opt_yt_cookies.get()
        browser_choice = None

        if "Chrome" in cookie_choice:
            browser_choice = "chrome"
        elif "Edge" in cookie_choice:
            browser_choice = "edge"
        elif "Firefox" in cookie_choice:
            browser_choice = "firefox"
        elif "Brave" in cookie_choice:
            browser_choice = "brave"

        raw_cookie_path = self.entry_cookie_file.get().strip().strip('"').strip("'")
        cookies_file = os.path.normpath(raw_cookie_path) if (raw_cookie_path and os.path.exists(os.path.normpath(raw_cookie_path))) else None

        self.is_yt_downloading = True
        self._start_download_timer(is_yt=True)
        self.btn_yt_start.configure(state="disabled")
        self.btn_yt_cancel.configure(state="normal")
        self.yt_pbar.set(0)
        self._set_social_state("indiriliyor")
        self.lbl_yt_progress.configure(text="İndiriliyor…")
        self.lbl_yt_pct.configure(text="0%")
        if hasattr(self, 'lbl_yt_elapsed'):
            self.lbl_yt_elapsed.configure(text="00:00")
        if hasattr(self, 'lbl_yt_eta'):
            self.lbl_yt_eta.configure(text="Hesaplanıyor...")

        self._log_yt(f"İndirme başlatıldı ({fmt}): {url}")
        if browser_choice:
            self._log_yt(f"[i] Tarayıcı Oturumu: {browser_choice.capitalize()}")
        if cookies_file:
            self._log_yt(f"[i] Çerez Dosyası: {os.path.basename(cookies_file)}")

        def cb(down, tot, spd, ratio):
            if not getattr(self, 'is_yt_downloading', False) or self.social_engine.cancel_event.is_set():
                return
            elapsed = self.download_elapsed_accumulated + (time.time() - self.download_start_time)
            eta_str = "--:--"
            if ratio >= 1.0 or (tot > 0 and down >= tot):
                eta_str = "00:00"
            elif ratio > 0.005 and spd > 10000 and tot > 0:
                rem = max(0, tot - down)
                eta_str = format_seconds(rem / spd)
            elif ratio > 0.005 and elapsed > 0.5:
                eta_str = format_seconds((elapsed / ratio) * (1.0 - ratio))

            self.yt_pbar.set(ratio)
            self.lbl_yt_pct.configure(text=f"{ratio*100:.0f}%")
            self.lbl_yt_progress.configure(text=f"{down/(1024*1024):.0f} / {tot/(1024*1024):.0f} MB")
            self.lbl_yt_speed.configure(text=f"{spd/(1024*1024):.2f} MB/s")
            if hasattr(self, 'lbl_yt_elapsed'):
                self.lbl_yt_elapsed.configure(text=f"{format_seconds(elapsed)}")
            if hasattr(self, 'lbl_yt_eta'):
                self.lbl_yt_eta.configure(text=f"{eta_str}")

        def run():
            try:
                self.social_engine.reset_cancel()
                success, res = self.social_engine.download_youtube_media(
                    media_url=url,
                    output_dir=out_dir,
                    format_choice=fmt,
                    browser_cookies=browser_choice,
                    cookies_file=cookies_file,
                    progress_callback=cb,
                    log_callback=self._log_yt
                )
                total_elapsed = self.download_elapsed_accumulated
                if hasattr(self, 'download_start_time') and self.download_start_time > 0:
                    total_elapsed += (time.time() - self.download_start_time)

                self._stop_download_timer()
                self.is_yt_downloading = False
                self.btn_yt_start.configure(state="normal")
                self.btn_yt_cancel.configure(state="disabled")
                if success:
                    self.yt_pbar.set(1.0)
                    self._set_social_state("cozumlendi")
                    self.lbl_yt_progress.configure(text="Tamamlandı")
                    self.lbl_yt_pct.configure(text="100%")
                    if hasattr(self, 'lbl_yt_eta'):
                        self.lbl_yt_eta.configure(text="00:00")
                    self._log_yt(f"[✓] İndirildi: {res}")
                    add_history_entry(os.path.basename(res), res, source_url=url, media_type="Sosyal / YouTube")
                    self._play_notification_sound()
                    self._send_desktop_notification("İndirme Tamamlandı", f"{os.path.basename(str(res).strip()) or 'Medya'} başarıyla indirildi.")
                    self._refresh_history_ui()

                    file_path = str(res).strip()
                    dur_str = format_human_duration(total_elapsed) if total_elapsed > 0 else ""
                    size_str = ""
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        try:
                            sz = os.path.getsize(file_path)
                            size_str = format_human_filesize(sz)
                        except Exception:
                            logger.debug("[ui.controllers.social] Dosya boyutu okunamadı", exc_info=True)

                    msg_parts = ["Medya başarıyla indirildi! ✅\n"]
                    if file_path:
                        msg_parts.append(f"📁 Dosya: {os.path.basename(file_path)}")
                        msg_parts.append(f"📍 Konum: {file_path}")
                    if size_str:
                        msg_parts.append(f"📦 Boyut: {size_str}")
                    if dur_str:
                        msg_parts.append(f"⏱️ Süre: {dur_str}")

                    if messagebox:
                        messagebox.showinfo("Tamamlandı", "\n".join(msg_parts))
                    self._handle_shutdown()
                else:
                    self.yt_pbar.set(0.0)
                    self._set_social_state("cozumlendi")
                    self.lbl_yt_pct.configure(text="0%")
                    self.lbl_yt_progress.configure(text="İptal edildi" if "iptal" in str(res).lower() else "Hata")
                    if hasattr(self, 'lbl_yt_speed'):
                        self.lbl_yt_speed.configure(text="0.00 MB/s")
                    if hasattr(self, 'lbl_yt_size'):
                        self.lbl_yt_size.configure(text="📦 0.0 MB")
                    if hasattr(self, 'lbl_yt_eta'):
                        self.lbl_yt_eta.configure(text="--:--")
                    self._log_yt(f"[{'İPTAL' if 'iptal' in str(res).lower() else 'HATA'}] {res}")
                    if "iptal" not in str(res).lower():
                        if messagebox:
                            messagebox.showerror("Hata", f"İndirme başarısız:\n{res}")
            except Exception as e:
                self._stop_download_timer()
                self.is_yt_downloading = False
                self.yt_pbar.set(0.0)
                self.btn_yt_start.configure(state="normal")
                self.btn_yt_cancel.configure(state="disabled")
                self._set_social_state("cozumlendi")
                self.lbl_yt_pct.configure(text="0%")
                self.lbl_yt_progress.configure(text="Hata")
                if hasattr(self, 'lbl_yt_speed'):
                    self.lbl_yt_speed.configure(text="0.00 MB/s")
                if hasattr(self, 'lbl_yt_size'):
                    self.lbl_yt_size.configure(text="📦 0.0 MB")
                if hasattr(self, 'lbl_yt_eta'):
                    self.lbl_yt_eta.configure(text="--:--")
                self._log_yt(f"[HATA] {e}")

        threading.Thread(target=run, daemon=True).start()

    def _cancel_youtube_download(self):
        self._log_yt("[!] İndirme iptal edildi.")
        self._stop_download_timer()
        self.is_yt_downloading = False
        self.social_engine.cancel()
        self.yt_pbar.set(0.0)
        self.btn_yt_start.configure(state="normal")
        self.btn_yt_cancel.configure(state="disabled")
        self.lbl_yt_pct.configure(text="0%")
        self.lbl_yt_progress.configure(text="İptal edildi")
        if hasattr(self, 'lbl_yt_speed'):
            self.lbl_yt_speed.configure(text="0.00 MB/s")
        if hasattr(self, 'lbl_yt_size'):
            self.lbl_yt_size.configure(text="📦 0.0 MB")
        if hasattr(self, 'lbl_yt_eta'):
            self.lbl_yt_eta.configure(text="--:--")
