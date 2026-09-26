# -*- coding: utf-8 -*-
"""Sosyal Medya — YouTube, Instagram, TikTok, X indirme ekranı.

Film ekranıyla aynı üç durumlu akışı paylaşır (`bos` → `cozumlendi` →
`indiriliyor`) ve aynı bileşen kitaplığını kullanır; iki sekme arasında geçen
kullanıcı aynı yerleşimi bulur.
"""

import os
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

logger = get_logger("views.social")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W

from mobile_engine import translate_user_friendly_error

# Film / dizi alan adlari — Akilli Yonlendirici bunlari Film sekmesine devreder.
FILM_HOSTS = ("dizipal", "fullhdfilm", "filmmodu", "dizilla", "roketdizi",
              "jetfilm", "dizibox", "sezonlukdizi", "hdfilm", ".m3u8")

# Varsayilan format merdiveni. Cozumleme gercek formatlari getirdiginde bunun
# yerini alir; getiremezse kullanici yine de secim yapabilir.
DEFAULT_FORMATS = [
    ("best", "En yüksek kalite"),
    ("1080p", "1080p Full HD"),
    ("720p", "720p HD"),
    ("480p", "480p SD"),
    ("360p", "360p düşük"),
    ("mp3", "MP3 320 kbps ses"),
    ("m4a", "M4A / AAC ses"),
]


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


def format_key(quality_text: str) -> str:
    """`1080p (mp4)` gibi bir etiketi motorun beklediği format anahtarına çevirir."""
    text = str(quality_text).lower()
    if "mp3" in text:
        return "mp3"
    if "m4a" in text or "aac" in text:
        return "m4a"
    for needle, key in (("2160", "2160p"), ("4k", "2160p"), ("1440", "1440p"),
                        ("2k", "1440p"), ("1080", "1080p"), ("720", "720p"),
                        ("480", "480p"), ("360", "360p")):
        if needle in text:
            return key
    return "best"


def build_social_view(page: ft.Page, controller, initial_url=None, auto_resolve=False):
    """Sosyal medya ekranını kurar ve döndürür."""
    timer_active = [False]
    current_eta_str = ["--:--"]
    last_downloaded_file = [None]
    resolved_info = {}
    # Pill etiketi -> motor format anahtari.
    format_keys = {}

    # =====================================================================
    # Durum 1 — bos
    # =====================================================================
    txt_url = W.text_field(
        "Sosyal medya veya YouTube linki",
        hint="YouTube, Instagram, TikTok, Shorts veya X bağlantısı…",
        value=initial_url or "",
        icon=ft.Icons.LINK_ROUNDED,
        expand=True,
    )

    txt_cookie_file = W.text_field(
        "Çerez dosyası (cookies.txt)",
        hint="Instagram veya kilitli videolar için — isteğe bağlı",
        expand=True,
    )

    cookies_panel = W.Collapsible(
        "Gelişmiş", "çerez dosyası",
        body_controls=[
            txt_cookie_file,
            W.label(
                "Yalnızca giriş gerektiren kilitli videolar için gerekir.",
                size=T.SIZE_XS, color=T.TEXT_DIM),
        ],
    )

    def routed_to_film(url: str) -> bool:
        """Link bu ekrana ait değilse Film sekmesine devreder."""
        if not any(host in url.lower() for host in FILM_HOSTS):
            return False
        W.snack(page, "Film/dizi linki algılandı, Film sekmesine aktarılıyor.")
        controller.switch_tab(0, url=url, auto_resolve=True)
        return True

    def paste_clipboard():
        try:
            val = page.get_clipboard()
        except Exception:
            logger.debug("[views.social] pano okunamadi", exc_info=True)
            return
        if not val:
            return
        val_clean = val.strip()
        txt_url.value = val_clean
        page.update()
        routed_to_film(val_clean)

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
                        W.step_hint(["Linki yapıştır", "Çözümle", "Formatı seç"]),
                    ],
                )
            ),
            cookies_panel,
        ],
    )

    # =====================================================================
    # Durum 2 — cozumlendi
    # =====================================================================
    lbl_resolved_url = W.label("", size=T.SIZE_SM, weight=T.W_SEMI,
                               color=T.TEXT_MUTED, max_lines=1,
                               overflow=ft.TextOverflow.ELLIPSIS, expand=True)
    lbl_resolved_title = W.label("Medya", size=T.SIZE_TITLE, weight=T.W_EXTRA,
                                 max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
    resolved_meta = ft.Row(spacing=6, wrap=True, run_spacing=6)
    pills_format = W.PillGroup(empty_text="Format bulunamadı")

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
                                    content=ft.Icon(
                                        ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED,
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
                        W.section_label("Format ve kalite"),
                        pills_format,
                        W.divider(),
                        ft.Row(
                            [
                                W.success_button("İndir",
                                                 lambda e: start_social_download(),
                                                 icon=ft.Icons.DOWNLOAD_ROUNDED,
                                                 expand=2),
                                W.ghost_button("Sıraya ekle",
                                               lambda e: add_to_queue_click(),
                                               icon=ft.Icons.PLAYLIST_ADD_ROUNDED,
                                               expand=1),
                            ],
                            spacing=T.GAP_TOUCH,
                        ),
                    ],
                )
            ),
        ],
    )

    # =====================================================================
    # Durum 3 — indiriliyor
    # =====================================================================
    lbl_dl_title = W.label("İndiriliyor", size=T.SIZE_LG, weight=T.W_EXTRA,
                           max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    lbl_dl_status = W.label("Hazırlanıyor…", size=T.SIZE_SM, weight=T.W_SEMI,
                            color=T.TEXT_MUTED)
    lbl_dl_percent = W.label("0%", size=T.SIZE_HERO, weight=T.W_SEMI, mono=True)
    pbar_social = W.progress_bar(0.0, height=8)

    tile_speed, lbl_speed = W.stat_tile("Hız", "0.00 MB/s", T.WARNING)
    tile_eta, lbl_eta = W.stat_tile("Kalan", "--:--")
    tile_elapsed, lbl_elapsed = W.stat_tile("Geçen", "00:00")
    tile_size, lbl_size = W.stat_tile("Boyut", "0.0 MB")

    btn_pause = W.warning_button("Duraklat", lambda e: toggle_pause(),
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
        lambda e: set_state("cozumlendi" if resolved_info else "bos"),
        icon=ft.Icons.ARROW_BACK_ROUNDED,
        height=T.H_BUTTON_SM,
    )
    btn_back_to_card.visible = False

    txt_logs = W.label(
        "Hazır. YouTube veya sosyal medya linkini yapıştırıp 'Çözümle' düğmesine "
        "dokunun.", size=T.SIZE_SM, color=T.TEXT_MUTED)
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
                        pbar_social,
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

    def set_state(name: str) -> None:
        for key, frame in states.items():
            frame.visible = key == name
        try:
            page.update()
        except Exception:
            logger.debug("[views.social] durum gecisi cizilemedi", exc_info=True)

    for key, frame in states.items():
        frame.visible = key == "bos"

    # =====================================================================
    # Davranis
    # =====================================================================
    def set_log(msg):
        txt_logs.value = str(msg)
        try:
            txt_logs.update()
        except Exception:
            logger.debug("[views.social] gunluk yazilamadi", exc_info=True)

    def _set_button_face(button, icon, text, color):
        button.content = ft.Row(
            [ft.Icon(icon, size=18, color=color),
             W.label(text, size=T.SIZE_BASE, weight=T.W_BOLD, color=color)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=8, tight=True,
        )

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
                        logger.debug("[views.social] sayac cizilemedi", exc_info=True)
                time.sleep(1)

        threading.Thread(target=tick_loop, daemon=True).start()

    def toggle_pause():
        if controller.is_downloading and not controller.is_paused:
            controller.pause_download()
            _set_button_face(btn_pause, ft.Icons.PLAY_ARROW_ROUNDED, "Devam et",
                             T.SUCCESS)
            lbl_dl_status.value = "Duraklatıldı"
        elif controller.is_paused:
            controller.resume_download()
            _set_button_face(btn_pause, ft.Icons.PAUSE_ROUNDED, "Duraklat", T.WARNING)
            lbl_dl_status.value = "İndiriliyor…"
        page.update()

    def add_to_queue_click():
        url = (txt_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir video linki girin.", T.DANGER_FILL)
            return
        title = resolved_info.get("title") or "Sosyal medya videosu"
        controller.add_queue_item(title, url, media_type="social")
        W.snack(page, f"'{W.elide(title, 30)}' kuyruğa eklendi.", T.SUCCESS_FILL)

    def _selected_format() -> str:
        """Seçili pill'i motorun beklediği format anahtarına çevirir."""
        chosen = pills_format.get()
        return format_keys.get(chosen) or format_key(chosen)

    def start_resolve_threaded():
        url = (txt_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir video linki girin.", T.DANGER_FILL)
            return
        if routed_to_film(url):
            return

        btn_resolve.disabled = True
        prg_resolve.visible = True
        btn_play_finished.visible = False
        set_log("Medya sunucusu sorgulanıyor ve formatlar analiz ediliyor…")
        page.update()

        def resolve_task():
            try:
                cookies = (txt_cookie_file.value or "").strip() or None
                info = controller.extract_social_info(url, cookies_file=cookies,
                                                      log_cb=set_log)
            except Exception as error:
                btn_resolve.disabled = False
                prg_resolve.visible = False
                friendly = translate_user_friendly_error(str(error))
                set_log(friendly)
                W.snack(page, friendly, T.DANGER_FILL)
                page.update()
                return

            btn_resolve.disabled = False
            prg_resolve.visible = False

            format_keys.clear()
            if info:
                resolved_info.clear()
                resolved_info.update(info)
                title = info.get("title", "Sosyal medya videosu")
                duration = info.get("duration", 0)
                qualities = info.get("qualities", [])

                lbl_resolved_title.value = title
                lbl_resolved_url.value = W.elide(url, 60)
                resolved_meta.controls = [
                    W.meta_chip(format_seconds(duration) if duration else "süre bilinmiyor"),
                    W.meta_chip(f"{len(qualities)} format"),
                ]
                labels = [str(q) for q in qualities]
                for quality in labels:
                    format_keys[quality] = format_key(quality)
                if not labels:
                    labels = [text for _, text in DEFAULT_FORMATS]
                    format_keys.update({text: key for key, text in DEFAULT_FORMATS})
                pills_format.set_values(labels)
                set_log(f"Çözümlendi: {title}")
            else:
                # Cozumleme basarisiz olsa da indirme genel modda calisabilir;
                # kullaniciyi cikmaza sokmak yerine varsayilan formatlari sun.
                resolved_info.clear()
                lbl_resolved_title.value = "Format listesi alınamadı"
                lbl_resolved_url.value = W.elide(url, 60)
                resolved_meta.controls = [W.meta_chip("genel indirme modu")]
                format_keys.update({text: key for key, text in DEFAULT_FORMATS})
                pills_format.set_values([text for _, text in DEFAULT_FORMATS])
                set_log("Formatlar ayrıştırılamadı, genel indirme modu kullanılacak.")

            set_state("cozumlendi")

        threading.Thread(target=resolve_task, daemon=True).start()

    def start_social_download():
        url = (txt_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir video linki girin.", T.DANGER_FILL)
            return
        if routed_to_film(url):
            return

        set_state("indiriliyor")
        lbl_dl_title.value = W.elide(resolved_info.get("title", "Sosyal medya"), 40)
        lbl_dl_status.value = "Başlatılıyor…"
        lbl_dl_percent.value = "0%"
        pbar_social.value = 0.0
        lbl_speed.value = "0.00 MB/s"
        lbl_size.value = "0.0 MB"
        lbl_elapsed.value = "00:00"
        lbl_eta.value = "--:--"
        current_eta_str[0] = "--:--"
        btn_play_finished.visible = False
        btn_back_to_card.visible = False
        _set_button_face(btn_pause, ft.Icons.PAUSE_ROUNDED, "Duraklat", T.WARNING)

        controller.start_download_session(
            resolved_info.get("title") or "Sosyal Medya")
        start_timer_tick()
        set_log("Video taranıyor ve indirme başlatılıyor…")
        page.update()

        last_update_time = [0.0]
        max_ratio = [0.0]
        max_down = [0]
        dl_start_time = time.time()

        def on_prog(down, tot, spd, ratio):
            now = time.time()
            is_final = ratio >= 1.0 or (tot > 0 and down >= tot)
            if not is_final and (now - last_update_time[0] < 0.06):
                return
            last_update_time[0] = now

            if ratio > max_ratio[0]:
                max_ratio[0] = ratio
            safe_ratio = min(1.0, max_ratio[0])

            if down > max_down[0]:
                max_down[0] = down
            down_show = min(tot, max_down[0]) if tot > 0 else max_down[0]

            pbar_social.value = safe_ratio
            lbl_dl_percent.value = f"{safe_ratio * 100:.0f}%"
            lbl_dl_status.value = "İndiriliyor…"
            lbl_speed.value = f"{spd / (1024 * 1024):.2f} MB/s" if spd > 0 else "—"
            lbl_size.value = (
                f"{down_show / (1024 * 1024):.1f} / {tot / (1024 * 1024):.1f} MB"
                if tot > 0 else f"{down_show / (1024 * 1024):.1f} MB")

            elapsed = max(0.1, now - dl_start_time)
            if safe_ratio >= 1.0:
                current_eta_str[0] = "00:00"
            elif safe_ratio > 0.005:
                current_eta_str[0] = format_seconds(
                    (elapsed / safe_ratio) * (1.0 - safe_ratio))
            lbl_eta.value = current_eta_str[0]

            controller.update_live_progress(down_show, tot, spd, safe_ratio,
                                            current_eta_str[0])
            try:
                page.update()
            except Exception:
                try:
                    pbar_social.update()
                    lbl_dl_percent.update()
                    lbl_dl_status.update()
                    lbl_speed.update()
                    lbl_size.update()
                    lbl_eta.update()
                except Exception:
                    logger.debug("[views.social] ilerleme cizilemedi", exc_info=True)

        def run_social():
            try:
                cookies = (txt_cookie_file.value or "").strip() or None
                success, res = controller.download_social_media(
                    media_url=url,
                    format_choice=_selected_format(),
                    cookies_file=cookies,
                    progress_cb=on_prog,
                    log_cb=set_log,
                )
                timer_active[0] = False
                controller.finish_download_session(
                    success=success,
                    filename=os.path.basename(res) if success else "")
                if success:
                    pbar_social.value = 1.0
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
                        logger.debug("[views.social] galeri taramasi basarisiz",
                                     exc_info=True)
                    W.snack(page, f"İndirme tamamlandı: {os.path.basename(res)}",
                            T.SUCCESS_FILL)
                else:
                    _report_failure(res)
            except Exception as error:
                timer_active[0] = False
                controller.finish_download_session(success=False)
                _report_failure(error)
            page.update()

        threading.Thread(target=run_social, daemon=True).start()

    def _report_failure(reason):
        text = str(reason).lower()
        cancelled = (controller.social_engine.cancel_event.is_set()
                     or "iptal" in text or "cancel" in text)
        btn_play_finished.visible = False
        btn_back_to_card.visible = True
        if cancelled:
            lbl_dl_title.value = "İndirme iptal edildi"
            lbl_dl_status.value = ""
            lbl_speed.value = "—"
            set_log("İndirme kullanıcı tarafından iptal edildi.")
            W.snack(page, "İndirme iptal edildi.")
        else:
            friendly = translate_user_friendly_error(str(reason))
            lbl_dl_title.value = "İndirme başarısız"
            lbl_dl_status.value = W.elide(friendly, 60)
            set_log(friendly)
            W.snack(page, friendly, T.DANGER_FILL)

    def cancel_download():
        timer_active[0] = False
        controller.cancel_current_download(cleanup=True)
        pbar_social.value = 0.0
        lbl_dl_percent.value = "0%"
        lbl_dl_title.value = "İndirme iptal edildi"
        lbl_dl_status.value = ""
        lbl_speed.value = "—"
        lbl_size.value = "—"
        lbl_eta.value = "--:--"
        btn_play_finished.visible = False
        btn_back_to_card.visible = False
        W.snack(page, "İndirme iptal edildi.")
        set_state("cozumlendi" if resolved_info else "bos")

    def set_url(url, auto_resolve=False):
        """Akıllı Yönlendirici'nin devrettiği linki yerleştirir."""
        txt_url.value = url or ""
        set_state("bos")
        try:
            page.update()
        except Exception:
            logger.debug("[views.social] set_url cizilemedi", exc_info=True)
        if auto_resolve and url:
            threading.Thread(target=start_resolve_threaded, daemon=True).start()

    if auto_resolve and initial_url:
        threading.Thread(target=start_resolve_threaded, daemon=True).start()

    container = W.screen([
        W.page_title("Sosyal Medya", ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED),
        state_idle,
        state_resolved,
        state_downloading,
    ])
    container.set_url = set_url
    return container
