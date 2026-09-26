# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Download Controller Mixin.
Handles starting, pausing, cancelling, retrying downloads, threading, and status resets.
"""

import os
import time
import threading
try:
    from tkinter import messagebox
except Exception:
    messagebox = None

from logger import get_logger
from engine import format_human_duration, format_human_filesize
from history import add_history_entry
from ui import theme as T
from ui.config import format_seconds, should_keep_external_srt, get_default_download_directory

logger = get_logger("ui.controllers.download")


class DownloadControllerMixin:
    """
    Mixin managing download lifecycles (film, streams, multi-audio, direct files).
    """

    def _toggle_pause_download(self):
        if not self.is_paused:
            if not self.is_downloading:
                return
            self.is_paused = True
            self.is_downloading = False
            self._pause_download_timer()
            self.engine.pause()
            self.btn_start.configure(state="normal", text="▶ Devam Et", fg_color=T.WARNING, hover_color=T.WARNING_BASE)
            self.btn_pause.configure(text="▶ Devam Et", fg_color=T.WARNING, hover_color=T.WARNING_BASE)
            self.btn_cancel.configure(state="normal")
            self._set_status("DURAKLATILDI", color=T.WARNING)
            if hasattr(self, 'lbl_status_metric'):
                self.lbl_status_metric.configure(text="Duraklatıldı")
            if hasattr(self, 'lbl_eta_time'):
                self.lbl_eta_time.configure(text="(Durduruldu)")
            self._log("[⏸️] İndirme duraklatıldı. İnen parçalar ve ilerleme çubuğu korundu.")
        else:
            self.is_paused = False
            self.is_downloading = False
            self.btn_start.configure(state="disabled", text="⏳ İndiriliyor...", fg_color=T.SUCCESS, hover_color=T.SUCCESS_HOVER)
            self.btn_pause.configure(text="⏸️ Duraklat", fg_color=T.BG_CARD, hover_color=T.BORDER)
            self.btn_cancel.configure(state="normal")
            self._set_status("İndiriliyor...", color=T.PRIMARY)
            if hasattr(self, 'lbl_status_metric'):
                self.lbl_status_metric.configure(text="İndiriliyor...")
            self._log("[▶] İndirmeye kaldığı yerden devam ediliyor...")
            self.engine.resume()
            self._resume_download_timer()
            self._start_film_download_threaded()

    def _start_film_download_threaded(self):
        if self.is_paused:
            self._toggle_pause_download()
            return

        if self.is_downloading:
            if messagebox:
                ask_queue = messagebox.askyesno(
                    "İndirme Devam Ediyor",
                    "Şu anda aktif bir indirme işlemi devam ediyor.\n\nBu filmi indirme kuyruğuna eklemek ister misiniz?"
                )
                if ask_queue:
                    self._add_current_film_to_queue()
            return

        out_path = self.entry_output.get().strip()
        if not out_path:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen kayıt dosyası belirtin.")
            return

        thread_count = int(self.slider_threads.get())
        selected_audio_text = self.opt_audio_track.get()

        if self.resolved_film_data:
            data = self.resolved_film_data
            if data.get("is_yt_dlp"):
                self._start_film_ytdlp_download(data.get("raw_url") or data["video_url"], out_path)
                return
            if data.get("direct_file") and not data.get("video_segments"):
                self._start_direct_file_download(data["video_url"], out_path, data.get("video_headers"), thread_count)
                return

            video_url = data["video_url"]
            video_headers = data.get("video_headers", {})
            video_segments = data.get("video_segments")
            total_segments = data.get("total_segments") or (len(video_segments) if video_segments else 0)
            audio_tracks = data.get("audio_tracks", [])

            if "Çift Sesli" in selected_audio_text and len(audio_tracks) >= 2:
                self._start_multi_audio_stream(
                    video_url=video_url,
                    audio_tracks=audio_tracks[:2],
                    out_path=out_path,
                    video_headers=video_headers,
                    total_segments=total_segments,
                    thread_count=thread_count,
                    video_segments=video_segments,
                    video_durations=data.get("video_durations"),
                    subtitles=data.get("subtitles", [])
                )
                return

            selected_audio = None
            if audio_tracks:
                for tr in audio_tracks:
                    t_name = tr.get("name", "").strip()
                    if t_name and t_name in selected_audio_text:
                        selected_audio = tr
                        break
                if not selected_audio:
                    val_list = [v for v in self.opt_audio_track.cget("values") if "Çift Sesli" not in v]
                    for idx, v in enumerate(val_list):
                        if v == selected_audio_text and idx < len(audio_tracks):
                            selected_audio = audio_tracks[idx]
                            break
                if not selected_audio:
                    selected_audio = audio_tracks[0]

            if audio_tracks and selected_audio:
                audio_segs = selected_audio.get("segments")
                eff_video_url = selected_audio.get("video_url") or video_url
                eff_video_headers = selected_audio.get("video_headers") or video_headers
                eff_video_segments = selected_audio.get("video_segments") or video_segments
                eff_video_durations = selected_audio.get("video_durations") or data.get("video_durations")
                eff_total_segments = len(eff_video_segments) if eff_video_segments else total_segments
                audio_url = selected_audio.get("url") or selected_audio.get("sample_segment_url") or ""
                is_same_as_video = bool(
                    (audio_segs and eff_video_segments and audio_segs == eff_video_segments)
                    or (audio_url and audio_url == eff_video_url)
                    or (audio_segs and audio_segs[0] == eff_video_url)
                )
                is_standalone = bool(selected_audio.get("is_standalone_stream") or is_same_as_video)

                if is_standalone:
                    target_segs = audio_segs or eff_video_segments
                    target_url = selected_audio.get("url") or selected_audio.get("sample_segment_url") or eff_video_url
                    target_hdrs = selected_audio.get("headers") or eff_video_headers
                    self.custom_headers = target_hdrs
                    self._start_single_stream(
                        target_url, out_path, thread_count,
                        segment_urls=target_segs,
                        total_segments=len(target_segs) if target_segs else eff_total_segments,
                        subtitles=data.get("subtitles", [])
                    )
                else:
                    self._start_multi_audio_stream(
                        video_url=eff_video_url,
                        audio_tracks=[selected_audio],
                        out_path=out_path,
                        video_headers=eff_video_headers,
                        total_segments=eff_total_segments,
                        thread_count=thread_count,
                        video_segments=eff_video_segments,
                        video_durations=eff_video_durations,
                        subtitles=data.get("subtitles", [])
                    )
            else:
                self.custom_headers = video_headers
                self._start_single_stream(
                    video_url, out_path, thread_count,
                    segment_urls=video_segments,
                    total_segments=total_segments,
                    subtitles=data.get("subtitles", [])
                )
        else:
            url = self.entry_film_page.get().strip()
            if not url:
                if messagebox:
                    messagebox.showwarning("Eksik Bilgi", "Lütfen bir link girin veya çözün.")
                return
            self._start_single_stream(url, out_path, thread_count)

    def _begin_download_ui(self, status_text, keep_progress=True):
        """
        Film sekmesindeki indirme baslatma arayuzunu tek yerden hazirlar.
        `keep_progress=True` ise duraklatilmis bir indirmeye devam edilirken mevcut ilerleme cubugu korunur.
        """
        self.is_downloading = True
        self.is_paused = False
        self.engine.reset_cancel()
        self._set_film_state("indiriliyor")
        self.lbl_dl_title.configure(text=self.lbl_resolved_title.cget("text"))
        self._start_download_timer(is_yt=False)

        cur_prog = self.progress_bar.get() if keep_progress else 0.0
        if cur_prog <= 0.001:
            self.progress_bar.set(0.0)
            self.lbl_progress_text.configure(text="0%")
            self.lbl_speed_text.configure(text="0.00 MB/s")
            self.lbl_size_text.configure(text="0.0 MB")
            if hasattr(self, 'lbl_elapsed_time'):
                self.lbl_elapsed_time.configure(text="00:00")
            if hasattr(self, 'lbl_eta_time'):
                self.lbl_eta_time.configure(text="Hesaplanıyor...")
        else:
            self.lbl_progress_text.configure(text=f"{cur_prog*100:.0f}%")

        self.btn_start.configure(state="disabled", text="⏳ İndiriliyor...")
        self.btn_pause.configure(state="normal", text="⏸️ Duraklat",
                                 fg_color=T.BG_CARD, hover_color=T.BORDER)
        self.btn_cancel.configure(state="normal")
        self._set_status(status_text, color=T.PRIMARY_LIGHT)
        if hasattr(self, 'lbl_status_metric'):
            self.lbl_status_metric.configure(text="İndiriliyor...")

    def _spawn_download_thread(self, run_fn):
        """Indirme is parcacigini olusturup baslatir."""
        self.download_thread = threading.Thread(target=run_fn, daemon=True)
        self.download_thread.start()

    def _start_multi_audio_stream(self, video_url, audio_tracks, out_path, video_headers, total_segments, thread_count, video_segments=None, subtitles=None, video_durations=None):
        recovery_url = (self.resolved_film_data or {}).get("raw_url")
        self._begin_download_ui("Çift Ses İndiriliyor...")

        def on_progress(completed, total, total_bytes, speed_bps=0):
            self._live_prog_state = (completed, total, total_bytes, speed_bps)

        def run():
            success, result = self.engine.run_multi_audio_download(
                video_url=video_url,
                audio_tracks=audio_tracks,
                output_filepath=out_path,
                video_headers=video_headers,
                total_segments=total_segments,
                thread_count=thread_count,
                progress_callback=on_progress,
                log_callback=self._log,
                status_callback=lambda s: self._set_status(s, color=T.PRIMARY_LIGHT if "..." in s else T.SUCCESS),
                video_segments=video_segments,
                video_durations=video_durations,
                subtitles=subtitles,
                keep_external_srt=should_keep_external_srt(),
                recovery_url=recovery_url,
            )
            if success:
                add_history_entry(os.path.basename(out_path), out_path, media_type="Çift Sesli Film")
            self._reset_ui(success, result)

        self._spawn_download_thread(run)

    def _start_direct_file_download(self, url, out_path, custom_headers=None, thread_count=16):
        self._begin_download_ui("Doğrudan Akış İndiriliyor...")

        def on_prog(downloaded, total, cur, spd):
            self._live_prog_state = (downloaded, total, downloaded, spd)

        def run():
            headers = custom_headers or (self.resolved_film_data.get("video_headers") if self.resolved_film_data else self.custom_headers)
            success, result = self.engine.download_direct_file(
                url=url,
                output_filepath=out_path,
                custom_headers=headers,
                thread_count=thread_count,
                progress_callback=on_prog,
                log_callback=self._log,
                status_callback=lambda s: self._set_status(s, color=T.PRIMARY_LIGHT if "..." in s else T.SUCCESS)
            )
            if success:
                add_history_entry(os.path.basename(out_path), out_path, media_type="Doğrudan Video")
            self._reset_ui(success, result)

        self._spawn_download_thread(run)

    def _start_single_stream(self, url, out_path, thread_count, segment_urls=None, total_segments=None, subtitles=None):
        recovery_url = (self.resolved_film_data or {}).get("raw_url")
        self._begin_download_ui("İndiriliyor...")

        def on_progress(completed, total, total_bytes, speed_bps=0):
            self._live_prog_state = (completed, total, total_bytes, speed_bps)

        def run():
            success, result = self.engine.run_download(
                sample_url=url,
                output_filepath=out_path,
                thread_count=thread_count,
                total_segments=total_segments,
                custom_headers=self.custom_headers,
                segment_urls=segment_urls,
                progress_callback=on_progress,
                log_callback=self._log,
                status_callback=lambda s: self._set_status(s, color=T.PRIMARY_LIGHT if "..." in s else T.SUCCESS),
                subtitles=subtitles,
                keep_external_srt=should_keep_external_srt(),
                recovery_url=recovery_url,
            )
            if not success and not self.engine.cancel_event.is_set():
                fallback_target = ""
                if self.resolved_film_data:
                    fallback_target = self.resolved_film_data.get("raw_url") or self.resolved_film_data.get("video_url")
                if not fallback_target:
                    try:
                        fallback_target = self.entry_film_page.get().strip() or url
                    except Exception:
                        fallback_target = url

                if fallback_target:
                    self._log(f"[i] 🔄 Doğrudan indirme başarısız oldu. Kullanıcıya hata verilmeden Evrensel Motor (yt-dlp) ile deneniyor...")
                    out_dir = os.path.dirname(out_path) or os.getcwd()
                    def ytdl_cb(down, tot, spd, ratio):
                        elapsed = self.download_elapsed_accumulated + (time.time() - self.download_start_time)
                        eta_str = "--:--"
                        if ratio >= 1.0:
                            eta_str = "00:00"
                        elif ratio > 0.005 and spd > 20000 and tot > 0:
                            rem = max(0, tot - down)
                            eta_str = format_seconds(rem / spd)

                        self.progress_bar.set(ratio)
                        self._set_status(f"İndiriliyor: %{ratio*100:.1f}")
                        if hasattr(self, 'lbl_progress_text'):
                            self.lbl_progress_text.configure(text=f"{ratio*100:.0f}%")
                        if hasattr(self, 'lbl_speed_text'):
                            self.lbl_speed_text.configure(text=f"{spd/(1024*1024):.2f} MB/s")
                        if hasattr(self, 'lbl_size_text'):
                            self.lbl_size_text.configure(text=f"{down/(1024*1024):.1f} / {tot/(1024*1024):.1f} MB")
                        if hasattr(self, 'lbl_elapsed_time'):
                            self.lbl_elapsed_time.configure(text=f"{format_seconds(elapsed)}")
                        if hasattr(self, 'lbl_eta_time'):
                            self.lbl_eta_time.configure(text=f"{eta_str}")

                    ok_yt, res_yt = self.engine.download_youtube_media(
                        media_url=fallback_target,
                        output_dir=out_dir,
                        format_choice="best",
                        progress_callback=ytdl_cb,
                        log_callback=self._log
                    )
                    if ok_yt and os.path.exists(res_yt):
                        add_history_entry(os.path.basename(res_yt), res_yt, source_url=fallback_target, media_type="Evrensel Web Medya")
                        self._reset_ui(True, res_yt)
                        return

            if success:
                add_history_entry(os.path.basename(out_path), out_path, media_type="Film")
            self._reset_ui(success, result)

        self._spawn_download_thread(run)

    def _start_film_ytdlp_download(self, raw_url, out_path):
        self.is_downloading = True
        self.btn_start.configure(state="disabled", text="⏳ İndiriliyor...")
        self.btn_pause.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress_bar.set(0)
        self._set_status("Evrensel Motor İndiriyor...")
        self._log(f"[▶] Evrensel Medya Motoru ile indirme başlatıldı: {raw_url}")

        out_dir = os.path.dirname(out_path) or os.getcwd()

        def cb(down, tot, spd, ratio):
            self.progress_bar.set(ratio)
            self._set_status(f"İndiriliyor: %{ratio*100:.1f}")
            if hasattr(self, 'lbl_progress_text'):
                self.lbl_progress_text.configure(text=f"{ratio*100:.0f}%")
            if hasattr(self, 'lbl_speed_text'):
                self.lbl_speed_text.configure(text=f"{spd/(1024*1024):.2f} MB/s")
            if hasattr(self, 'lbl_size_text'):
                self.lbl_size_text.configure(text=f"{down/(1024*1024):.1f} / {tot/(1024*1024):.1f} MB")

        def run():
            success, res = self.engine.download_youtube_media(
                media_url=raw_url,
                output_dir=out_dir,
                format_choice="best",
                progress_callback=cb,
                log_callback=self._log
            )
            if success:
                add_history_entry(os.path.basename(res), res, source_url=raw_url, media_type="Evrensel Web Medya")
            self._reset_ui(success, res)

        self._spawn_download_thread(run)

    def _cancel_download(self):
        if self.is_downloading or self.is_paused:
            self._log("İndirme iptal edildi. Geçici dosyalar temizleniyor...")
            self.is_downloading = False
            self.is_paused = False
            self._stop_download_timer()
            self.engine.cancel(cleanup=True)
            self._set_status("İptal Edildi", color=T.DANGER)
            self.progress_bar.set(0.0)
            if hasattr(self, 'lbl_progress_text'):
                self.lbl_progress_text.configure(text="0%")
            if hasattr(self, 'lbl_speed_text'):
                self.lbl_speed_text.configure(text="0.00 MB/s")
            if hasattr(self, 'lbl_size_text'):
                self.lbl_size_text.configure(text="0.0 MB")
            if hasattr(self, 'lbl_elapsed_time'):
                self.lbl_elapsed_time.configure(text="00:00")
            if hasattr(self, 'lbl_eta_time'):
                self.lbl_eta_time.configure(text="--:--")
            if hasattr(self, 'lbl_status_metric'):
                self.lbl_status_metric.configure(text="İptal Edildi")
            self.btn_cancel.configure(state="disabled")
            self.btn_pause.configure(state="disabled", text="⏸️ Duraklat")
            clean_choice = self.opt_audio_track.get().split('(')[0].strip() if hasattr(self, 'opt_audio_track') else "İndir"
            self.btn_start.configure(state="normal", text=f"▶ İndir ({clean_choice})", fg_color=T.SUCCESS, hover_color=T.SUCCESS_HOVER)

    def _reset_ui(self, success, result_msg):
        def update():
            try:
                if self.is_paused or (result_msg and "duraklat" in str(result_msg).lower()):
                    self.is_downloading = False
                    self.is_paused = True
                    self.btn_start.configure(state="disabled", text="⏳ Duraklatıldı")
                    self.btn_pause.configure(state="normal", text="▶ Devam Et", fg_color=T.WARNING, hover_color=T.WARNING_BASE)
                    self.btn_cancel.configure(state="normal")
                    self._set_status("DURAKLATILDI", color=T.WARNING)
                    if hasattr(self, 'lbl_status_metric'):
                        self.lbl_status_metric.configure(text="Duraklatıldı")
                    if hasattr(self, 'lbl_eta_time'):
                        self.lbl_eta_time.configure(text="(Durduruldu)")
                    return

                total_elapsed = self.download_elapsed_accumulated
                if hasattr(self, 'download_start_time') and self.download_start_time > 0:
                    total_elapsed += (time.time() - self.download_start_time)

                self.is_downloading = False
                self.is_paused = False
                self._stop_download_timer()
                self._set_film_state("cozumlendi" if self.resolved_film_data else "bos")
                clean_choice = self.opt_audio_track.get().split('(')[0].strip() if hasattr(self, 'opt_audio_track') else "İndir"
                self.btn_start.configure(state="normal", text=f"▶ İndir ({clean_choice})", fg_color=T.SUCCESS, hover_color=T.SUCCESS_HOVER)
                self.btn_pause.configure(state="disabled", text="⏸️ Duraklat", fg_color=T.BG_CARD, hover_color=T.BORDER)
                self.btn_cancel.configure(state="disabled")

                if success:
                    self.progress_bar.set(1.0)
                    if hasattr(self, 'lbl_progress_text'):
                        self.lbl_progress_text.configure(text="100%")
                    if hasattr(self, 'lbl_eta_time'):
                        self.lbl_eta_time.configure(text="00:00")
                    if hasattr(self, 'lbl_status_metric'):
                        self.lbl_status_metric.configure(text="Tamamlandı")
                    self._set_status("Tamamlandı", color=T.SUCCESS)
                    self._play_notification_sound()
                    self._send_desktop_notification("İndirme Tamamlandı", f"{os.path.basename(str(result_msg).strip()) or 'Video'} başarıyla kaydedildi.")
                    self._refresh_history_ui()

                    file_path = str(result_msg).strip()
                    dur_str = format_human_duration(total_elapsed) if total_elapsed > 0 else ""
                    size_str = ""
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        try:
                            sz = os.path.getsize(file_path)
                            size_str = format_human_filesize(sz)
                        except Exception:
                            logger.debug("[ui.controllers.download] Dosya boyutu okunamadı", exc_info=True)

                    msg_parts = ["İşlem başarıyla tamamlandı! ✅\n"]
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
                    self.progress_bar.set(0.0)
                    if hasattr(self, 'lbl_progress_text'):
                        self.lbl_progress_text.configure(text="0%")
                    if hasattr(self, 'lbl_speed_text'):
                        self.lbl_speed_text.configure(text="0.00 MB/s")
                    if hasattr(self, 'lbl_eta_time'):
                        self.lbl_eta_time.configure(text="--:--")
                    if hasattr(self, 'lbl_status_metric'):
                        self.lbl_status_metric.configure(text="İptal Edildi")
                    self._set_status("İptal Edildi", color=T.DANGER)
                    if result_msg and "iptal" not in result_msg.lower() and "duraklat" not in result_msg.lower():
                        if messagebox:
                            messagebox.showerror("Hata", f"İndirme başarısız:\n{result_msg}")
            except Exception:
                logger.debug("[ui.controllers.download] _reset_ui.update() istisnası", exc_info=True)
        self.after(0, update)

    def _open_output_folder(self):
        out_path = self.entry_output.get().strip() if hasattr(self, 'entry_output') else ""
        folder = os.path.dirname(out_path) if out_path else ""
        if not folder or not os.path.exists(folder):
            folder = get_default_download_directory()
        if os.path.exists(folder):
            self._reveal_in_file_manager(folder)
