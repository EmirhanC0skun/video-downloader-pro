import os
import sys
import asyncio

# Android ARM64 FFmpeg & Native Library Environment Initialization
if sys.platform != "win32":
    try:
        import shutil, stat as _stat
        _src_dir = "/data/local/tmp"
        _app_data_dir = None
        for _candidate in [
            "/data/user/0/com.videodownloaderpro.videodownloaderpro/cache",
            "/data/data/com.videodownloaderpro.videodownloaderpro/cache",
            "/data/user/0/com.videodownloaderpro.videodownloaderpro/files",
            "/data/data/com.videodownloaderpro.videodownloaderpro/files",
        ]:
            if os.path.isdir(_candidate):
                _app_data_dir = _candidate
                break
        if _app_data_dir is None:
            _tmpdir = os.environ.get("TMPDIR", "")
            if _tmpdir and os.path.isdir(_tmpdir):
                _app_data_dir = _tmpdir

        if _app_data_dir and os.path.exists(_src_dir):
            # Copy ffmpeg and all dependent .so libraries so SELinux & Android linker allow execution
            for fn in [
                "ffmpeg", "libavcodec.so", "libavdevice.so", "libavfilter.so",
                "libavformat.so", "libavutil.so", "libpostproc.so", "libswresample.so", "libswscale.so"
            ]:
                src_f = os.path.join(_src_dir, fn)
                dst_f = os.path.join(_app_data_dir, fn)
                if os.path.exists(src_f):
                    if not os.path.exists(dst_f) or os.path.getsize(dst_f) != os.path.getsize(src_f):
                        try:
                            shutil.copy2(src_f, dst_f)
                        except Exception:
                            pass
                    if os.path.exists(dst_f):
                        try:
                            os.chmod(dst_f, _stat.S_IRWXU | _stat.S_IRGRP | _stat.S_IXGRP | _stat.S_IROTH | _stat.S_IXOTH)
                        except Exception:
                            pass

            os.environ["PATH"] = _app_data_dir + ":" + _src_dir + ":" + os.environ.get("PATH", "")
            os.environ["LD_LIBRARY_PATH"] = f"{_app_data_dir}:{_src_dir}:" + os.environ.get("LD_LIBRARY_PATH", "")
    except Exception:
        pass

import flet as ft

# Üst dizin bağlantısı
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from mobile_engine import MobileDownloadController, configure_android_services
from views.film_view import build_film_view
from views.social_view import build_social_view
from views.queue_view import build_queue_view
from views.converter_view import build_converter_view
from views.downloads_view import build_downloads_view
from views.settings_view import build_settings_view

# Tasarim belirtecleri ve bilesen kitapligi tek kaynaktan gelir.
try:
    import theme as T
    import widgets as W
    import fonts as UIFonts
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T
    from android_app import widgets as W
    from android_app import fonts as UIFonts

APP_VERSION = "2.8.0"

# Gezinme cubugundaki ekranlar. Masaüstündeki `ShellViewMixin.NAV_PAGES` ile
# ayni sira ve ayni adlar — iki uygulamada ayni sekme ayni yerde durur.
NAV_PAGES = (
    ("Film & Web", ft.Icons.LOCAL_MOVIES_OUTLINED, ft.Icons.LOCAL_MOVIES_ROUNDED),
    ("Sosyal", ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED),
    ("Kuyruk", ft.Icons.PLAYLIST_PLAY_ROUNDED, ft.Icons.PLAYLIST_ADD_CHECK_ROUNDED),
    ("Dönüştür", ft.Icons.TRANSFORM_ROUNDED, ft.Icons.CHANGE_CIRCLE_ROUNDED),
    ("İndirilenler", ft.Icons.FOLDER_OUTLINED, ft.Icons.FOLDER_ROUNDED),
)

# Denetleyici durumu -> (rozet metni, nokta rengi). Masaüstündeki StatusCard
# ile ayni sozluk.
STATUS_LABELS = {
    "IDLE": ("Hazır", T.SUCCESS),
    "DOWNLOADING": ("İndiriliyor", T.PRIMARY_LIGHT),
    "PAUSED": ("Duraklatıldı", T.WARNING),
    "COMPLETED": ("Tamamlandı", T.SUCCESS),
    "CANCELLED": ("İptal edildi", T.TEXT_MUTED),
    "ERROR": ("Hata", T.DANGER),
}


def main(page: ft.Page):
    page.title = f"Video Downloader Pro v{APP_VERSION}"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = T.BG_APP
    page.padding = 0

    # Gomulu Manrope / JetBrains Mono — masaüstüyle ayni harf formu. Varliklar
    # paketlenmemisse sessizce sistem fontuna duser.
    UIFonts.register(page)
    page.theme = ft.Theme(
        color_scheme_seed=T.PRIMARY,
        font_family=T.FONT_UI,
        use_material3=True,
    )

    page.window.width = 440
    page.window.height = 900
    page.window.resizable = True

    controller = MobileDownloadController()
    configure_android_services(page, controller)
    preferences = ft.SharedPreferences()
    page.services.append(preferences)

    # -- App bar --------------------------------------------------------------
    status_dot = W.status_dot(T.SUCCESS)
    status_text = W.label("Hazır", size=T.SIZE_XS, weight=T.W_BOLD, color=T.TEXT_MUTED)
    status_chip = ft.Container(
        content=ft.Row([status_dot, status_text], spacing=6, tight=True),
        bgcolor=T.BG_ELEVATED,
        border_radius=T.R_CHIP,
        padding=W.padding(10, 6),
        margin=ft.Margin(0, 0, 4, 0),
    )

    def paint_status(state: str = None) -> None:
        """Üst çubuktaki canlı durum rozetini denetleyici durumuna göre boyar."""
        text, color = STATUS_LABELS.get(state or controller.state,
                                        STATUS_LABELS["IDLE"])
        status_text.value = text
        status_dot.bgcolor = color
        try:
            status_chip.update()
        except Exception:
            pass

    # Denetleyici indirme durumu her degistiginde rozeti gunceller.
    controller.status_handler = paint_status

    settings_open = [False]

    btn_settings = W.icon_button(
        ft.Icons.SETTINGS_ROUNDED,
        on_click=lambda e: open_settings(),
        color=T.TEXT_MUTED,
        tooltip="Ayarlar & Güvenlik",
    )
    btn_back = W.icon_button(
        ft.Icons.ARROW_BACK_ROUNDED,
        on_click=lambda e: close_settings(),
        color=T.TEXT,
        tooltip="Geri",
    )
    btn_back.visible = False

    page.appbar = ft.AppBar(
        leading=ft.Container(
            content=ft.Icon(ft.Icons.BOLT_ROUNDED, color="#FFFFFF", size=18),
            bgcolor=T.PRIMARY,
            border_radius=9,
            width=30,
            height=30,
            margin=ft.Margin(12, 0, 0, 0),
            alignment=ft.Alignment(0, 0),
        ),
        leading_width=46,
        title=ft.Row(
            spacing=8,
            tight=True,
            controls=[
                W.label("Video Downloader", size=T.SIZE_MD, weight=T.W_EXTRA),
                ft.Container(
                    content=W.label(f"v{APP_VERSION}", size=T.SIZE_XS,
                                    weight=T.W_BOLD, color=T.PRIMARY_TINT, mono=True),
                    bgcolor=T.PRIMARY_BADGE,
                    border_radius=6,
                    padding=W.padding(6, 2),
                ),
            ],
        ),
        center_title=False,
        bgcolor=T.BG_SIDEBAR,
        toolbar_height=T.APPBAR_H,
        elevation=0,
        actions=[status_chip, btn_back, btn_settings],
    )

    # -- Ekranlar -------------------------------------------------------------
    # Alti ekran da bir kez kurulur ve saklanir: sekme degistirmek widget
    # yeniden kurmaz, arka plan is parcaciklarindan gelen guncellemeler
    # hedefini sasirmaz. Masaüstündeki sayfa yonlendiricisiyle ayni yaklasim.
    view_film = build_film_view(page, controller)
    view_social = build_social_view(page, controller)
    view_queue = build_queue_view(page, controller)
    view_converter = build_converter_view(page, controller)
    view_downloads = build_downloads_view(page, controller)
    view_settings = build_settings_view(page, controller)

    tab_views = {
        0: view_film,
        1: view_social,
        2: view_queue,
        3: view_converter,
        4: view_downloads,
    }

    content_area = ft.Container(content=view_film, expand=True, bgcolor=T.BG_APP)

    def switch_to_tab(idx, url=None, auto_resolve=False):
        """Sekme yönlendiricisi. `controller.nav_handler` bunu çağırır."""
        close_settings(repaint=False)
        page.navigation_bar.selected_index = idx
        target_view = tab_views.get(idx, view_film)
        if url and hasattr(target_view, "set_url"):
            # Anahtar sozcuk adi `set_url` imzasiyla birebir eslesmeli; eskiden
            # `auto_resolve=` gonderiliyor ama gorunumler `auto_res` bekliyordu
            # ve Akilli Yonlendirici her devirde TypeError ile dusuyordu.
            target_view.set_url(url, auto_resolve=auto_resolve)
        elif idx == 4 and hasattr(target_view, "refresh_downloads"):
            target_view.refresh_downloads()
        elif idx == 3 and hasattr(target_view, "refresh_files"):
            target_view.refresh_files()
        content_area.content = target_view
        page.update()

    controller.nav_handler = switch_to_tab

    def open_settings():
        settings_open[0] = True
        btn_back.visible = True
        btn_settings.visible = False
        page.navigation_bar.visible = False
        content_area.content = view_settings
        page.update()

    def close_settings(repaint: bool = True):
        if not settings_open[0]:
            return
        settings_open[0] = False
        btn_back.visible = False
        btn_settings.visible = True
        page.navigation_bar.visible = True
        idx = page.navigation_bar.selected_index or 0
        content_area.content = tab_views.get(idx, view_film)
        if repaint:
            page.update()

    def on_navigation_change(e):
        idx = e.control.selected_index
        if idx is not None:
            switch_to_tab(idx)

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor=T.BG_SIDEBAR,
        indicator_color=T.PRIMARY_BADGE,
        indicator_shape=ft.RoundedRectangleBorder(radius=T.R_BADGE),
        shadow_color=T.BG_APP,
        border=ft.Border(top=ft.BorderSide(1, T.BORDER_SIDEBAR)),
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        on_change=on_navigation_change,
        elevation=0,
        destinations=[
            ft.NavigationBarDestination(icon=icon, selected_icon=selected, label=text)
            for text, icon, selected in NAV_PAGES
        ],
    )

    # Sistem cubuklari ve cikinti (notch) altina icerik kacmasin diye guvenli
    # alan sarmalayicisi; alt kenari gezinme cubugu zaten kendisi yonetir.
    page.add(ft.SafeArea(content=content_area, avoid_intrusions_bottom=False,
                         expand=True))

    # -- Ilk acilis izinleri --------------------------------------------------
    def prompt_permissions():
        def close_perm(e=None):
            W.dismiss(page, dlg_perm)

        async def grant_and_close(e=None):
            W.dismiss(page, dlg_perm)
            from mobile_engine import request_android_permissions
            permission_future = request_android_permissions()
            if permission_future is not None:
                await asyncio.wrap_future(permission_future)
            await preferences.set("vdpro.android.permissions_prompted", True)
            W.snack(page, "Android izinleri işlendi.", T.SUCCESS_FILL)

        def perm_row(icon, color, title, subtitle):
            return ft.Row(
                [
                    ft.Icon(icon, color=color, size=20),
                    ft.Column(
                        [
                            W.label(title, size=T.SIZE_SM, weight=T.W_BOLD),
                            W.label(subtitle, size=T.SIZE_XS, color=T.TEXT_MUTED),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        dlg_perm = ft.AlertDialog(
            modal=True,
            bgcolor=T.BG_CARD,
            shape=ft.RoundedRectangleBorder(radius=T.R_CARD),
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.SECURITY_ROUNDED, color=T.PRIMARY, size=22),
                    W.label("Arka plan & bildirim izinleri", size=T.SIZE_MD,
                            weight=T.W_EXTRA),
                ],
                spacing=8,
            ),
            content=ft.Column(
                tight=True,
                spacing=14,
                controls=[
                    W.label(
                        "İndirmelerin arka planda ve kilit ekranında kesintisiz "
                        "sürmesi için gereken izinler:",
                        size=T.SIZE_SM, color=T.TEXT_MUTED),
                    perm_row(ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED, T.PRIMARY_LIGHT,
                             "Canlı bildirimler",
                             "İndirme yüzdesini ve hızını canlı takip etmek için"),
                    perm_row(ft.Icons.BATTERY_SAVER_ROUNDED, T.WARNING,
                             "Arka plan & pil muafiyeti",
                             "Ekran kapandığında indirmelerin durmaması için"),
                    perm_row(ft.Icons.FOLDER_SPECIAL_ROUNDED, T.SUCCESS,
                             "Depolama & galeri erişimi",
                             "Videoları doğrudan galeriye kaydetmek için"),
                ],
            ),
            actions=[
                W.ghost_button("Daha sonra", close_perm, height=T.H_BUTTON_SM),
                W.primary_button("İzinleri onayla", grant_and_close,
                                 icon=ft.Icons.CHECK_ROUNDED, height=T.H_BUTTON_SM),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        W.show(page, dlg_perm)

    if sys.platform != "win32":
        async def prompt_permissions_once():
            prompted = await preferences.get("vdpro.android.permissions_prompted")
            if prompted is not True:
                prompt_permissions()

        page.run_task(prompt_permissions_once)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
