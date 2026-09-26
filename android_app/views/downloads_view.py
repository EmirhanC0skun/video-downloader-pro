# -*- coding: utf-8 -*-
"""İndirilenler — kütüphane ve geçmiş ekranı.

Masaüstündeki `ui/views/library.py` karşılığı: canlı arama, tek dokunuşla
oynatma, tekrar indirme ve depolama yönetimi.
"""

import os
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

logger = get_logger("views.downloads")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W

try:
    from core.history import load_history, clear_history
except ImportError:
    try:
        from history import load_history, clear_history
    except ImportError:
        load_history = lambda: []
        clear_history = lambda: None

# Sosyal medya alan adlari — `Tekrar indir` dogru sekmeye yonlendirir.
SOCIAL_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com",
                "twitter.com", "x.com", "vimeo.com")


def build_downloads_view(page: ft.Page, controller):
    """İndirilenler ekranını kurar ve döndürür."""
    files_list = ft.Column(spacing=T.GAP_TOUCH, tight=True)

    txt_search = W.text_field(hint="Geçmişte ve indirilenlerde ara…",
                              icon=ft.Icons.SEARCH_ROUNDED, expand=True)
    lbl_storage = W.label("Depolama taranıyor…", size=T.SIZE_SM, weight=T.W_SEMI,
                          color=T.TEXT_MUTED)

    def repeat_download(item):
        """Medyayı kaynak sekmesinde yeniden çözümlemeye gönderir."""
        source = item.get("source_url", "")
        if not source:
            W.snack(page, "Bu medyanın kaynak bağlantısı kayıtlı değil.",
                    T.WARNING_FILL)
            return
        is_social = any(host in source.lower() for host in SOCIAL_HOSTS)
        W.snack(page, f"'{W.elide(item.get('title', 'Medya'), 30)}' yeniden "
                      "çözümleniyor.")
        controller.switch_tab(1 if is_social else 0, url=source, auto_resolve=True)

    def delete_file(path):
        """Dosyayı ve yanındaki altyazıyı siler — onay alındıktan sonra."""
        try:
            if os.path.exists(path):
                os.remove(path)
            subtitle = os.path.splitext(path)[0] + ".srt"
            if os.path.exists(subtitle):
                os.remove(subtitle)
            refresh_list()
            W.snack(page, "Dosya silindi.")
        except Exception as error:
            W.snack(page, f"Silme hatası: {error}", T.DANGER_FILL)

    def confirm_delete(item):
        # Silme geri alinamaz ve mobilde yanlis satira dokunmak kolaydir;
        # tek dokunusla dosya yok etmek yerine once onay istenir.
        W.confirm_dialog(
            page, "Dosyayı sil",
            f"'{W.elide(item['title'], 40)}' cihazdan kalıcı olarak silinecek.",
            on_confirm=lambda: delete_file(item["path"]),
        )

    def collect_items(query: str):
        """Diskteki dosyaları geçmiş kayıtlarıyla eşleştirip filtreler."""
        try:
            disk_files = controller.get_completed_files()
        except Exception:
            logger.debug("[views.downloads] disk taranamadi", exc_info=True)
            disk_files = []
        history_by_path = {h.get("file_path", ""): h for h in (load_history() or [])}

        items = []
        for entry in disk_files:
            path = entry["path"]
            record = history_by_path.get(path, {})
            items.append({
                "title": record.get("title") or entry["name"],
                "filename": entry["name"],
                "path": path,
                "size_mb": entry["size_mb"],
                "date": entry["date"],
                "source_url": record.get("source_url", ""),
                "media_type": record.get("media_type", "Medya"),
                "is_audio": entry["is_audio"],
            })

        if query:
            items = [
                item for item in items
                if query in item["title"].lower()
                or query in item["filename"].lower()
                or query in item.get("source_url", "").lower()
            ]
        return items

    def refresh_list():
        query = (txt_search.value or "").strip().lower()
        files_list.controls.clear()
        items = collect_items(query)

        total_mb = sum(item["size_mb"] for item in items)
        lbl_storage.value = f"{len(items)} dosya · {total_mb:.1f} MB"

        if not items:
            files_list.controls.append(
                W.empty_state(
                    ft.Icons.FOLDER_OFF_ROUNDED,
                    f"'{query}' ile eşleşen medya yok." if query
                    else "Henüz indirilmiş medya yok.",
                    f"Klasör: {controller.download_dir}",
                )
            )
        else:
            for item in items:
                is_audio = item["is_audio"]
                files_list.controls.append(
                    W.list_row(
                        item["title"],
                        f"{item['size_mb']} MB · {item['date']} · {item['media_type']}",
                        icon=(ft.Icons.AUDIOTRACK_ROUNDED if is_audio
                              else ft.Icons.MOVIE_ROUNDED),
                        icon_fill=(T.ICON_FILL_AUDIO if is_audio
                                   else T.ICON_FILL_VIDEO),
                        icon_color=(T.PURPLE_LIGHT if is_audio else T.PRIMARY_LIGHT),
                        actions=[
                            (ft.Icons.PLAY_ARROW_ROUNDED, "Oynat",
                             lambda p=item["path"]: controller.open_file_externally(p),
                             T.SUCCESS),
                            (ft.Icons.REFRESH_ROUNDED, "Tekrar indir",
                             lambda it=item: repeat_download(it), T.PRIMARY_LIGHT),
                            (ft.Icons.DELETE_OUTLINE_ROUNDED, "Sil",
                             lambda it=item: confirm_delete(it), T.DANGER),
                        ],
                    )
                )
        try:
            page.update()
        except Exception:
            logger.debug("[views.downloads] liste cizilemedi", exc_info=True)

    txt_search.on_change = lambda e: refresh_list()

    def clear_all_history():
        W.confirm_dialog(
            page, "Geçmişi temizle",
            "İndirme geçmişi kayıtları silinecek. Dosyaların kendisi cihazda kalır.",
            on_confirm=lambda: (_safe_clear_history(), refresh_list()),
            confirm_text="Temizle",
        )

    def _safe_clear_history():
        try:
            clear_history()
            W.snack(page, "Geçmiş kayıtları temizlendi.")
        except Exception as error:
            W.snack(page, f"Hata: {error}", T.DANGER_FILL)

    refresh_list()

    container = W.screen([
        W.page_title(
            "İndirilenler", ft.Icons.FOLDER_ROUNDED,
            [
                W.icon_button(ft.Icons.FOLDER_SPECIAL_ROUNDED,
                              lambda e: controller.open_file_externally(
                                  controller.download_dir),
                              color=T.WARNING, tooltip="Klasörü aç"),
                W.icon_button(ft.Icons.DELETE_SWEEP_ROUNDED,
                              lambda e: clear_all_history(),
                              color=T.TEXT_MUTED, tooltip="Geçmişi temizle"),
                W.icon_button(ft.Icons.REFRESH_ROUNDED, lambda e: refresh_list(),
                              color=T.PRIMARY_LIGHT, tooltip="Yenile"),
            ],
        ),
        txt_search,
        lbl_storage,
        files_list,
    ])
    container.refresh_downloads = refresh_list
    return container
