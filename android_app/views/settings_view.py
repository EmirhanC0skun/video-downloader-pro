# -*- coding: utf-8 -*-
"""Ayarlar & Güvenlik ekranı.

Masaüstündeki `ui/views/settings.py` gibi kurulur: her satır bir başlık, bir
açıklama ve sağda tek bir kontrol taşır. Hız profili bir pill kümesidir —
mobilde açılır menüden hem daha görünür hem daha kolay vurulur.
"""

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

logger = get_logger("views.settings")

try:
    import theme as T
    import widgets as W
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W

APP_VERSION = "2.8.0"

# Pill etiketi -> kanal sayisi. Mobil varsayilani 4x'tir: telefonda daha fazla
# es zamanli baglanti pil ve isi maliyetini indirme hizindan hizli buyutur.
SPEED_PROFILES = [
    ("Dengeli (4x)", 4),
    ("Hızlı (8x)", 8),
    ("Maksimum (16x)", 16),
    ("Turbo (32x)", 32),
]


def build_settings_view(page: ft.Page, controller):
    """Ayarlar ekranını kurar ve döndürür."""
    speed_keys = {text: value for text, value in SPEED_PROFILES}

    def on_speed_selected(value):
        # Eskiden bu secim bir `Dropdown`un `on_change` niteligiyle okunuyordu;
        # Flet 0.86'da o alan yok, atama olu kaliyor ve hiz profili hicbir zaman
        # uygulanmiyordu.
        threads = speed_keys.get(value)
        if not threads:
            return
        controller.speed_threads = threads
        W.snack(page, f"Hız profili: {threads}x kanal", T.SUCCESS_FILL)

    pills_speed = W.PillGroup([text for text, _ in SPEED_PROFILES],
                              on_select=on_speed_selected)
    current = next((text for text, value in SPEED_PROFILES
                    if value == controller.speed_threads), None)
    if current:
        pills_speed.set(current)

    txt_download_dir = W.text_field("İndirme klasörü",
                                    value=controller.download_dir, expand=True)

    def apply_download_dir():
        target = (txt_download_dir.value or "").strip()
        if not target:
            return
        if controller.set_download_dir(target):
            W.snack(page, "İndirme klasörü güncellendi.", T.SUCCESS_FILL)
        else:
            W.snack(page, "Klasör oluşturulamadı, eski yol korundu.", T.DANGER_FILL)
            txt_download_dir.value = controller.download_dir
            page.update()

    def run_android_settings_intent(action, extras, message):
        """Android sistem ayar ekranını açar.

        `am start` yalnızca cihazda çalışır; masaüstünde sessizce hiçbir şey
        yapmaz — komut yoksa kullanıcıya hata göstermenin anlamı yok.
        """
        import subprocess
        try:
            subprocess.run(["am", "start", "-a", action] + extras,
                           capture_output=True, timeout=2)
            W.snack(page, message)
        except Exception:
            logger.debug("[views.settings] sistem ayari acilamadi", exc_info=True)
            W.snack(page, "Bu ayar yalnızca Android cihazda açılabilir.",
                    T.WARNING_FILL)

    def open_notification_settings(e=None):
        package = "com.videodownloaderpro.videodownloaderpro"
        run_android_settings_intent(
            "android.settings.APP_NOTIFICATION_SETTINGS",
            ["--es", "android.provider.extra.APP_PACKAGE", package,
             "--es", "app_package", package],
            "Bildirim ayarları açılıyor…")

    def open_battery_settings(e=None):
        run_android_settings_intent(
            "android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
            ["-d", "package:com.videodownloaderpro.videodownloaderpro"],
            "Pil optimizasyonu ayarları açılıyor…")

    def grant_all_permissions(e=None):
        from mobile_engine import request_android_permissions
        request_android_permissions()
        W.snack(page, "Tüm izinler talep edildi.", T.SUCCESS_FILL)

    def info_line(icon, text, color=T.TEXT_MUTED):
        return ft.Row(
            [
                ft.Icon(icon, size=14, color=color),
                W.label(text, size=T.SIZE_SM, color=T.TEXT_MUTED, expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    card_permissions = W.card(
        ft.Column(
            spacing=12,
            tight=True,
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED, size=18,
                            color=T.PRIMARY_LIGHT),
                    W.label("Bildirim & arka plan izinleri", size=T.SIZE_BASE,
                            weight=T.W_EXTRA),
                ], spacing=8),
                W.label("İndirme yüzdesini bildirim çubuğunda canlı izlemek ve "
                        "ekran kapandığında indirmelerin sürmesi için:",
                        size=T.SIZE_SM, color=T.TEXT_MUTED),
                ft.Row(
                    [
                        W.ghost_button("Bildirimler", open_notification_settings,
                                       icon=ft.Icons.NOTIFICATIONS_ROUNDED,
                                       height=T.H_BUTTON_SM, expand=1),
                        W.ghost_button("Pil izni", open_battery_settings,
                                       icon=ft.Icons.BATTERY_SAVER_ROUNDED,
                                       height=T.H_BUTTON_SM, expand=1),
                    ],
                    spacing=T.GAP_TOUCH,
                ),
                W.full_width(
                    W.primary_button("Tüm izinleri onayla", grant_all_permissions,
                                     icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
                                     height=T.H_BUTTON_SM)),
            ],
        ),
        border=T.PRIMARY,
    )

    card_performance = W.card(
        ft.Column(
            spacing=12,
            tight=True,
            controls=[
                W.section_label("Hız & performans"),
                W.label("Aynı anda kaç paralel kanal açılacağını belirler. Mobilde "
                        "yüksek değerler pil ve ısı maliyetini hızdan daha çok "
                        "büyütür.", size=T.SIZE_SM, color=T.TEXT_MUTED),
                pills_speed,
            ],
        )
    )

    card_storage = W.card(
        ft.Column(
            spacing=12,
            tight=True,
            controls=[
                W.section_label("Depolama"),
                txt_download_dir,
                W.full_width(
                    W.ghost_button("Klasörü uygula", lambda e: apply_download_dir(),
                                   icon=ft.Icons.FOLDER_SPECIAL_ROUNDED,
                                   height=T.H_BUTTON_SM)),
            ],
        )
    )

    card_network = W.card(
        ft.Column(
            spacing=10,
            tight=True,
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.SHIELD_ROUNDED, size=18, color=T.SUCCESS),
                    W.label("Ağ & DPI güvenliği", size=T.SIZE_BASE, weight=T.W_EXTRA),
                ], spacing=8),
                info_line(ft.Icons.DNS_ROUNDED,
                          "Cloudflare DoH (DNS over HTTPS) aktif"),
                info_line(ft.Icons.FINGERPRINT_ROUNDED,
                          "Chrome 124 TLS parmak izi taklidi (curl_cffi)"),
                info_line(ft.Icons.LOCK_ROUNDED,
                          "AES-128 HLS şifre çözücü ve n-sig çözücü entegre"),
            ],
        )
    )

    card_about = W.card(
        ft.Column(
            spacing=10,
            tight=True,
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=18, color=T.PRIMARY),
                    W.label("Video Downloader Pro", size=T.SIZE_BASE,
                            weight=T.W_EXTRA, expand=True),
                    W.meta_chip(f"v{APP_VERSION}"),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                info_line(ft.Icons.MEMORY_ROUNDED,
                          "32 kanallı paralel HLS/fMP4 motoru ve evrensel AAC muxer"),
                info_line(ft.Icons.PHONE_ANDROID_ROUNDED,
                          "Flutter & Flet Material 3 (Android / masaüstü)"),
                info_line(ft.Icons.PERSON_ROUNDED, "Geliştirici: Emirhan Coşkun"),
            ],
        )
    )

    return W.screen([
        W.page_title("Ayarlar & Güvenlik", ft.Icons.SETTINGS_ROUNDED),
        card_permissions,
        card_performance,
        card_storage,
        card_network,
        card_about,
    ])
