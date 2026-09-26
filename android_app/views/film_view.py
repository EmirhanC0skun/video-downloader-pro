# -*- coding: utf-8 -*-
"""Film & Web — medya çözümleme ve indirme ekranı.

Masaüstündeki `ui/views/film.py` ile aynı üç durumlu akışı taşır:

    bos  ->  cozumlendi  ->  indiriliyor

Her durum ayrı bir kapsayıcıdır ve yalnızca biri görünür olur. Ekranı tek bir
uzun forma yığmak yerine bölmek, mobilde asıl kazancı verir: kullanıcı her
adımda yalnızca o adıma ait kontrolleri görür (aşamalı açığa çıkarma), ve
durum değiştirmek widget'ları yeniden kurmadığı için arka plan iş
parçacığından gelen ilerleme güncellemeleri hedefini şaşırmaz.
"""

import os
import re
import time
import threading
import flet as ft

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging

        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("views.film")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W

from mobile_engine import translate_user_friendly_error

# Sosyal medya alan adlari — Akilli Yonlendirici bu linkleri Sosyal sekmesine
# devreder.
SOCIAL_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com",
                "twitter.com", "x.com", "vimeo.com")


def _request_quality_manifest(target_url, headers):
    """Fetch a quality playlist with the optional TLS client when available."""
    import requests as standard_requests

    try:
        from curl_cffi import requests as curl_requests
    except Exception:
        curl_requests = None

    if curl_requests:
        return curl_requests.get(
            target_url,
            headers=headers,
            impersonate="chrome124",
            timeout=12,
        )
    return standard_requests.get(target_url, headers=headers, timeout=12)


def format_seconds(secs):
    if secs is None or secs < 0 or secs > 86400 * 30:
        return "--:--"
    secs = int(secs)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def thread_profile(value: int) -> str:
    """Kanal sayısını okunur bir hız profiline çevirir."""
    if value >= 48:
        return "Maksimum"
    if value >= 32:
        return "Turbo"
    if value >= 16:
        return "Yüksek"
    if value >= 8:
        return "Hızlı"
    return "Dengeli"


def build_film_view(page: ft.Page, controller, initial_url=None, auto_resolve=False):
    """Film & Web ekranını kurar ve döndürür."""
    resolved_data = {}
    timer_active = [False]
    current_eta_str = ["--:--"]
    last_downloaded_file = [None]

    # =====================================================================
    # Durum 1 — bos: link girisi
    # =====================================================================
    txt_url = W.text_field(
        "Film veya dizi linki",
        hint="https://… film sayfası veya cURL",
        value=initial_url or "",
        icon=ft.Icons.LINK_ROUNDED,
        expand=True,
    )

    def paste_clipboard():
        try:
            val = page.get_clipboard()
        except Exception:
            logger.debug("[views.film] pano okunamadi", exc_info=True)
            return
        if not val:
            return
        val_clean = val.strip()
        txt_url.value = val_clean
        page.update()
        # Akilli Yonlendirici: sosyal medya linki bu ekrana ait degil.
        if any(host in val_clean.lower() for host in SOCIAL_HOSTS):
            W.snack(page, "Sosyal medya linki algılandı, Sosyal sekmesine aktarılıyor.")
            controller.switch_tab(1, url=val_clean, auto_resolve=True)

    slider_threads = ft.Slider(
        min=2, max=64, divisions=62, value=32,
        active_color=T.PRIMARY, inactive_color=T.BG_APP,
    )
    lbl_threads = W.label("Kanal: 32x", size=T.SIZE_SM, weight=T.W_BOLD,
                          color=T.TEXT_MUTED)
    lbl_thread_profile = W.label("Turbo", size=T.SIZE_XS, weight=T.W_BOLD,
                                 color=T.TEXT_DIM)

    def on_threads_changed(e):
        value = int(e.control.value)
        lbl_threads.value = f"Kanal: {value}x"
        lbl_thread_profile.value = thread_profile(value)
        try:
            lbl_threads.update()
            lbl_thread_profile.update()
        except Exception:
            logger.debug("[views.film] kanal etiketi guncellenemedi", exc_info=True)

    slider_threads.on_change = on_threads_changed

    txt_output_dir = W.text_field("Kayıt klasörü", value=controller.download_dir,
                                  expand=True)

    def apply_output_dir():
        target = (txt_output_dir.value or "").strip()
        if not target:
            return
        if controller.set_download_dir(target):
            W.snack(page, "Kayıt klasörü güncellendi.", T.SUCCESS_FILL)
        else:
            W.snack(page, "Klasör oluşturulamadı, eski yol korundu.", T.DANGER_FILL)
            txt_output_dir.value = controller.download_dir
            page.update()

    advanced = W.Collapsible(
        "Gelişmiş", "kanal sayısı · kayıt yolu",
        body_controls=[
            ft.Row([lbl_threads, ft.Container(expand=True), lbl_thread_profile]),
            slider_threads,
            ft.Row(
                [txt_output_dir,
                 W.ghost_button("Uygula", lambda e: apply_output_dir(),
                                height=T.H_BUTTON_SM)],
                spacing=T.GAP_TOUCH,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
    )

    recent_list = ft.Column(spacing=T.GAP_TOUCH, tight=True)

    def refresh_recent():
        """`Son indirilenler` şeridini diskteki son üç dosyayla doldurur."""
        recent_list.controls.clear()
        try:
            files = controller.get_completed_files()[:3]
        except Exception:
            logger.debug("[views.film] son indirilenler okunamadi", exc_info=True)
            files = []
        if not files:
            recent_list.controls.append(
                W.label("Henüz indirilmiş medya yok.", size=T.SIZE_SM,
                        color=T.TEXT_DIM)
            )
        else:
            for item in files:
                is_audio = item.get("is_audio")
                recent_list.controls.append(
                    W.list_row(
                        item["name"],
                        f"{item['size_mb']} MB · {item['date']}",
                        icon=(ft.Icons.AUDIOTRACK_ROUNDED if is_audio
                              else ft.Icons.MOVIE_ROUNDED),
                        icon_fill=(T.ICON_FILL_AUDIO if is_audio
                                   else T.ICON_FILL_VIDEO),
                        icon_color=(T.PURPLE_LIGHT if is_audio else T.PRIMARY_LIGHT),
                        actions=[(
                            ft.Icons.PLAY_ARROW_ROUNDED, "Oynat",
                            lambda p=item["path"]: controller.open_file_externally(p),
                            T.SUCCESS,
                        )],
                    )
                )
        try:
            recent_list.update()
        except Exception:
            logger.debug("[views.film] son indirilenler cizilemedi", exc_info=True)

    prg_resolve = ft.ProgressRing(visible=False, width=18, height=18,
                                  stroke_width=2, color=T.PRIMARY_LIGHT)
    btn_resolve = W.primary_button("Çözümle", lambda e: start_resolve_threaded(),
                                   icon=ft.Icons.SEARCH_ROUNDED, expand=True)

    state_idle = ft.Column(
        spacing=T.SECTION_GAP,
        tight=True,
        controls=[
            W.card(
                ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        # Alanin kendi ustte duran etiketi zaten "Film veya dizi
                        # linki" diyor; ustune ayri bir baslik koymak ayni sozu
                        # iki kez yazdiriyordu.
                        txt_url,
                        ft.Row(
                            [
                                W.ghost_button("Yapıştır", lambda e: paste_clipboard(),
                                               icon=ft.Icons.CONTENT_PASTE_ROUNDED,
                                               expand=1),
                                btn_resolve,
                                prg_resolve,
                            ],
                            spacing=T.GAP_TOUCH,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        W.step_hint(["Linki yapıştır", "Çözümle", "Kaliteyi seç"]),
                    ],
                )
            ),
            advanced,
            ft.Column(
                spacing=T.GAP_TOUCH,
                tight=True,
                controls=[
                    ft.Row([
                        W.section_label("Son indirilenler"),
                        ft.Container(expand=True),
                        W.link("Tümünü gör", lambda: controller.switch_tab(4)),
                    ]),
                    recent_list,
                ],
            ),
        ],
    )

    # =====================================================================
    # Durum 2 — cozumlendi: kalite / ses secimi
    # =====================================================================
    lbl_resolved_url = W.label("", size=T.SIZE_SM, weight=T.W_SEMI,
                               color=T.TEXT_MUTED, max_lines=1,
                               overflow=ft.TextOverflow.ELLIPSIS, expand=True)
    lbl_resolved_title = W.label("Medya", size=T.SIZE_TITLE, weight=T.W_EXTRA,
                                 max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
    resolved_meta = ft.Row(spacing=6, wrap=True, run_spacing=6)

    pills_quality = W.PillGroup(on_select=lambda v: on_quality_selected(v),
                                empty_text="Kalite bulunamadı")
    pills_audio = W.PillGroup(empty_text="Ses kanalı bulunamadı")

    lbl_save_hint = W.label("", size=T.SIZE_XS, weight=T.W_SEMI, color=T.TEXT_MUTED)

    state_resolved = ft.Column(
        spacing=T.SECTION_GAP,
        tight=True,
        controls=[
            W.card(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=T.SUCCESS, size=18),
                        lbl_resolved_url,
                        W.link("Değiştir", lambda: set_state("bos")),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                radius=T.R_TILE,
                pad=W.padding(12, 4, 4, 4),
            ),
            W.card(
                ft.Column(
                    spacing=14,
                    tight=True,
                    controls=[
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(ft.Icons.MOVIE_ROUNDED,
                                                    color=T.PRIMARY, size=24),
                                    bgcolor=T.BG_APP,
                                    border_radius=10,
                                    width=64,
                                    height=56,
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Column([lbl_resolved_title, resolved_meta],
                                          spacing=6, tight=True, expand=True),
                            ],
                            spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        W.divider(),
                        W.section_label("Kalite"),
                        pills_quality,
                        W.section_label("Ses"),
                        pills_audio,
                        W.divider(),
                        ft.Row(
                            [
                                W.success_button("İndir",
                                                 lambda e: start_download_threaded(),
                                                 icon=ft.Icons.DOWNLOAD_ROUNDED,
                                                 expand=2),
                                W.ghost_button("Sıraya ekle",
                                               lambda e: add_to_queue_click(),
                                               icon=ft.Icons.PLAYLIST_ADD_ROUNDED,
                                               expand=1),
                            ],
                            spacing=T.GAP_TOUCH,
                        ),
                        lbl_save_hint,
                    ],
                )
            ),
        ],
    )

    # =====================================================================
    # Durum 3 — indiriliyor: ilerleme
    # =====================================================================
    lbl_dl_title = W.label("İndiriliyor", size=T.SIZE_LG, weight=T.W_EXTRA,
                           max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    lbl_dl_status = W.label("Hazırlanıyor…", size=T.SIZE_SM, weight=T.W_SEMI,
                            color=T.TEXT_MUTED)
    lbl_dl_percent = W.label("0%", size=T.SIZE_HERO, weight=T.W_SEMI, mono=True)
    pbar_download = W.progress_bar(0.0, height=8)

    tile_speed, lbl_speed = W.stat_tile("Hız", "0.00 MB/s", T.WARNING)
    tile_eta, lbl_eta = W.stat_tile("Kalan", "--:--")
    tile_elapsed, lbl_elapsed = W.stat_tile("Geçen", "00:00")
    tile_size, lbl_size = W.stat_tile("Boyut", "0.0 MB")

    btn_pause = W.warning_button("Duraklat", lambda e: toggle_pause_resume(),
                                 icon=ft.Icons.PAUSE_ROUNDED, expand=1)
    btn_cancel = W.danger_button("İptal", lambda e: cancel_download(),
                                 icon=ft.Icons.STOP_CIRCLE_ROUNDED, expand=1)
    btn_play_finished = W.success_button(
        "İndirileni oynat",
        lambda e: (controller.open_file_externally(last_downloaded_file[0])
                   if last_downloaded_file[0] else None),
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        height=T.H_BUTTON_SM,
    )
    btn_play_finished.visible = False
    btn_back_to_card = W.ghost_button(
        "Çözücüye Dön",
        lambda e: set_state("cozumlendi" if resolved_data else "bos"),
        icon=ft.Icons.ARROW_BACK_ROUNDED,
        height=T.H_BUTTON_SM,
    )
    btn_back_to_card.visible = False

    txt_logs = W.label(
        "Hazır. Film linkini yapıştırıp 'Çözümle' düğmesine dokunun.",
        size=T.SIZE_SM, color=T.TEXT_MUTED)
    log_panel = W.Collapsible("İşlem günlüğü", "", expanded=False,
                              body_controls=[W.log_strip(txt_logs)])

    state_downloading = ft.Column(
        spacing=T.SECTION_GAP,
        tight=True,
        controls=[
            W.card(
                ft.Column(
                    spacing=14,
                    tight=True,
                    controls=[
                        ft.Row(
                            [
                                ft.Column([lbl_dl_title, lbl_dl_status], spacing=4,
                                          tight=True, expand=True),
                                lbl_dl_percent,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=12,
                        ),
                        pbar_download,
                        # Dar ekranda dort kutu tek satira sigmaz; ikiserli iki
                        # satir her genislikte okunur kalir.
                        ft.Row([tile_speed, tile_eta], spacing=T.GAP_TOUCH),
                        ft.Row([tile_elapsed, tile_size], spacing=T.GAP_TOUCH),
                        ft.Row([btn_pause, btn_cancel], spacing=T.GAP_TOUCH),
                        W.full_width(btn_play_finished),
                        W.full_width(btn_back_to_card),
                    ],
                )
            ),
            log_panel,
        ],
    )

    states = {"bos": state_idle, "cozumlendi": state_resolved,
              "indiriliyor": state_downloading}
    current_state = ["bos"]

    def set_state(name: str) -> None:
        """Görünür durumu değiştirir; widget'ları yeniden kurmaz."""
        current_state[0] = name
        for key, frame in states.items():
            frame.visible = key == name
        try:
            page.update()
        except Exception:
            logger.debug("[views.film] durum gecisi cizilemedi", exc_info=True)

    for key, frame in states.items():
        frame.visible = key == "bos"

    # =====================================================================
    # Davranis
    # =====================================================================
    def log_msg(msg):
        txt_logs.value = str(msg)
        try:
            txt_logs.update()
        except Exception:
            logger.debug("[views.film] gunluk yazilamadi", exc_info=True)

    def start_timer_tick():
        timer_active[0] = True

        def tick_loop():
            while timer_active[0]:
                if controller.is_downloading:
                    lbl_elapsed.value = format_seconds(controller.get_elapsed_seconds())
                    lbl_eta.value = current_eta_str[0]
                    try:
                        lbl_elapsed.update()
                        lbl_eta.update()
                    except Exception:
                        logger.debug("[views.film] sayac cizilemedi", exc_info=True)
                time.sleep(1)

        threading.Thread(target=tick_loop, daemon=True).start()

    def toggle_pause_resume():
        if controller.is_paused:
            controller.resume_download()
            _set_button_face(btn_pause, ft.Icons.PAUSE_ROUNDED, "Duraklat", T.WARNING)
            lbl_dl_status.value = "İndiriliyor…"
            log_msg("İndirmeye devam ediliyor…")
        else:
            controller.pause_download()
            _set_button_face(btn_pause, ft.Icons.PLAY_ARROW_ROUNDED, "Devam et",
                             T.SUCCESS)
            lbl_dl_status.value = "Duraklatıldı"
            log_msg("İndirme duraklatıldı.")
        page.update()

    def _set_button_face(button, icon, text, color):
        """Butonun ikon + metnini yerinde değiştirir (yeniden kurmadan)."""
        button.content = ft.Row(
            [ft.Icon(icon, size=18, color=color),
             W.label(text, size=T.SIZE_BASE, weight=T.W_BOLD, color=color)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=8, tight=True,
        )

    def add_to_queue_click():
        if not resolved_data:
            return
        title = resolved_data.get("title", "Film")
        controller.add_queue_item(title, txt_url.value.strip(), media_type="film",
                                  audio_choice=str(pills_audio.index))
        W.snack(page, f"'{W.elide(title, 30)}' kuyruğa eklendi.", T.SUCCESS_FILL)

    def on_quality_selected(value):
        """Seçilen kalitenin çalma listesini indirip segment listesini tazeler."""
        qualities = resolved_data.get("qualities") or []
        index = pills_quality.index
        if not (0 <= index < len(qualities)):
            return
        chosen = qualities[index]
        log_msg(f"Çözünürlük değiştiriliyor: {chosen['label']}")
        target_url = chosen["url"]
        headers = resolved_data.get("video_headers", {})

        def fetch_quality():
            try:
                from urllib.parse import urljoin
                response = _request_quality_manifest(target_url, headers)
                if response.status_code != 200:
                    return
                init_match = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']',
                                       response.text)
                init_segments = ([urljoin(target_url, init_match.group(1))]
                                 if init_match else [])
                segments = init_segments + [
                    urljoin(target_url, line.strip())
                    for line in response.text.splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                if not segments:
                    return
                resolved_data["video_segments"] = segments
                resolved_data["total_segments"] = len(segments)
                resolved_data["video_url"] = target_url
                paint_meta(len(segments),
                           len(resolved_data.get("audio_tracks", [])))
                log_msg(f"Kalite güncellendi: {chosen['label']} "
                        f"({len(segments)} parça)")
            except Exception as error:
                log_msg(f"Kalite yükleme notu: {error}")

        threading.Thread(target=fetch_quality, daemon=True).start()

    def paint_meta(total_segments, audio_count):
        """Başlık altındaki mono meta rozetlerini tazeler."""
        chips = []
        if total_segments:
            chips.append(W.meta_chip(f"{total_segments} parça"))
            chips.append(W.meta_chip(f"~{total_segments * 1.8:.0f} MB"))
        else:
            chips.append(W.meta_chip("dinamik akış"))
        chips.append(W.meta_chip(f"{audio_count or 1} ses"))
        resolved_meta.controls = chips
        try:
            resolved_meta.update()
        except Exception:
            logger.debug("[views.film] meta rozetleri cizilemedi", exc_info=True)

    def start_resolve_threaded():
        url = (txt_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir film linki girin.", T.DANGER_FILL)
            return

        btn_resolve.disabled = True
        prg_resolve.visible = True
        btn_play_finished.visible = False
        log_msg("Film sayfası analiz ediliyor…")
        page.update()

        def task():
            try:
                data = controller.resolve_media_url(url, log_cb=log_msg)
            except Exception as error:
                btn_resolve.disabled = False
                prg_resolve.visible = False
                log_msg(f"Hata: {error}")
                page.update()
                return

            btn_resolve.disabled = False
            prg_resolve.visible = False

            if not (data and data.get("success")):
                log_msg("Medya akışı bulunamadı.")
                W.snack(page, "Medya akışı çözümlenemedi.", T.DANGER_FILL)
                page.update()
                return

            resolved_data.clear()
            resolved_data.update(data)

            audio_tracks = data.get("audio_tracks", [])
            total_segments = data.get("total_segments") or 0
            qualities = data.get("qualities", [])

            lbl_resolved_title.value = data.get("title", "Film medyası")
            lbl_resolved_url.value = W.elide(url, 60)
            paint_meta(total_segments, len(audio_tracks))

            pills_quality.set_values(
                [q["label"] for q in qualities] or ["En yüksek kalite"])

            audio_values = []
            if len(audio_tracks) >= 2:
                audio_values.append("Çift sesli tek MP4 (dublaj + orijinal)")
            audio_values.extend(
                track.get("name", f"Ses kanalı {index + 1}")
                for index, track in enumerate(audio_tracks)
            )
            pills_audio.set_values(audio_values or ["Standart orijinal ses"])

            lbl_save_hint.value = f"Kayıt: {controller.download_dir}"
            log_msg("Medyayı indirmeye hazır.")
            set_state("cozumlendi")

        threading.Thread(target=task, daemon=True).start()

    def _selected_audio_tracks():
        """Pill seçimini motorun beklediği ses kanalı listesine çevirir."""
        audio_tracks = resolved_data.get("audio_tracks") or []
        if not audio_tracks:
            return []
        index = pills_audio.index
        dual_offered = len(audio_tracks) >= 2
        if dual_offered and index == 0:
            return audio_tracks[:2]
        # Cift sesli secenek listenin basina eklendiginde kanallar bir kayar.
        track_index = index - 1 if dual_offered else index
        if 0 <= track_index < len(audio_tracks):
            return [audio_tracks[track_index]]
        return [audio_tracks[0]]

    def start_download_threaded():
        if not resolved_data:
            return

        set_state("indiriliyor")
        lbl_dl_title.value = W.elide(resolved_data.get("title", "Film"), 40)
        lbl_dl_status.value = "Başlatılıyor…"
        lbl_dl_percent.value = "0%"
        pbar_download.value = 0.0
        lbl_speed.value = "0.00 MB/s"
        lbl_size.value = "0.0 MB"
        lbl_elapsed.value = "00:00"
        lbl_eta.value = "--:--"
        current_eta_str[0] = "--:--"
        btn_play_finished.visible = False
        btn_back_to_card.visible = False
        _set_button_face(btn_pause, ft.Icons.PAUSE_ROUNDED, "Duraklat", T.WARNING)

        controller.start_download_session(resolved_data.get("title", "film"))
        start_timer_tick()
        log_msg("İndirme başlatıldı…")
        page.update()

        last_update_time = [0.0]
        max_ratio = [0.0]
        max_completed = [0]
        dl_start_time = time.time()

        def on_prog(completed, total, total_bytes=0, speed_bps=0, *args):
            now = time.time()
            is_final = total > 0 and completed >= total
            if not is_final and (now - last_update_time[0] < 0.06):
                return
            last_update_time[0] = now

            calc_ratio = completed / total if total > 0 else 0
            if calc_ratio > max_ratio[0]:
                max_ratio[0] = calc_ratio
            ratio = min(1.0, max_ratio[0])

            if completed > max_completed[0]:
                max_completed[0] = completed
            comp_show = min(total, max_completed[0]) if total > 0 else max_completed[0]

            pbar_download.value = ratio
            lbl_dl_percent.value = f"{ratio * 100:.0f}%"
            lbl_dl_status.value = f"{comp_show}/{total} parça" if total else "İndiriliyor…"
            lbl_speed.value = (f"{speed_bps / (1024 * 1024):.2f} MB/s"
                               if speed_bps > 0 else "—")
            lbl_size.value = f"{total_bytes / (1024 * 1024):.1f} MB"

            elapsed = max(0.1, now - dl_start_time)
            if ratio >= 1.0:
                current_eta_str[0] = "00:00"
            elif ratio > 0.005:
                current_eta_str[0] = format_seconds((elapsed / ratio) * (1.0 - ratio))
            lbl_eta.value = current_eta_str[0]

            controller.update_live_progress(comp_show, total, speed_bps, ratio,
                                            current_eta_str[0])
            try:
                page.update()
            except Exception:
                try:
                    pbar_download.update()
                    lbl_dl_percent.update()
                    lbl_dl_status.update()
                    lbl_speed.update()
                    lbl_size.update()
                    lbl_eta.update()
                except Exception:
                    logger.debug("[views.film] ilerleme cizilemedi", exc_info=True)

        def run_dl():
            data = resolved_data
            raw_title = data.get("title", "film") or "film"
            clean_title = re.sub(r'[\\/*?:"<>|]', '_', raw_title).strip(". ")[:80]
            if not clean_title:
                clean_title = f"film_{int(time.time())}"
            out_path = os.path.join(controller.download_dir, f"{clean_title}.mp4")
            try:
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
            except Exception:
                logger.debug("[views.film] cikti klasoru olusturulamadi", exc_info=True)
            threads = int(slider_threads.value)

            try:
                segments = data.get("video_segments")
                if not segments and data.get("audio_tracks"):
                    segments = data["audio_tracks"][0].get("segments")

                total_segments = data.get("total_segments") or (
                    len(segments) if segments else 0)
                video_url_clean = data.get("video_url", "").lower().split("?")[0]
                is_direct = data.get("direct_file") or (
                    not any(ext in video_url_clean
                            for ext in [".m3u8", ".mpd", "seg-", "fragment"])
                    and video_url_clean.endswith(
                        (".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi"))
                )

                if is_direct:
                    success, res = controller.engine.download_direct_file(
                        url=data["video_url"],
                        output_filepath=out_path,
                        thread_count=threads,
                        custom_headers=data.get("video_headers"),
                        progress_callback=on_prog,
                        log_callback=log_msg,
                    )
                elif data.get("audio_tracks"):
                    success, res = controller.engine.run_multi_audio_download(
                        video_url=data["video_url"],
                        audio_tracks=_selected_audio_tracks(),
                        output_filepath=out_path,
                        video_headers=data.get("video_headers", {}),
                        total_segments=total_segments,
                        thread_count=threads,
                        progress_callback=on_prog,
                        log_callback=log_msg,
                        video_segments=segments,
                        video_durations=data.get("video_durations"),
                        subtitles=data.get("subtitles"),
                        keep_external_srt=True,
                        recovery_url=data.get("raw_url"),
                    )
                else:
                    success, res = controller.engine.run_download(
                        sample_url=data["video_url"],
                        output_filepath=out_path,
                        thread_count=threads,
                        total_segments=total_segments,
                        custom_headers=data.get("video_headers", {}),
                        segment_urls=segments,
                        progress_callback=on_prog,
                        log_callback=log_msg,
                        subtitles=data.get("subtitles"),
                        keep_external_srt=True,
                        recovery_url=data.get("raw_url"),
                    )

                timer_active[0] = False
                controller.finish_download_session(
                    success=success, filename=os.path.basename(out_path))

                if success:
                    pbar_download.value = 1.0
                    lbl_dl_percent.value = "100%"
                    lbl_dl_title.value = "Tamamlandı"
                    lbl_dl_status.value = os.path.basename(res)
                    current_eta_str[0] = "00:00"
                    lbl_eta.value = "00:00"
                    lbl_elapsed.value = format_seconds(
                        controller.get_elapsed_seconds())
                    last_downloaded_file[0] = res
                    btn_play_finished.visible = True
                    btn_back_to_card.visible = True
                    try:
                        from mobile_engine import scan_media_file
                        scan_media_file(res)
                    except Exception:
                        logger.debug("[views.film] galeri taramasi basarisiz",
                                     exc_info=True)
                    log_msg(f"İndirme tamamlandı: {os.path.basename(res)}")
                    W.snack(page, f"İndirme tamamlandı: {os.path.basename(res)}",
                            T.SUCCESS_FILL)
                    refresh_recent()
                else:
                    _report_failure(res)
            except Exception as error:
                timer_active[0] = False
                controller.finish_download_session(
                    success=False, filename=os.path.basename(out_path))
                _report_failure(error)
            page.update()

        threading.Thread(target=run_dl, daemon=True).start()

    def _report_failure(reason):
        """İptal ile gerçek hatayı ayırır ve kullanıcıya anlaşılır dille söyler."""
        text = str(reason).lower()
        cancelled = (controller.engine.cancel_event.is_set()
                     or "iptal" in text or "cancel" in text)
        btn_play_finished.visible = False
        btn_back_to_card.visible = True
        if cancelled:
            lbl_dl_title.value = "İndirme iptal edildi"
            lbl_dl_status.value = ""
            lbl_speed.value = "—"
            log_msg("İndirme kullanıcı tarafından iptal edildi.")
            W.snack(page, "İndirme iptal edildi.")
        else:
            friendly = translate_user_friendly_error(str(reason))
            lbl_dl_title.value = "İndirme başarısız"
            lbl_dl_status.value = W.elide(friendly, 60)
            log_msg(friendly)
            W.snack(page, friendly, T.DANGER_FILL)

    def cancel_download():
        timer_active[0] = False
        controller.cancel_current_download(cleanup=True)
        pbar_download.value = 0.0
        lbl_dl_percent.value = "0%"
        lbl_dl_title.value = "İndirme iptal edildi"
        lbl_dl_status.value = ""
        lbl_speed.value = "—"
        lbl_size.value = "—"
        lbl_eta.value = "--:--"
        btn_play_finished.visible = False
        btn_back_to_card.visible = False
        W.snack(page, "İndirme iptal edildi.")
        set_state("cozumlendi" if resolved_data else "bos")

    def set_url(url, auto_resolve=False):
        """Akıllı Yönlendirici'nin devrettiği linki yerleştirir.

        Anahtar sözcük adı `main.switch_to_tab` ile birebir aynıdır; farklı
        olduğu sürece her devir `TypeError` ile düşüyordu.
        """
        txt_url.value = url or ""
        set_state("bos")
        try:
            page.update()
        except Exception:
            logger.debug("[views.film] set_url cizilemedi", exc_info=True)
        if auto_resolve and url:
            threading.Thread(target=start_resolve_threaded, daemon=True).start()

    if auto_resolve and initial_url:
        threading.Thread(target=start_resolve_threaded, daemon=True).start()

    refresh_recent()

    container = W.screen([
        W.page_title("Film & Web", ft.Icons.LOCAL_MOVIES_ROUNDED),
        state_idle,
        state_resolved,
        state_downloading,
    ])
    container.set_url = set_url
    container.refresh_recent = refresh_recent
    return container
