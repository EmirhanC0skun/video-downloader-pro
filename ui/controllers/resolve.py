# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Film & Web Media Resolution Controller Mixin.
Handles pasting URLs, cURL imports, threaded HLS resolution, and quality switching.
"""

import os
import re
import threading
try:
    from tkinter import messagebox
except Exception:
    messagebox = None

from logger import get_logger
from engine import parse_curl_command, sanitize_filename, fix_mojibake
from extractor import resolve_film_page
from ui import widgets as W
from ui import theme as T
from ui.config import translate_user_friendly_error, get_default_download_directory

logger = get_logger("ui.controllers.resolve")


class ResolveControllerMixin:
    """
    Mixin managing film and web URL resolution, cURL parsing, and quality/audio variant updates.
    """

    def _paste_film_url(self):
        try:
            t = self.clipboard_get()
            val = t.strip()
            if val:
                self.entry_film_page.delete(0, "end")
                self.entry_film_page.insert(0, val)
                self._check_smart_mode_suggestion(val)
                self._log(f"📋 Link panodan yapıştırıldı: {val[:60]}...")
        except Exception:
            logger.debug("[ui.controllers.resolve] _paste_film_url() sessiz istisna yutuldu", exc_info=True)

    def _import_from_curl(self):
        try:
            clipboard_text = self.clipboard_get()
            if not clipboard_text or ("curl" not in clipboard_text and "http" not in clipboard_text):
                if messagebox:
                    messagebox.showinfo("cURL İçe Aktar", "Lütfen panoya kopyalanan cURL komutunu yapıştırın.")
                return

            url, headers = parse_curl_command(clipboard_text)
            if url:
                self.entry_film_page.delete(0, "end")
                self.entry_film_page.insert(0, url)
                self.custom_headers = headers
                self._log(f"[✓] cURL içe aktarıldı ({len(headers)} başlık)")
                if messagebox:
                    messagebox.showinfo("Başarılı", f"cURL çözümlendi!\nURL: {url[:50]}...\nBaşlık: {len(headers)}")
        except Exception as e:
            if messagebox:
                messagebox.showerror("Hata", f"cURL hatası: {e}")

    def _on_audio_track_changed(self, choice):
        if hasattr(self, 'btn_start'):
            clean_choice = choice.split('(')[0].strip()
            self.btn_start.configure(text=f"▶ İndir ({clean_choice})", state="normal")
            self.progress_bar.set(0.0)
            self.lbl_progress_text.configure(text="0%")
            self.lbl_speed_text.configure(text="0.00 MB/s")
            self.lbl_size_text.configure(text="0.0 MB")
            self._set_status("Hazır", color=T.TEXT)

    def _resolve_film_threaded(self, _from_router=False):
        film_url = self.entry_film_page.get().strip()
        recovery_candidate = getattr(self, "_recovery_resume_candidate", None)
        if hasattr(self, "_recovery_resume_candidate"):
            delattr(self, "_recovery_resume_candidate")
        if not film_url:
            if messagebox:
                messagebox.showwarning("Eksik Bilgi", "Lütfen bir film veya medya linki girin.")
            return

        if "curl " in film_url.lower() or "-h " in film_url.lower():
            try:
                c_url, c_headers = parse_curl_command(film_url)
                if c_url:
                    self.entry_film_page.delete(0, "end")
                    self.entry_film_page.insert(0, c_url)
                    self.custom_headers = c_headers
                    film_url = c_url
                    self._log(f"[+] cURL komutu otomatik algılandı ({len(c_headers)} başlık)")
            except Exception:
                logger.debug("[ui.controllers.resolve] _resolve_film_threaded cURL algılama istisnası", exc_info=True)

        self.btn_resolve.configure(state="disabled", text="Çözülüyor...")
        self._set_status("Çözümleniyor...", color=T.PRIMARY_LIGHT)

        def apply_result(data):
            try:
                self.resolved_film_data = data
                title = fix_mojibake(data.get("title", "Film"))

                def apply_ui():
                    self.lbl_resolved_title.configure(text=W.elide(title, 46))
                    self.lbl_resolved_url.configure(
                        text=W.elide(self.entry_film_page.get().strip(), 68))

                    qualities = data.get("qualities", [])
                    if qualities and hasattr(self, 'opt_quality'):
                        qual_labels = [q["label"] for q in qualities]
                        self.opt_quality.configure(values=qual_labels)
                        self.opt_quality.set(qual_labels[0])
                    elif hasattr(self, 'opt_quality'):
                        self.opt_quality.configure(values=["🌟 En Yüksek Kalite"])
                        self.opt_quality.set("🌟 En Yüksek Kalite")

                    audio_tracks = data.get("audio_tracks", [])
                    if audio_tracks:
                        track_names = []
                        is_single = (len(audio_tracks) == 1)
                        for a in audio_tracks:
                            name = a.get("name", "")
                            lang = a.get("lang", "").lower()
                            seg_count = a.get('count', data.get('total_segments', 0))
                            seg_str = f" ({seg_count} Parça)" if seg_count > 0 else ""
                            if is_single:
                                if "dublaj" in name.lower() or ("dublaj" in title.lower() and "altyaz" not in title.lower()):
                                    flag_name = f"🇹🇷 Türkçe Dublaj{seg_str}"
                                elif "altyaz" in name.lower() or "altyaz" in title.lower():
                                    flag_name = f"🇬🇧 Orijinal / Türkçe Altyazılı{seg_str}"
                                else:
                                    flag_name = f"🎬 {name or 'Standart / Orijinal Akış'}{seg_str}"
                            else:
                                if "dublaj" in name.lower():
                                    flag_name = f"🇹🇷 Dublaj{seg_str}"
                                elif "altyaz" in name.lower():
                                    flag_name = f"🇬🇧 Orijinal / Türkçe Altyazılı{seg_str}"
                                elif "ing" in name.lower() or "eng" in lang or "orijinal" in name.lower() or "original" in name.lower():
                                    flag_name = f"🇬🇧 Orijinal / İngilizce{seg_str}"
                                elif "turk" in name.lower() or "tur" in lang:
                                    flag_name = f"🇹🇷 Dublaj{seg_str}"
                                else:
                                    flag_name = f"🎬 {name}{seg_str}"
                            track_names.append(flag_name)

                        if len(audio_tracks) >= 2:
                            dual_name = "🌟 Çift Sesli (Dublaj + İngilizce) [Tek MP4]"
                            track_names.append(dual_name)
                            default_track = dual_name
                        else:
                            default_track = track_names[0]

                        self.opt_audio_track.configure(values=track_names)
                        self.opt_audio_track.set(default_track)
                        self.btn_start.configure(
                            text=f"İndir ({default_track.split('(')[0].strip()})")
                        self._log("💡 Bilgi: Çift Sesli seçildiğinde film tek MP4 olarak iner ve medya oynatıcınızda (VLC / Windows Media) Ses menüsünden dil değiştirilebilir.")
                    else:
                        self.opt_audio_track.configure(values=["Dahili Akış"])
                        self.opt_audio_track.set("Dahili Akış")
                        self.btn_start.configure(text="İndir (Tek Akış)")

                    recovery_output = (
                        recovery_candidate.get("output_filepath", "").strip()
                        if recovery_candidate else ""
                    )
                    if recovery_output:
                        out_path = recovery_output
                    else:
                        safe_title = sanitize_filename(title, max_length=100)
                        cur_dir = ""
                        if hasattr(self, 'entry_output'):
                            raw_val = self.entry_output.get().strip()
                            if raw_val:
                                cur_dir = os.path.dirname(raw_val)
                        if not cur_dir or not os.path.exists(cur_dir):
                            cur_dir = get_default_download_directory()
                        out_path = os.path.join(cur_dir, f"{safe_title}.mp4")
                    self.entry_output.delete(0, "end")
                    self.entry_output.insert(0, out_path)

                    subs = data.get("subtitles") or []
                    sub_sum = None
                    if subs:
                        sub_label = subs[0].get('name') or subs[0].get('label') or 'Türkçe'
                        sub_sum = f"🇹🇷 {sub_label} (Otomatik Gömülecek + .SRT)"
                        sub_names = ", ".join([s.get('name') or s.get('label') or 'Altyazı' for s in subs[:3]])
                        self._log(f"[+] 📝 Altyazı algılandı: {sub_names} — MP4 içine gömülecek ve harici .srt olarak kaydedilecek.")

                    self._set_film_meta(data)
                    self._set_film_state("cozumlendi")
                    self._set_status("Çözüldü", color=T.SUCCESS,
                                     detail=W.elide(title, 26))

                    q_sum = self.opt_quality.get() if hasattr(self, 'opt_quality') else "🌟 En Yüksek Kalite"
                    tot_segs = data.get('total_segments', 0)
                    sz_sum = f"~{(tot_segs * 1.8):.0f} MB ({tot_segs} Parça)" if tot_segs > 0 else "Dinamik HLS Akışı"
                    aud_sum = self.opt_audio_track.get() if hasattr(self, 'opt_audio_track') else "Standart Ses"

                    if recovery_candidate:
                        self._log("[i] Kurtarma kaynağı yeniden çözüldü; diskteki parçalarla indirme devam ettiriliyor...")
                        self._start_film_download_threaded()
                    else:
                        try:
                            self._show_resolution_modal(
                                title=title,
                                media_type="Film",
                                quality_summary=q_sum,
                                size_summary=sz_sum,
                                audio_summary=aud_sum,
                                on_download=self._start_film_download_threaded,
                                on_queue=self._add_current_film_to_queue,
                                subtitle_summary=sub_sum
                            )
                        except Exception:
                            logger.debug("[ui.controllers.resolve] cozumleme modali acilamadi", exc_info=True)

                try:
                    self.after_idle(apply_ui)
                except Exception:
                    logger.debug(
                        "[ui.controllers.resolve] apply_ui ana Tk kuyruğuna alınamadı",
                        exc_info=True,
                    )

            except Exception as e:
                friendly_msg = translate_user_friendly_error(str(e))
                logger.exception("Cozumleme sonucu arayuze uygulanamadi")
                self._log(f"[HATA] Çözümleme başarısız: {e}")
                self._set_status("Hata", color=T.DANGER)
                try:
                    self.after_idle(lambda: messagebox.showerror("Çözümleme Hatası", friendly_msg))
                except Exception:
                    logger.debug("[ui.controllers.resolve] hata modali acilamadi", exc_info=True)
            finally:
                try:
                    self.after_idle(lambda: self.btn_resolve.configure(state="normal", text="Çözümle"))
                except Exception:
                    logger.debug("[ui.controllers.resolve] btn_resolve eski haline getirilemedi", exc_info=True)

        def apply_error(err):
            try:
                self._log(f"[HATA] Çözümleme başarısız: {err}")
                self._set_status("Hata", color=T.DANGER)
                if messagebox:
                    messagebox.showerror("Çözümleme Hatası", translate_user_friendly_error(str(err)))
            finally:
                self.btn_resolve.configure(state="normal", text="Çözümle")

        def task():
            try:
                data = resolve_film_page(film_url, log_callback=self._log)
            except Exception as e:
                try:
                    self.after(0, lambda err=e: apply_error(err))
                except Exception:
                    logger.debug("[ui.controllers.resolve] after apply_error fırlatıldı", exc_info=True)
                return
            try:
                self.after(0, lambda d=data: apply_result(d))
            except Exception:
                logger.debug("[ui.controllers.resolve] after apply_result fırlatıldı", exc_info=True)

        threading.Thread(target=task, daemon=True).start()

    def _on_quality_changed(self, choice):
        """Kullanıcı açılır menüden çözünürlük/kalite değiştirdiğinde yeni akış segmentlerini yükler."""
        if not self.resolved_film_data or not self.resolved_film_data.get("qualities"):
            return
        qualities = self.resolved_film_data.get("qualities", [])
        chosen_variant = next((q for q in qualities if q["label"] == choice), None)
        if not chosen_variant or not chosen_variant.get("url"):
            return

        self._log(f"[i] 🎬 Çözünürlük değiştiriliyor: {chosen_variant['label']}")
        target_url = chosen_variant["url"]
        headers = self.resolved_film_data.get("video_headers", {})

        if chosen_variant.get("direct_file"):
            self.resolved_film_data["video_url"] = target_url
            self.resolved_film_data["video_segments"] = None
            self.resolved_film_data["total_segments"] = 1
            self.resolved_film_data["direct_file"] = True
            self._log(f"[+] Doğrudan dosya kalitesi seçildi: {chosen_variant['label']}")
            return

        def fetch_quality_segments():
            try:
                import requests as py_req
                from urllib.parse import urljoin
                from curl_cffi import requests as c_req
                r = c_req.get(target_url, headers=headers, impersonate="chrome124", timeout=12) if c_req else py_req.get(target_url, headers=headers, timeout=12)
                if r.status_code == 200:
                    init_match = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']', r.text)
                    init_seg = [urljoin(target_url, init_match.group(1))] if init_match else []
                    new_segs = init_seg + [urljoin(target_url, l.strip()) for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
                    if new_segs:
                        self.resolved_film_data["video_segments"] = new_segs
                        self.resolved_film_data["total_segments"] = len(new_segs)
                        self.resolved_film_data["video_url"] = target_url

                        def update_ui():
                            self._log(f"[+] Kalite güncellendi ({len(new_segs)} parça): {chosen_variant['label']}")
                            cur_title = self.resolved_film_data.get("title", "Film")
                            short_q = chosen_variant['label'].split('(')[0].strip()
                            self.lbl_resolved_title.configure(text=f"🎬 {cur_title[:32]}... [{short_q}] ({len(new_segs)} Parça)")
                        self.after(0, update_ui)
            except Exception as ex:
                self._log(f"[!] Kalite akışı yükleme notu: {ex}")

        threading.Thread(target=fetch_quality_segments, daemon=True).start()
