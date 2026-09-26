# -*- coding: utf-8 -*-
"""Dönüştürücü — yerel FFmpeg ile format dönüştürme ve ses ayıklama.

Masaüstündeki `ui/views/converter.py` karşılığıdır: kaynak dosya seçilir,
hedef format bir pill kümesinden işaretlenir, dönüştürme yerel motorla yapılır.
"""

import os
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

logger = get_logger("views.converter")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W

# Pill etiketi -> FFmpeg hedef formati.
FORMATS = [
    ("MP3 320 kbps ses", "mp3"),
    ("MP4 (H.264 + AAC)", "mp4"),
    ("MKV kapsayıcı", "mkv"),
    ("WAV sıkıştırmasız", "wav"),
]


def build_converter_view(page: ft.Page, controller):
    """Dönüştürücü ekranını kurar ve döndürür."""
    selected_file = [None]
    last_converted_file = [None]

    lbl_selected = W.label("Henüz dosya seçilmedi", size=T.SIZE_SM,
                           color=T.TEXT_MUTED, max_lines=1,
                           overflow=ft.TextOverflow.ELLIPSIS)
    files_list = ft.Column(spacing=T.GAP_TOUCH, tight=True)

    pills_format = W.PillGroup([text for text, _ in FORMATS])
    format_keys = {text: key for text, key in FORMATS}

    prg_convert = ft.ProgressRing(visible=False, width=18, height=18,
                                  stroke_width=2, color=T.PURPLE_LIGHT)
    lbl_status = W.label("Hazır. Dönüştürülecek bir dosya seçin.", size=T.SIZE_SM,
                         color=T.TEXT_MUTED)

    btn_convert = W.purple_button("Dönüştür", lambda e: start_convert_threaded(),
                                  icon=ft.Icons.TRANSFORM_ROUNDED,
                                  height=T.H_BUTTON, expand=True)
    btn_convert.disabled = True

    btn_play_converted = W.success_button(
        "Dönüştürüleni aç",
        lambda e: (controller.open_file_externally(last_converted_file[0])
                   if last_converted_file[0] else None),
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        height=T.H_BUTTON_SM,
    )
    btn_play_converted.visible = False

    def select_file(path: str) -> None:
        """Kaynak dosyayı işaretler ve listeyi yeniden boyar."""
        selected_file[0] = path
        lbl_selected.value = os.path.basename(path)
        lbl_status.value = f"Seçildi: {os.path.basename(path)}"
        btn_convert.disabled = False
        btn_play_converted.visible = False
        refresh_files()

    def refresh_files() -> None:
        """İndirilen dosyaları listeler; seçili olan mavi tint alır."""
        files_list.controls.clear()
        try:
            files = controller.get_completed_files()
        except Exception:
            logger.debug("[views.converter] dosya listesi okunamadi", exc_info=True)
            files = []

        if not files:
            files_list.controls.append(
                W.empty_state(
                    ft.Icons.FOLDER_OFF_ROUNDED,
                    "Dönüştürülecek dosya yok.",
                    "Önce Film veya Sosyal sekmesinden bir medya indirin.",
                )
            )
        else:
            for item in files:
                path = item["path"]
                is_selected = path == selected_file[0]
                is_audio = item.get("is_audio")
                files_list.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.AUDIOTRACK_ROUNDED if is_audio
                                        else ft.Icons.MOVIE_ROUNDED,
                                        size=18,
                                        color=T.PURPLE_LIGHT if is_audio
                                        else T.PRIMARY_LIGHT),
                                    bgcolor=T.ICON_FILL_AUDIO if is_audio
                                    else T.ICON_FILL_VIDEO,
                                    border_radius=9,
                                    width=36, height=36,
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Column(
                                    [
                                        W.label(item["name"], size=T.SIZE_BASE,
                                                weight=T.W_BOLD, max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS),
                                        W.label(f"{item['size_mb']} MB · {item['date']}",
                                                size=T.SIZE_XS, color=T.TEXT_MUTED),
                                    ],
                                    spacing=2, tight=True, expand=True,
                                ),
                                ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=20,
                                        color=T.PRIMARY) if is_selected
                                else ft.Container(width=20),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor=T.PRIMARY_FILL_SOFT if is_selected else T.BG_CARD,
                        border=W.border_all(1, T.PRIMARY if is_selected else T.BORDER),
                        border_radius=T.R_TILE,
                        padding=W.padding(10, 8),
                        on_click=lambda e, p=path: select_file(p),
                        ink=True,
                    )
                )
        try:
            page.update()
        except Exception:
            logger.debug("[views.converter] liste cizilemedi", exc_info=True)

    def set_status(msg):
        lbl_status.value = str(msg)
        try:
            lbl_status.update()
        except Exception:
            logger.debug("[views.converter] durum yazilamadi", exc_info=True)

    def start_convert_threaded():
        in_path = selected_file[0]
        if not in_path or not os.path.exists(in_path):
            W.snack(page, "Lütfen geçerli bir dosya seçin.", T.DANGER_FILL)
            return

        btn_convert.disabled = True
        btn_play_converted.visible = False
        prg_convert.visible = True
        set_status("FFmpeg ile dönüştürülüyor…")
        page.update()

        # Pill etiketi -> format anahtari. Eskiden bu secim bir `Dropdown`un
        # `on_change` niteligiyle okunurdu; Flet 0.86'da o alan yok ve secim
        # hicbir zaman islenmiyordu.
        target_format = format_keys.get(pills_format.get(), "mp3")

        def task():
            try:
                success, res = controller.convert_media(
                    in_path, target_format=target_format, log_cb=set_status)
            except Exception as error:
                success, res = False, error

            btn_convert.disabled = False
            prg_convert.visible = False
            if success:
                last_converted_file[0] = res
                btn_play_converted.visible = True
                set_status(f"Dönüştürme tamamlandı: {os.path.basename(res)}")
                W.snack(page, f"Kaydedildi: {os.path.basename(res)}", T.SUCCESS_FILL)
                refresh_files()
            else:
                set_status(f"Hata: {res}")
                W.snack(page, f"Dönüştürme başarısız: {res}", T.DANGER_FILL)
            page.update()

        threading.Thread(target=task, daemon=True).start()

    refresh_files()

    container = W.screen([
        W.page_title(
            "Dönüştürücü", ft.Icons.TRANSFORM_ROUNDED,
            W.icon_button(ft.Icons.REFRESH_ROUNDED, lambda e: refresh_files(),
                          color=T.PRIMARY_LIGHT, tooltip="Listeyi yenile"),
        ),
        W.card(
            ft.Column(
                spacing=14,
                tight=True,
                controls=[
                    W.section_label("Hedef format"),
                    pills_format,
                    W.divider(),
                    ft.Row([
                        ft.Icon(ft.Icons.FILE_OPEN_ROUNDED, size=16, color=T.TEXT_DIM),
                        lbl_selected,
                    ], spacing=8),
                    ft.Row([btn_convert, prg_convert], spacing=T.GAP_TOUCH,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    W.full_width(btn_play_converted),
                    W.tile(lbl_status),
                ],
            )
        ),
        W.section_label("Kaynak dosya"),
        files_list,
        W.card(
            ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE_ROUNDED, size=16,
                                color=T.WARNING),
                        W.label("İpucu", size=T.SIZE_SM, weight=T.W_BOLD),
                    ], spacing=8),
                    W.label("Videodan arka plan sesini ayıklamak için hedef "
                            "formatı MP3 seçin.", size=T.SIZE_SM, color=T.TEXT_MUTED),
                    W.label("Tüm dönüştürmeler cihazınızda yerel FFmpeg motoruyla "
                            "yapılır; dosya hiçbir sunucuya gönderilmez.",
                            size=T.SIZE_SM, color=T.TEXT_MUTED),
                ],
            ),
            radius=T.R_CARD_SM,
        ),
    ])
    container.refresh_files = refresh_files
    return container
