# -*- coding: utf-8 -*-
"""
Video Downloader Pro — UI Shell View Mixin.
Builds the sidebar, top header, page router host, and view state transitions.
"""

import os
try:
    import customtkinter as ctk
    from ui import fonts as F
    from ui import widgets as W
except Exception:
    ctk = None
    F = None
    W = None

from ui import theme as T
from ui.constants import APP_VERSION
from ui.config import get_default_download_directory


class ShellViewMixin:
    """
    Mixin providing main window shell layout, sidebar navigation, header, and page router.
    """

    NAV_PAGES = (
        ("film", "film", "Film & Web", "Film & Web", "Film ve dizi sitelerinden indir"),
        ("social", "social", "Sosyal Medya", "Sosyal Medya", "YouTube, Instagram, TikTok, X"),
        ("queue", "queue", "Kuyruk", "Kuyruk", "Dizileri toplu indir"),
        ("library", "library", "İndirilenler", "İndirilenler", "Kütüphane ve geçmiş"),
        ("converter", "convert", "Dönüştürücü", "Dönüştürücü", "Videodan ses çıkar"),
        ("settings", "settings", "Ayarlar", "Ayarlar", "Basit tut, gerekirse Gelişmiş'i aç"),
    )

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        main = ctk.CTkFrame(self, fg_color=T.BG_APP, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_header(main)

        # Tum sayfalar ayni hucreye gridlenir; yonlendirici yalnizca birini
        # gorunur birakir. Boylece sayfa degistirmek widget yeniden kurmaz ve
        # arka plan is parcaciklarindan gelen guncellemeler hedefini sasirmaz.
        self.page_host = ctk.CTkFrame(main, fg_color="transparent")
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=28, pady=(22, 24))
        self.page_host.grid_columnconfigure(0, weight=1, minsize=0)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.pages = {}
        builders = {
            "film": self._build_film_page,
            "social": self._build_social_page,
            "queue": self._build_queue_page,
            "library": self._build_library_page,
            "converter": self._build_converter_page,
            "settings": self._build_settings_page,
        }
        for key, _icon, _nav, _title, _sub in self.NAV_PAGES:
            # Tasarim icerigi 800px'te sabitler; pencere genislese de sayfa
            # sola yasli ve okunabilir genislikte kalir.
            page = ctk.CTkFrame(self.page_host, fg_color="transparent",
                                width=T.CONTENT_MAX_W)
            page.grid(row=0, column=0, sticky="nsw")
            page.grid_columnconfigure(0, weight=1, minsize=T.CONTENT_MAX_W)
            self.pages[key] = page
            builders[key](page)

        self._show_page("film")

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, fg_color=T.BG_SIDEBAR, corner_radius=0,
                           width=T.SIDEBAR_W)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(len(self.NAV_PAGES) + 1, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=12, pady=(18, 18))
        brand.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(brand, text=W.icon_text("bolt"), font=F.icon(16),
                     text_color="#FFFFFF", fg_color=T.PRIMARY, corner_radius=9,
                     width=30, height=30).grid(row=0, column=0, rowspan=2, padx=(8, 10))
        W.label(brand, "Video Downloader", size=T.SIZE_MD, weight=800).grid(
            row=0, column=1, sticky="sw")
        W.label(brand, f"Pro · v{APP_VERSION}", size=T.SIZE_XS, weight=600,
                color=T.TEXT_MUTED).grid(row=1, column=1, sticky="nw")

        self.nav = {}
        for row, (key, icon_name, nav_text, _title, _sub) in enumerate(self.NAV_PAGES, start=1):
            item = W.SidebarItem(bar, icon_name, nav_text,
                                 command=lambda k=key: self._show_page(k))
            item.grid(row=row, column=0, sticky="ew", padx=12, pady=3)
            self.nav[key] = item

        self.status_card = W.StatusCard(bar)
        self.status_card.grid(row=len(self.NAV_PAGES) + 2, column=0, sticky="ew",
                              padx=12, pady=(0, 14))

    def _build_header(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent", height=T.HEADER_H)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        head.grid_columnconfigure(0, weight=1)
        # Baslik bloguna disaridan esit bosluk veren bos satirlar; tasarimda
        # baslik 64px cubugun dikey merkezindedir.
        head.grid_rowconfigure(0, weight=1)
        head.grid_rowconfigure(3, weight=1)

        self.lbl_page_title = W.label(head, "Film & Web", size=T.SIZE_XL, weight=800)
        self.lbl_page_title.grid(row=1, column=0, sticky="sw", padx=28)
        self.lbl_page_sub = W.label(head, "", size=T.SIZE_SM, weight=600,
                                    color=T.TEXT_MUTED)
        self.lbl_page_sub.grid(row=2, column=0, sticky="nw", padx=28, pady=(2, 0))

        def_dir_name = os.path.basename(get_default_download_directory()) or "VideoDownloaderPro"
        self.btn_header_folder = ctk.CTkButton(
            head, text=f"{W.icon_text('folder')}  {def_dir_name}",
            height=34, corner_radius=T.R_BADGE, fg_color=T.BG_CARD,
            hover_color=T.BG_ELEVATED, text_color=T.TEXT_MUTED,
            border_width=1, border_color=T.BORDER,
            font=F.ui(T.SIZE_SM, 700), command=self._open_output_folder)
        self.btn_header_folder.grid(row=1, column=1, rowspan=2, sticky="e", padx=(0, 28))

        W.Divider(parent, color=T.over("#FFFFFF", T.BG_APP, 0.05)).grid(
            row=0, column=0, sticky="sew")

    def _show_page(self, key):
        """Sayfa yönlendiricisi — eski `tabview.set()` çağrılarının yerini alır."""
        if key not in self.pages:
            return
        for name, page in self.pages.items():
            page.grid() if name == key else page.grid_remove()
        for name, item in self.nav.items():
            item.set_active(name == key)

        for entry in self.NAV_PAGES:
            if entry[0] == key:
                self.lbl_page_title.configure(text=entry[3])
                self.lbl_page_sub.configure(text=entry[4])
                break

        self.current_page = key
        if key == "library":
            self._refresh_history_ui()
        elif key == "film":
            self._refresh_recent_list()

    def _set_film_state(self, state):
        """Film sayfasını `bos` / `cozumlendi` / `indiriliyor` durumuna geçirir."""
        self._film_state = state
        for name, frame in self.film_states.items():
            frame.grid() if name == state else frame.grid_remove()

    def _set_social_state(self, state):
        self._social_state = state
        for name, frame in self.social_states.items():
            frame.grid() if name == state else frame.grid_remove()
