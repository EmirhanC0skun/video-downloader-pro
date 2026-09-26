# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Batch Queue Controller Mixin.
Handles adding items/series/ranges to the queue, item deletion, pausing, and serial processing.
"""

import os
import time
import threading
try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None
    messagebox = None

from logger import get_logger
from engine import sanitize_filename
from extractor import scan_series_episodes, generate_episode_urls, resolve_film_page
from history import add_history_entry
from ui import theme as T
from ui.config import format_seconds, should_keep_external_srt, get_default_download_directory

logger = get_logger("ui.controllers.queue")


class QueueControllerMixin:
    """
    Mixin managing batch queue processing, episode range scanning, and queue items lifecycle.
    """

    def _paste_queue_url(self):
        try:
            t = self.clipboard_get()
            self.entry_queue_url.delete(0, "end")
            self.entry_queue_url.insert(0, t.strip())
        except Exception:
            logger.debug("[ui.controllers.queue] _paste_queue_url() sessiz istisna yutuldu", exc_info=True)

    def _add_to_queue(self):
        url = self.entry_queue_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Link", "Lütfen kuyruğa eklemek için bir URL girin.")
            return
        item = {
            "id": int(time.time() * 1000),
            "url": url,
            "title": f"Görev #{len(self.download_queue)+1}",
            "status": "Bekliyor",
            "progress": 0.0
        }
        with self._queue_lock:
            self.download_queue.append(item)
        self.entry_queue_url.delete(0, "end")
        self._refresh_queue_ui()

    def _scan_and_add_series(self, all_episodes=True):
        url = self.entry_queue_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Link", "Lütfen taranacak dizi sayfasının linkini girin.")
            return

        self._set_status("Dizi & Sezonlar Taranıyor...", color=T.PRIMARY_LIGHT)
        def task():
            try:
                episodes = scan_series_episodes(url, log_callback=self._log)
                start_val = self.entry_start_ep.get().strip()
                end_val = self.entry_end_ep.get().strip()

                if not episodes:
                    start_ep = int(start_val or 1)
                    end_ep = int(end_val or 10)
                    episodes = generate_episode_urls(url, start_ep, end_ep)
                elif not all_episodes and start_val and end_val:
                    try:
                        s_limit = int(start_val)
                        e_limit = int(end_val)
                        episodes = [ep for ep in episodes if s_limit <= ep.get("episode", 1) <= e_limit]
                    except ValueError:
                        logger.debug("[ui.controllers.queue] _scan_and_add_series parsing istisnası", exc_info=True)

                added_count = 0
                for ep in episodes:
                    item = {
                        "id": int(time.time() * 1000) + added_count,
                        "url": ep["url"],
                        "title": ep["title"],
                        "status": "Bekliyor",
                        "progress": 0.0
                    }
                    self.download_queue.append(item)
                    added_count += 1

                self.after(0, self._refresh_queue_ui)
                self._set_status(f"{added_count} Bölüm Eklendi", color=T.SUCCESS)
                if messagebox:
                    messagebox.showinfo("Başarılı", f"📺 Toplam {added_count} adet dizi bölümü indirme kuyruğuna eklendi!\n'Kuyruğu Başlat' ile tüm bölümleri sırayla indirebilirsiniz.")
            except Exception as e:
                self._set_status("Hata", color=T.DANGER)
                if messagebox:
                    messagebox.showerror("Hata", f"Bölümler taranamadı: {e}")

        threading.Thread(target=task, daemon=True).start()

    def _add_range_to_queue(self):
        url = self.entry_queue_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Link", "Lütfen şablon bölüm linkini girin (örn: ...-1-sezon-1-bolum).")
            return

        try:
            start_ep = int(self.entry_start_ep.get().strip() or 1)
            end_ep = int(self.entry_end_ep.get().strip() or 10)
            if start_ep > end_ep:
                if messagebox:
                    messagebox.showwarning("Geçersiz Aralık", "Başlangıç bölümü bitişten büyük olamaz.")
                return

            episodes = generate_episode_urls(url, start_ep, end_ep)
            added_count = 0
            for idx, ep in enumerate(episodes):
                item = {
                    "id": int(time.time() * 1000) + idx,
                    "url": ep["url"],
                    "title": ep["title"],
                    "status": "Bekliyor",
                    "progress": 0.0
                }
                self.download_queue.append(item)
                added_count += 1

            self._refresh_queue_ui()
            self._set_status(f"{len(episodes)} Bölüm Eklendi", color=T.SUCCESS)
            if messagebox:
                messagebox.showinfo("Başarılı", f"{len(episodes)} adet sıralı bölüm kuyruğa eklendi!")
        except Exception as e:
            if messagebox:
                messagebox.showerror("Hata", f"Aralık oluşturulamadı: {e}")

    def _remove_queue_item(self, item_id):
        if self.is_queue_running and self.current_queue_item_id == item_id:
            self.queue_engine.cancel()
        with self._queue_lock:
            self.download_queue = [it for it in self.download_queue if it["id"] != item_id]
        self._refresh_queue_ui()
        self._set_status("Öğe Kuyruktan Kaldırıldı", color=T.WARNING)

    def _cancel_queue_item(self, item_id):
        for it in self.download_queue:
            if it["id"] == item_id:
                if self.is_queue_running and self.current_queue_item_id == item_id:
                    self.queue_engine.cancel()
                it["status"] = "İptal Edildi ⏹️"
                it["progress"] = 0.0
                break
        self._refresh_queue_ui()
        self._set_status("Öğe İptal Edildi", color=T.WARNING)

    def _retry_queue_item(self, item_id):
        for it in self.download_queue:
            if it["id"] == item_id:
                it["status"] = "Bekliyor"
                it["progress"] = 0.0
                break
        self._refresh_queue_ui()
        self._set_status("Öğe Yeniden Sıraya Alındı", color=T.PRIMARY_LIGHT)

    def _copy_queue_item_url(self, item_id):
        for it in self.download_queue:
            if it["id"] == item_id:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(it["url"])
                    self._set_status("Link Panoya Kopyalandı", color=T.SUCCESS)
                except Exception:
                    logger.debug("[ui.controllers.queue] _copy_queue_item_url() sessiz istisna yutuldu", exc_info=True)
                break

    def _open_queue_item_folder(self, item_id):
        for it in self.download_queue:
            if it["id"] == item_id:
                p = it.get("output_path")
                if p and os.path.exists(p):
                    target_dir = os.path.dirname(p) if os.path.isfile(p) else p
                    self._safe_open_dir(target_dir)
                else:
                    self._open_output_folder()
                break

    def _show_queue_context_menu(self, event, item_id):
        target_item = next((it for it in self.download_queue if it["id"] == item_id), None)
        if not target_item or tk is None:
            return

        menu = tk.Menu(self, tearoff=0, bg="#1a1d24", fg="#ffffff", activebackground="#00adb5", activeforeground="#ffffff", relief="flat", bd=1)

        is_active = (self.is_queue_running and self.current_queue_item_id == item_id)

        if is_active:
            menu.add_command(label="⏹️ İndirmeyi İptal Et / Durdur", command=lambda: self._cancel_queue_item(item_id))
        else:
            if "İptal" in target_item["status"] or "Hata" in target_item["status"]:
                menu.add_command(label="🔄 Yeniden Sıraya Al (Tekrar Dene)", command=lambda: self._retry_queue_item(item_id))
            else:
                menu.add_command(label="⏹️ Bu Öğeyi İptal Et / Atla", command=lambda: self._cancel_queue_item(item_id))

        menu.add_command(label="🗑️ Kuyruktan Çıkar (Sil)", command=lambda: self._remove_queue_item(item_id))
        menu.add_separator()
        menu.add_command(label="📋 Linki Kopyala", command=lambda: self._copy_queue_item_url(item_id))
        if target_item.get("output_path") and os.path.exists(target_item["output_path"]):
            menu.add_command(label="📂 Dosya Konumunu Aç", command=lambda: self._open_queue_item_folder(item_id))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _clear_queue(self):
        if self.is_queue_running:
            if messagebox:
                messagebox.showwarning("İşlem Devam Ediyor", "Kuyruk çalışırken temizlenemez. Önce duraklatın.")
            return
        with self._queue_lock:
            self.download_queue = []
        self.is_queue_paused = False
        self.btn_q_stop.configure(text="⏸️ Duraklat", fg_color=T.BG_CARD, hover_color=T.BORDER)
        self.btn_q_start.configure(state="normal", text="▶ Kuyruğu Başlat (Sırayla İndir)")
        self._refresh_queue_ui()

    def _toggle_queue_pause(self):
        if self.is_queue_running and not self.is_queue_paused:
            self.is_queue_paused = True
            self.is_queue_running = False
            self.queue_engine.cancel()
            self.btn_q_stop.configure(
                text="▶️ Devam Et",
                fg_color=T.SUCCESS,
                hover_color=T.SUCCESS_HOVER
            )
            self.btn_q_start.configure(state="normal", text="▶ Kuyruğu Başlat")
            self._set_status("Kuyruk Duraklatıldı ⏸️", color=T.WARNING)
            if self.current_queue_item_id:
                for it in self.download_queue:
                    if it["id"] == self.current_queue_item_id and it["status"] not in ["Tamamlandı", "İptal Edildi ⏹️"]:
                        it["status"] = "⏸️ Duraklatıldı"
                        self._update_queue_item_progress(it["id"], "⏸️ Duraklatıldı", it.get("progress", 0.0), color=T.WARNING)
        elif self.is_queue_paused or not self.is_queue_running:
            self.is_queue_paused = False
            self.btn_q_stop.configure(
                text="⏸️ Duraklat",
                fg_color=T.BG_CARD,
                hover_color=T.BORDER
            )
            self._start_queue_processing()

    def _stop_queue_processing(self):
        self._toggle_queue_pause()

    def _start_queue_processing(self):
        if not self.download_queue:
            if messagebox:
                messagebox.showinfo("Kuyruk Boş", "Kuyrukta indirilecek öğe yok.")
            return
        if self.is_queue_running:
            return

        self.is_queue_running = True
        self.is_queue_paused = False
        self.queue_engine.reset_cancel()
        self.btn_q_start.configure(state="disabled", text="⏳ Kuyruk Çalışıyor...")
        self.btn_q_stop.configure(
            state="normal",
            text="⏸️ Duraklat",
            fg_color=T.BG_CARD,
            hover_color=T.BORDER
        )

        def worker():
            processed_ids = set()
            while True:
                if not self.is_queue_running or self.is_queue_paused:
                    break
                with self._queue_lock:
                    item = next(
                        (it for it in self.download_queue
                         if it["id"] not in processed_ids
                         and it["status"] not in ("Tamamlandı", "İptal Edildi ⏹️")),
                        None,
                    )
                if item is None:
                    break
                processed_ids.add(item["id"])

                item_id = item["id"]
                self.current_queue_item_id = item_id
                item["status"] = "İndiriliyor (%0)"
                self._update_queue_item_progress(item_id, item["status"], item.get("progress", 0.0), color=T.WARNING)
                self._set_status(f"Kuyruk: {item['title']}", color=T.PRIMARY_LIGHT)

                url = item["url"]
                def_dir = get_default_download_directory()
                safe_out = item.get("output_path") or os.path.join(def_dir, f"kuyruk_{int(time.time())}.mp4")

                last_progress_time = [0]
                q_item_start = time.time()

                def q_cb(comp, tot, b, spd):
                    if not self.is_queue_running or self.is_queue_paused:
                        return
                    now = time.time()
                    if now - last_progress_time[0] >= 0.15 or comp >= tot:
                        last_progress_time[0] = now
                        ratio = comp / tot if tot > 0 else 0
                        item["progress"] = ratio
                        elapsed = max(0.1, now - q_item_start)
                        eta_secs = ((elapsed / comp) * (tot - comp)) if (comp > 0 and ratio < 1.0) else 0
                        eta_str = format_seconds(eta_secs) if ratio < 1.0 else "00:00"
                        spd_mb = spd / (1024 * 1024)
                        item["status"] = f"İndiriliyor %{ratio*100:.0f} (⚡{spd_mb:.1f}M • ⏳{eta_str})"
                        self._update_queue_item_progress(item_id, item["status"], ratio, color=T.WARNING)

                try:
                    if any(d in url.lower() for d in ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "twitter.com", "x.com"]) or item.get("format_choice"):
                        def yt_cb(down, tot, spd, ratio):
                            if not self.is_queue_running or self.is_queue_paused:
                                return
                            now = time.time()
                            if now - last_progress_time[0] >= 0.15 or ratio >= 1.0:
                                last_progress_time[0] = now
                                item["progress"] = ratio
                                elapsed = max(0.1, now - q_item_start)
                                eta_secs = ((elapsed / ratio) * (1.0 - ratio)) if (ratio > 0.005 and ratio < 1.0) else 0
                                eta_str = format_seconds(eta_secs) if ratio < 1.0 else "00:00"
                                spd_mb = spd / (1024 * 1024)
                                item["status"] = f"İndiriliyor %{ratio*100:.0f} (⚡{spd_mb:.1f}M • ⏳{eta_str})"
                                self._update_queue_item_progress(item_id, item["status"], ratio, color=T.WARNING)

                        fmt = item.get("format_choice", "best")
                        out_dir = item.get("output_dir") or def_dir
                        browser_choice = item.get("browser_choice")
                        cookie_file = item.get("cookie_file")

                        success, res = self.queue_engine.download_youtube_media(
                            media_url=url,
                            output_dir=out_dir,
                            format_choice=fmt,
                            browser_cookies=browser_choice,
                            cookies_file=cookie_file,
                            progress_callback=yt_cb
                        )
                        if success:
                            safe_out = res
                    else:
                        if item.get("resolved_data"):
                            data = item["resolved_data"]
                        else:
                            data = resolve_film_page(url)

                        item["title"] = data.get("title", item["title"])[:100]
                        safe_title = sanitize_filename(data.get("title", "film"), max_length=100)
                        if not item.get("output_path"):
                            safe_out = os.path.join(def_dir, f"{safe_title}.mp4")

                        audio_tracks = data.get("audio_tracks", [])
                        video_segments = data.get("video_segments")
                        video_durations = data.get("video_durations")
                        video_url = data.get("video_url")
                        video_headers = data.get("video_headers", {})
                        total_segments = data.get("total_segments", 1000)
                        subtitles = data.get("subtitles", [])
                        thread_count = item.get("thread_count", 16)
                        track_choice = item.get("audio_track_choice", "")

                        if "Çift Sesli" in track_choice and len(audio_tracks) >= 2:
                            success, res = self.queue_engine.run_multi_audio_download(
                                video_url=video_url,
                                audio_tracks=audio_tracks[:2],
                                output_filepath=safe_out,
                                video_headers=video_headers,
                                total_segments=total_segments,
                                thread_count=thread_count,
                                progress_callback=q_cb,
                                video_segments=video_segments,
                                video_durations=video_durations,
                                subtitles=subtitles,
                                keep_external_srt=should_keep_external_srt(),
                                recovery_url=data.get("raw_url") or url,
                            )
                        elif data.get("direct_file") and not video_segments:
                            success, res = self.queue_engine.download_direct_file(
                                url=video_url,
                                output_filepath=safe_out,
                                custom_headers=video_headers,
                                progress_callback=q_cb
                            )
                        else:
                            has_separate_audio = False
                            selected_audio = audio_tracks[0] if audio_tracks else None
                            if selected_audio:
                                if video_segments and selected_audio.get("segments") and video_segments != selected_audio.get("segments"):
                                    has_separate_audio = True
                                elif video_url and selected_audio.get("sample_segment_url") and video_url != selected_audio.get("sample_segment_url"):
                                    has_separate_audio = True
                                elif "imageaud" in selected_audio.get("sample_segment_url", "") and "image2_" in (video_url or ""):
                                    has_separate_audio = True

                            if has_separate_audio and selected_audio:
                                success, res = self.queue_engine.run_dual_stream_download(
                                    video_url=video_url,
                                    audio_url=selected_audio["sample_segment_url"],
                                    output_filepath=safe_out,
                                    video_headers=video_headers,
                                    audio_headers=selected_audio.get("headers", video_headers),
                                    total_segments=selected_audio.get("count", total_segments),
                                    thread_count=thread_count,
                                    progress_callback=q_cb,
                                    video_segments=video_segments,
                                    audio_segments=selected_audio.get("segments"),
                                    video_durations=selected_audio.get("video_durations") or video_durations,
                                    audio_durations=selected_audio.get("durations"),
                                    subtitles=subtitles,
                                    keep_external_srt=should_keep_external_srt(),
                                    recovery_url=data.get("raw_url") or url,
                                )
                            else:
                                target_url = selected_audio["sample_segment_url"] if selected_audio else video_url
                                target_headers = selected_audio.get("headers", video_headers) if selected_audio else video_headers
                                seg_list = selected_audio.get("segments") if selected_audio else video_segments
                                track_count = selected_audio.get("count", total_segments) if selected_audio else total_segments
                                success, res = self.queue_engine.run_download(
                                    sample_url=target_url,
                                    output_filepath=safe_out,
                                    custom_headers=target_headers,
                                    total_segments=track_count,
                                    segment_urls=seg_list,
                                    thread_count=thread_count,
                                    progress_callback=q_cb,
                                    subtitles=subtitles,
                                    keep_external_srt=should_keep_external_srt(),
                                    recovery_url=data.get("raw_url") or url,
                                )

                    if success:
                        item["status"] = "Tamamlandı"
                        item["progress"] = 1.0
                        self._update_queue_item_progress(item_id, "Tamamlandı", 1.0, title=f"{item['title']}", color=T.SUCCESS)
                        file_sz = os.path.getsize(safe_out) if os.path.exists(safe_out) else 0
                        m_type = "Dizi / Kuyruk" if any(k in item.get("title", "").lower() for k in ["sezon", "bölüm", "episode", "s0", "s1", "s2"]) else "Kuyruk İndirmesi"
                        add_history_entry(item["title"] or os.path.basename(safe_out), safe_out, size_bytes=file_sz, source_url=url, media_type=m_type)
                        self.after(0, self._refresh_history_ui)
                    elif self.is_queue_paused or not self.is_queue_running:
                        item["status"] = "⏸️ Duraklatıldı"
                        self._update_queue_item_progress(item_id, "⏸️ Duraklatıldı", item.get("progress", 0.0), color=T.WARNING)
                    elif item.get("status") == "İptal Edildi ⏹️":
                        self._update_queue_item_progress(item_id, "İptal Edildi ⏹️", 0.0, color=T.DANGER)
                    else:
                        item["status"] = "Hata"
                        self._update_queue_item_progress(item_id, "Hata", 0.0, color=T.DANGER)
                except Exception as e:
                    if self.is_queue_paused or not self.is_queue_running:
                        item["status"] = "⏸️ Duraklatıldı"
                        self._update_queue_item_progress(item_id, "⏸️ Duraklatıldı", item.get("progress", 0.0), color=T.WARNING)
                    elif item.get("status") == "İptal Edildi ⏹️":
                        self._update_queue_item_progress(item_id, "İptal Edildi ⏹️", 0.0, color=T.DANGER)
                    else:
                        err_msg = str(e)[:25]
                        item["status"] = f"Hata: {err_msg}"
                        self._update_queue_item_progress(item_id, f"Hata: {err_msg}", 0.0, color=T.DANGER)
                finally:
                    self.current_queue_item_id = None

            self.is_queue_running = False
            self.current_queue_item_id = None
            if not self.is_queue_paused:
                self.after(0, lambda: self.btn_q_start.configure(state="normal", text="▶ Kuyruğu Başlat (Sırayla İndir)"))
                self.after(0, lambda: self.btn_q_stop.configure(state="normal", text="⏸️ Duraklat", fg_color=T.BG_CARD, hover_color=T.BORDER))
                self._set_status("Kuyruk İşlemleri Bitti", color=T.SUCCESS)
                self._play_notification_sound()
                self._send_desktop_notification("Kuyruk Tamamlandı", "Tüm kuyruk indirmeleri başarıyla tamamlandı.")
                self.after(0, self._handle_shutdown)

        self.queue_thread = threading.Thread(target=worker, daemon=True)
        self.queue_thread.start()

    def _update_queue_item_progress(self, item_id, status_text, progress_ratio, title=None, color=None):
        def update():
            if item_id in self.queue_row_widgets:
                w = self.queue_row_widgets[item_id]
                try:
                    w["pbar"].set(max(0.0, min(1.0, progress_ratio)))
                    c = color or (T.SUCCESS if "Tamamlandı" in status_text else (T.WARNING if "İndiriliyor" in status_text else (T.DANGER if "Hata" in status_text or "İptal" in status_text else T.TEXT_MUTED)))
                    w["lbl_st"].configure(text=status_text, text_color=c)
                    if title:
                        w["lbl_name"].configure(text=f"{title} - {w['url'][:40]}...")
                except Exception:
                    logger.debug("[ui.controllers.queue] _update_queue_item_progress.update() sessiz istisna yutuldu", exc_info=True)
        self.after(0, update)

    def _add_current_film_to_queue(self):
        url = self.entry_film_page.get().strip()
        if not url and not self.resolved_film_data:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen önce bir film linki girin veya çözümleyin.")
            return

        out_path = self.entry_output.get().strip() if hasattr(self, 'entry_output') else ""
        selected_audio_text = self.opt_audio_track.get() if hasattr(self, 'opt_audio_track') else ""

        title = "Film"
        if self.resolved_film_data:
            title = self.resolved_film_data.get("title") or (os.path.splitext(os.path.basename(out_path))[0] if out_path else "Film")
        elif out_path:
            title = os.path.splitext(os.path.basename(out_path))[0]
        else:
            title = f"Film #{len(self.download_queue)+1}"

        item = {
            "id": int(time.time() * 1000),
            "url": url or (self.resolved_film_data.get("raw_url") if self.resolved_film_data else ""),
            "title": title[:100],
            "status": "Bekliyor",
            "progress": 0.0,
            "resolved_data": self.resolved_film_data,
            "output_path": out_path,
            "audio_track_choice": selected_audio_text,
            "thread_count": int(self.slider_threads.get()) if hasattr(self, 'slider_threads') else 16
        }
        self.download_queue.append(item)
        self._refresh_queue_ui()
        self._set_status(f"'{title[:20]}' Kuyruğa Eklendi", color=T.SUCCESS)
        if messagebox:
            messagebox.showinfo("Kuyruğa Eklendi", f"'{title}' başarıyla indirme kuyruğuna eklendi!\n'Dizi & Kuyruk' sekmesinden sırayla indirebilirsiniz.")

    def _add_current_yt_to_queue(self):
        url = self.entry_yt_url.get().strip()
        if not url:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen kuyruğa eklemek için bir YouTube/Medya linki girin.")
            return

        out_dir = self.entry_yt_dir.get().strip() if hasattr(self, 'entry_yt_dir') else ""
        fmt_choice = self.opt_yt_format.get() if hasattr(self, 'opt_yt_format') else "En Yüksek Kalite"
        if "MP3" in fmt_choice:
            fmt = "mp3"
        elif "720p" in fmt_choice:
            fmt = "720p"
        elif "1080p" in fmt_choice:
            fmt = "1080p"
        else:
            fmt = "best"

        cookie_choice = self.opt_yt_cookies.get() if hasattr(self, 'opt_yt_cookies') else ""
        cookie_file_path = self.entry_cookie_file.get().strip() if hasattr(self, 'entry_cookie_file') else ""
        browser_choice = None
        if "Chrome" in cookie_choice:
            browser_choice = "chrome"
        elif "Edge" in cookie_choice:
            browser_choice = "edge"
        elif "Firefox" in cookie_choice:
            browser_choice = "firefox"
        elif "Brave" in cookie_choice:
            browser_choice = "brave"

        item = {
            "id": int(time.time() * 1000),
            "url": url,
            "title": f"Sosyal #{len(self.download_queue)+1}",
            "status": "Bekliyor",
            "progress": 0.0,
            "format_choice": fmt,
            "output_dir": out_dir,
            "browser_choice": browser_choice,
            "cookie_file": cookie_file_path if (cookie_file_path and os.path.exists(cookie_file_path)) else None
        }
        self.download_queue.append(item)
        self._refresh_queue_ui()
        self._set_status("Kuyruğa Eklendi", color=T.SUCCESS)
        if messagebox:
            messagebox.showinfo("Kuyruğa Eklendi", f"'{url[:40]}...' başarıyla indirme kuyruğuna eklendi!\n'Dizi & Kuyruk' sekmesinden yönetebilirsiniz.")
