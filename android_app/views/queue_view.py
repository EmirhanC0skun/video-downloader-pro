# -*- coding: utf-8 -*-
"""Kuyruk — dizi ve toplu indirme ekranı.

Masaüstündeki `ui/views/queue.py` ile aynı yaşam döngüsünü sunar: tüm
bölümleri tara, aralık tara, kuyruğu başlat/duraklat, tek tek iptal et,
yeniden sıraya al, kuyruktan çıkar.
"""

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

logger = get_logger("views.queue")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W


def status_color(status_text: str) -> str:
    """Kuyruk durumu metnini anlamsal renge eşler."""
    if not status_text:
        return T.TEXT_MUTED
    text = status_text.lower()
    if "tamamlandı" in text:
        return T.SUCCESS
    if "duraklat" in text:
        return T.WARNING
    if "indiriliyor" in text:
        return T.PRIMARY_LIGHT
    if "iptal" in text or "hata" in text:
        return T.DANGER
    return T.TEXT_MUTED


def build_queue_view(page: ft.Page, controller):
    """Kuyruk ekranını kurar ve döndürür."""
    item_widgets = {}

    txt_series_url = W.text_field(
        "Dizi sayfa linki",
        hint="https://… dizi sayfası veya bölüm şablonu",
        icon=ft.Icons.AUTO_AWESOME_MOTION_ROUNDED,
        expand=True,
    )
    txt_start_ep = W.text_field("İlk bölüm", value="1", width=110,
                                keyboard_type=ft.KeyboardType.NUMBER)
    txt_end_ep = W.text_field("Son bölüm", value="10", width=110,
                              keyboard_type=ft.KeyboardType.NUMBER)

    queue_list = ft.Column(spacing=T.GAP_TOUCH, tight=True)
    lbl_queue_summary = W.label("", size=T.SIZE_SM, weight=T.W_SEMI,
                                color=T.TEXT_MUTED)

    btn_scan_all = W.primary_button("Tüm bölümleri tara",
                                    lambda e: scan_and_add_all_episodes(),
                                    icon=ft.Icons.AUTO_AWESOME_ROUNDED, expand=True)
    btn_scan_range = W.ghost_button("Aralık", lambda e: scan_range_episodes(),
                                    icon=ft.Icons.FILTER_LIST_ROUNDED,
                                    height=T.H_BUTTON_SM)
    btn_start_queue = W.success_button("Kuyruğu başlat",
                                       lambda e: start_batch_download(),
                                       icon=ft.Icons.PLAY_ARROW_ROUNDED, expand=2)
    btn_pause_queue = W.warning_button("Duraklat", lambda e: toggle_pause_download(),
                                       icon=ft.Icons.PAUSE_ROUNDED, expand=1)
    btn_pause_queue.disabled = True

    def _set_button_face(button, icon, text, color):
        """Butonun ikon + metnini yerinde değiştirir (yeniden kurmadan)."""
        button.content = ft.Row(
            [ft.Icon(icon, size=18, color=color),
             W.label(text, size=T.SIZE_BASE, weight=T.W_BOLD, color=color)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=8, tight=True,
        )

    def paint_controls():
        """Başlat / Duraklat düğmelerini kuyruk durumuna göre senkronlar."""
        if controller.is_queue_running and not controller.is_queue_paused:
            btn_start_queue.disabled = True
            _set_button_face(btn_start_queue, ft.Icons.HOURGLASS_TOP_ROUNDED,
                             "Kuyruk çalışıyor", T.SUCCESS_INK)
            btn_pause_queue.disabled = False
            _set_button_face(btn_pause_queue, ft.Icons.PAUSE_ROUNDED, "Duraklat",
                             T.WARNING)
        elif controller.is_queue_paused:
            btn_start_queue.disabled = False
            _set_button_face(btn_start_queue, ft.Icons.PLAY_ARROW_ROUNDED,
                             "Kuyruğu başlat", T.SUCCESS_INK)
            btn_pause_queue.disabled = False
            _set_button_face(btn_pause_queue, ft.Icons.PLAY_ARROW_ROUNDED,
                             "Devam et", T.SUCCESS)
        else:
            btn_start_queue.disabled = False
            _set_button_face(btn_start_queue, ft.Icons.PLAY_ARROW_ROUNDED,
                             "Kuyruğu başlat", T.SUCCESS_INK)
            btn_pause_queue.disabled = True
            _set_button_face(btn_pause_queue, ft.Icons.PAUSE_ROUNDED, "Duraklat",
                             T.TEXT_DIM)

    def build_item_card(item):
        """Tek bir kuyruk satırını kurar ve canlı alanlarını kaydeder."""
        item_id = item["id"]
        status = item["status"]
        color = status_color(status)

        lbl_status = W.label(status, size=T.SIZE_XS, weight=T.W_BOLD, color=color)
        pbar = W.progress_bar(item.get("progress", 0.0), height=6)
        lbl_speed = W.label(item.get("speed", "") or "", size=T.SIZE_XS,
                            weight=T.W_BOLD, color=T.WARNING, mono=True)
        lbl_size = W.label(item.get("size", "") or "", size=T.SIZE_XS,
                           color=T.TEXT_MUTED, mono=True)

        item_widgets[item_id] = {
            "pbar": pbar, "status": lbl_status, "speed": lbl_speed, "size": lbl_size,
        }

        return W.card(
            ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.MOVIE_ROUNDED, size=16,
                                                color=T.PRIMARY_LIGHT),
                                bgcolor=T.ICON_FILL_VIDEO,
                                border_radius=8,
                                width=30, height=30,
                                alignment=ft.Alignment(0, 0),
                            ),
                            W.label(item["title"], size=T.SIZE_BASE, weight=T.W_BOLD,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True),
                            ft.Container(
                                content=lbl_status,
                                bgcolor=T.BG_ELEVATED,
                                border_radius=6,
                                padding=W.padding(8, 4),
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    pbar,
                    ft.Row(
                        [
                            lbl_size,
                            ft.Container(expand=True),
                            lbl_speed,
                            W.icon_button(ft.Icons.STOP_CIRCLE_OUTLINED,
                                          lambda e, i=item_id: cancel_single_item(i),
                                          color=T.DANGER, tooltip="İptal et", size=18),
                            W.icon_button(ft.Icons.REFRESH_ROUNDED,
                                          lambda e, i=item_id: retry_single_item(i),
                                          color=T.PRIMARY_LIGHT,
                                          tooltip="Yeniden sıraya al", size=18),
                            W.icon_button(ft.Icons.DELETE_OUTLINE_ROUNDED,
                                          lambda e, i=item_id: remove_item(i),
                                          color=T.TEXT_MUTED,
                                          tooltip="Kuyruktan çıkar", size=18),
                        ],
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
            ),
            radius=T.R_TILE,
            pad=W.padding(12, 10),
        )

    def refresh_queue_ui(target_item=None):
        """Tek satırı veya tüm listeyi tazeler.

        `target_item` verildiğinde yalnızca o satırın canlı alanları yazılır —
        indirme sırasında saniyede birkaç kez çağrıldığı için tüm listeyi
        yeniden kurmak gereksiz çizim yükü olurdu.
        """
        paint_controls()

        if target_item and target_item["id"] in item_widgets:
            widgets = item_widgets[target_item["id"]]
            status = target_item["status"]
            widgets["pbar"].value = target_item.get("progress", 0.0)
            widgets["speed"].value = target_item.get("speed", "") or ""
            widgets["size"].value = target_item.get("size", "") or ""
            widgets["status"].value = status
            widgets["status"].color = status_color(status)
            try:
                widgets["pbar"].update()
                widgets["speed"].update()
                widgets["size"].update()
                widgets["status"].update()
                btn_start_queue.update()
                btn_pause_queue.update()
            except Exception:
                logger.debug("[views.queue] satir cizilemedi", exc_info=True)
            return

        queue_list.controls.clear()
        item_widgets.clear()

        items = controller.queue_items
        if not items:
            lbl_queue_summary.value = ""
            queue_list.controls.append(
                W.empty_state(
                    ft.Icons.PLAYLIST_REMOVE_ROUNDED,
                    "Kuyrukta henüz indirme yok.",
                    "Dizi linkini yapıştırıp 'Tüm bölümleri tara' düğmesine dokunun.",
                )
            )
        else:
            done = sum(1 for i in items
                       if "tamamlandı" in str(i.get("status", "")).lower())
            lbl_queue_summary.value = f"{len(items)} bölüm · {done} tamamlandı"
            for item in items:
                queue_list.controls.append(build_item_card(item))

        try:
            page.update()
        except Exception:
            logger.debug("[views.queue] liste cizilemedi", exc_info=True)

    # -- Oge eylemleri --------------------------------------------------------
    def remove_item(item_id):
        controller.remove_queue_item(item_id)
        refresh_queue_ui()

    def cancel_single_item(item_id):
        controller.cancel_queue_item(item_id)
        refresh_queue_ui()

    def retry_single_item(item_id):
        controller.retry_queue_item(item_id)
        refresh_queue_ui()

    def clear_all():
        if not controller.queue_items:
            return
        W.confirm_dialog(
            page, "Kuyruğu temizle",
            f"{len(controller.queue_items)} bölüm kuyruktan çıkarılacak. "
            "İndirilmiş dosyalar silinmez.",
            on_confirm=lambda: (controller.clear_queue(), refresh_queue_ui()),
            confirm_text="Temizle",
        )

    # -- Tarama ---------------------------------------------------------------
    def scan_and_add_all_episodes():
        url = (txt_series_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir dizi linki girin.", T.DANGER_FILL)
            return

        btn_scan_all.disabled = True
        W.snack(page, "Dizi sayfası taranıyor…")
        page.update()

        def scan_task():
            try:
                episodes = controller.scan_series_episodes(url, all_episodes=True)
                if not episodes:
                    W.snack(page, "Bölüm bulunamadı; aralık ile taramayı deneyin.",
                            T.WARNING_FILL)
                else:
                    for episode in episodes:
                        controller.add_queue_item(title=episode["title"],
                                                  url=episode["url"],
                                                  media_type="film")
                    W.snack(page, f"{len(episodes)} bölüm sıraya eklendi.",
                            T.SUCCESS_FILL)
            except Exception as error:
                W.snack(page, f"Tarama hatası: {error}", T.DANGER_FILL)
            finally:
                btn_scan_all.disabled = False
                refresh_queue_ui()

        threading.Thread(target=scan_task, daemon=True).start()

    def scan_range_episodes():
        url = (txt_series_url.value or "").strip()
        if not url:
            W.snack(page, "Lütfen bir dizi linki girin.", T.DANGER_FILL)
            return
        try:
            start_ep = int((txt_start_ep.value or "1").strip())
            end_ep = int((txt_end_ep.value or "10").strip())
        except ValueError:
            W.snack(page, "Bölüm aralığı sayı olmalı.", T.DANGER_FILL)
            return

        episodes = controller.scan_series_episodes(url, start_ep, end_ep,
                                                   all_episodes=False)
        for episode in episodes:
            controller.add_queue_item(title=episode["title"], url=episode["url"],
                                      media_type="film")
        W.snack(page, f"{len(episodes)} bölüm kuyruğa eklendi.", T.SUCCESS_FILL)
        refresh_queue_ui()

    # -- Kuyruk yasam dongusu -------------------------------------------------
    def start_batch_download():
        if not controller.queue_items:
            W.snack(page, "Kuyruk boş.", T.WARNING_FILL)
            return
        controller.start_queue(status_update_cb=refresh_queue_ui)
        refresh_queue_ui()

    def toggle_pause_download():
        state = controller.toggle_queue_pause(status_update_cb=refresh_queue_ui)
        W.snack(page, "Kuyruk duraklatıldı." if state == "PAUSED"
                else "Kuyruk sürdürülüyor.")
        refresh_queue_ui()

    refresh_queue_ui()

    container = W.screen([
        W.page_title(
            "Kuyruk", ft.Icons.PLAYLIST_PLAY_ROUNDED,
            W.icon_button(ft.Icons.DELETE_SWEEP_ROUNDED, lambda e: clear_all(),
                          color=T.TEXT_MUTED, tooltip="Kuyruğu temizle"),
        ),
        W.card(
            ft.Column(
                spacing=12,
                tight=True,
                controls=[
                    W.label("Otomatik dizi & sezon çözücü", size=T.SIZE_SM,
                            weight=T.W_BOLD, color=T.TEXT_MUTED),
                    txt_series_url,
                    W.full_width(btn_scan_all),
                    ft.Row([txt_start_ep, txt_end_ep, btn_scan_range],
                           spacing=T.GAP_TOUCH,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
            )
        ),
        ft.Row([btn_start_queue, btn_pause_queue], spacing=T.GAP_TOUCH),
        ft.Row([
            W.section_label("İndirme listesi"),
            ft.Container(expand=True),
            lbl_queue_summary,
        ]),
        queue_list,
    ])
    container.refresh_queue = refresh_queue_ui
    return container
