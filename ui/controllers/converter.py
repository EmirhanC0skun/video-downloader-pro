# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Audio Converter Controller Mixin.
Handles file inputs/outputs browsing and FFmpeg-based audio conversion.
"""

import os
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

logger = get_logger("ui.controllers.converter")


class ConverterControllerMixin:
    """
    Mixin managing audio conversion operations.
    """

    def _browse_conv_input(self):
        if not filedialog:
            return
        f = filedialog.askopenfilename(
            filetypes=[("Video / Ses Dosyaları", "*.mp4 *.ts *.mkv *.avi *.mov *.webm *.flv *.m4a"), ("Tüm Dosyalar", "*.*")],
            title="Dönüştürülecek Dosyayı Seçin"
        )
        if f:
            self.entry_conv_in.delete(0, "end")
            self.entry_conv_in.insert(0, f)
            base = os.path.splitext(f)[0]
            fmt_text = self.opt_conv_fmt.get()
            ext = ".wav" if "WAV" in fmt_text else ".mp3"
            self.entry_conv_out.delete(0, "end")
            self.entry_conv_out.insert(0, base + ext)

    def _browse_conv_output(self):
        if not filedialog:
            return
        f = filedialog.asksaveasfilename(
            filetypes=[("MP3 Ses", "*.mp3"), ("WAV Ses", "*.wav"), ("Tüm Dosyalar", "*.*")],
            title="Kayıt Ses Dosyasını Seçin"
        )
        if f:
            self.entry_conv_out.delete(0, "end")
            self.entry_conv_out.insert(0, f)

    def _start_convert_threaded(self):
        in_p = self.entry_conv_in.get().strip()
        out_p = self.entry_conv_out.get().strip()
        if not in_p or not os.path.exists(in_p):
            if messagebox:
                messagebox.showwarning("Eksik Dosya", "Lütfen geçerli bir girdi dosyası seçin.")
            return
        if not out_p:
            if messagebox:
                messagebox.showwarning("Eksik Dosya", "Lütfen çıktı dosya adını belirtin.")
            return

        from ui.config import find_desktop_ffmpeg
        if not find_desktop_ffmpeg():
            if messagebox:
                messagebox.showwarning(
                    "FFmpeg Bulunamadı",
                    "Ses dönüştürme işlemi için sisteminizde FFmpeg kurulu olmalıdır.\n\n"
                    "Lütfen FFmpeg'i PATH ortam değişkenine ekleyin veya uygulama klasörüne yerleştirin."
                )
            self._log_conv("[!] FFmpeg bulunamadığı için dönüştürme başlatılamadı.")
            return

        fmt_text = self.opt_conv_fmt.get()
        if "WAV" in fmt_text:
            fmt = "wav"
            bitrate = "320k"
        elif "192 kbps" in fmt_text:
            fmt = "mp3"
            bitrate = "192k"
        else:
            fmt = "mp3"
            bitrate = "320k"

        self._log_conv(f"Dönüştürülüyor: {os.path.basename(in_p)} -> {os.path.basename(out_p)}")

        t_start = time.time()
        def run():
            success, res = self.engine.convert_media_to_audio(
                input_filepath=in_p,
                output_filepath=out_p,
                audio_format=fmt,
                bitrate=bitrate,
                log_callback=self._log_conv
            )
            elapsed = time.time() - t_start
            if success:
                add_history_entry(os.path.basename(out_p), out_p, media_type="Ses Dönüştürme")
                self._play_notification_sound()
                self._send_desktop_notification("Dönüştürme Tamamlandı", f"{os.path.basename(str(res).strip()) or 'Ses'} başarıyla oluşturuldu.")
                self._refresh_history_ui()

                file_path = str(res).strip()
                dur_str = format_human_duration(elapsed) if elapsed > 0 else ""
                size_str = ""
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    try:
                        sz = os.path.getsize(file_path)
                        size_str = format_human_filesize(sz)
                    except Exception:
                        logger.debug("[ui.controllers.converter] Dosya boyutu okunamadı", exc_info=True)

                msg_parts = ["Ses dosyası başarıyla oluşturuldu! ✅\n"]
                if file_path:
                    msg_parts.append(f"📁 Dosya: {os.path.basename(file_path)}")
                    msg_parts.append(f"📍 Konum: {file_path}")
                if size_str:
                    msg_parts.append(f"📦 Boyut: {size_str}")
                if dur_str:
                    msg_parts.append(f"⏱️ Süre: {dur_str}")

                if messagebox:
                    messagebox.showinfo("Tamamlandı", "\n".join(msg_parts))
            else:
                if messagebox:
                    messagebox.showerror("Hata", f"Dönüştürme hatası:\n{res}")

        threading.Thread(target=run, daemon=True).start()
