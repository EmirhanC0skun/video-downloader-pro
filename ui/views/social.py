# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Social Media Page View Mixin.
Builds the idle, advanced settings, resolved media, and downloading views for the Social tab.
"""

try:
    import customtkinter as ctk
    from ui import fonts as F
    from ui import widgets as W
except Exception:
    ctk = None
    F = None
    W = None

from ui import theme as T
from ui.config import get_default_download_directory


class SocialViewMixin:
    """
    Mixin containing page builder and state sub-views for the Social Media tab.
    """

    def _build_social_page(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        host = ctk.CTkFrame(parent, fg_color="transparent")
        host.grid(row=0, column=0, sticky="new")
        host.grid_columnconfigure(0, weight=1)

        self.social_states = {
            "bos": ctk.CTkFrame(host, fg_color="transparent"),
            "cozumlendi": ctk.CTkFrame(host, fg_color="transparent"),
            "indiriliyor": ctk.CTkFrame(host, fg_color="transparent"),
        }
        for frame in self.social_states.values():
            frame.grid(row=0, column=0, sticky="new")
            frame.grid_columnconfigure(0, weight=1)

        self._build_social_idle(self.social_states["bos"])
        self._build_social_resolved(self.social_states["cozumlendi"])
        self._build_social_downloading(self.social_states["indiriliyor"])
        self._set_social_state("bos")

    def _build_social_idle(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        W.label(card, "Video veya müzik linki", size=T.SIZE_BASE, weight=700,
                color=T.TEXT_MUTED).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=20, pady=12)
        row.grid_columnconfigure(0, weight=1)
        self.entry_yt_url = W.entry(row, "YouTube, Instagram, TikTok veya X bağlantısı…")
        self.entry_yt_url.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        W.ghost_button(row, "Yapıştır", self._paste_yt_url, icon="paste",
                       width=118).grid(row=0, column=1, padx=(0, 8))
        self.btn_yt_resolve = W.primary_button(row, "Çözümle",
                                               self._resolve_youtube_url_threaded, width=120)
        self.btn_yt_resolve.grid(row=0, column=2)

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        foot.grid_columnconfigure(1, weight=1)
        W.StepHint(foot, ["Linki yapıştır", "Çözümle", "Biçimi seç, indir"]).grid(
            row=0, column=0, sticky="w")
        W.link(foot, "Gelişmiş  ›", lambda: self.adv_social.toggle(),
               color=T.TEXT_MUTED).grid(row=0, column=2, sticky="e")

        self.adv_social = self._build_social_advanced(parent)
        self.adv_social.grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def _build_social_advanced(self, parent):
        panel = W.Collapsible(parent, "Gelişmiş", "oturum · çerez · hedef klasör")
        body = panel.body
        body.grid_columnconfigure(1, weight=1)

        W.label(body, "Oturum / çerez", size=T.SIZE_SM, weight=700,
                color=T.TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=(6, 6))
        self.opt_yt_cookies = ctk.CTkOptionMenu(
            body,
            values=["🚫 Oturum Yok (Genel)", "🌐 Chrome Oturumu", "🌐 Edge Oturumu",
                    "🌐 Firefox Oturumu", "🌐 Brave Oturumu", "📁 Çerez Dosyası (.txt)"],
            height=T.H_BUTTON_SM, width=210, command=self._on_yt_cookie_changed,
            corner_radius=T.R_INPUT, fg_color=T.BG_APP, button_color=T.BG_ELEVATED,
            button_hover_color=T.BG_HOVER, text_color=T.TEXT,
            dropdown_fg_color=T.BG_ELEVATED, dropdown_text_color=T.TEXT,
            dropdown_hover_color=T.BG_HOVER, font=F.ui(T.SIZE_SM, 600),
            dropdown_font=F.ui(T.SIZE_SM, 600))
        self.opt_yt_cookies.grid(row=1, column=0, sticky="w", padx=(0, 8))

        self.entry_cookie_file = W.entry(body, "cookies.txt dosya yolu (opsiyonel)…",
                                         height=T.H_BUTTON_SM)
        self.entry_cookie_file.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.btn_cookie_browse = W.ghost_button(body, ".txt seç", self._browse_cookie_file,
                                                height=T.H_BUTTON_SM, width=110)
        self.btn_cookie_browse.grid(row=1, column=2)

        W.label(body, "Hedef klasör", size=T.SIZE_SM, weight=700,
                color=T.TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=(14, 6))
        self.entry_yt_dir = W.entry(body, height=T.H_BUTTON_SM)
        self.entry_yt_dir.insert(0, get_default_download_directory())
        self.entry_yt_dir.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        W.ghost_button(body, "Seç", self._browse_yt_dir, icon="folder_open",
                       height=T.H_BUTTON_SM, width=110).grid(row=3, column=2)
        return panel

    def _build_social_resolved(self, parent):
        strip = W.Card(parent, radius=T.R_TILE)
        strip.grid(row=0, column=0, sticky="ew")
        strip.grid_columnconfigure(1, weight=1)
        W.icon_label(strip, "check", 16, T.SUCCESS).grid(row=0, column=0, padx=(14, 10),
                                                         pady=12)
        self.lbl_yt_resolved_url = W.label(strip, "", size=T.SIZE_BASE, weight=600,
                                           color=T.TEXT_MUTED)
        self.lbl_yt_resolved_url.grid(row=0, column=1, sticky="w")
        W.link(strip, "Değiştir", lambda: self._set_social_state("bos")).grid(
            row=0, column=2, padx=(10, 14))

        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=W.icon_text("social"), font=F.icon(24),
                     text_color=T.PRIMARY, fg_color=T.BG_APP, corner_radius=10,
                     width=112, height=64).grid(row=0, column=0, padx=(20, 16), pady=(20, 0))
        self.lbl_yt_title = W.label(card, "Medya: Henüz taranmadı", size=T.SIZE_TITLE,
                                    weight=800)
        self.lbl_yt_title.grid(row=0, column=1, sticky="sw", padx=(0, 20), pady=(20, 0))

        W.section_label(card, "Biçim").grid(row=1, column=0, columnspan=2, sticky="w",
                                            padx=20, pady=(16, 8))
        self.opt_yt_format = W.OptionPills(
            card,
            values=["🌟 En Yüksek Kalite (4K / 1080p)", "🎬 1080p Full HD", "📺 720p HD",
                    "📱 480p SD", "⚡ 360p Düşük", "🎵 Sadece Ses (MP3 320k)",
                    "🎧 Sadece Ses (M4A / AAC)"])
        self.opt_yt_format.grid(row=2, column=0, columnspan=2, sticky="w", padx=20)

        W.Divider(card).grid(row=3, column=0, columnspan=2, sticky="ew", padx=20,
                             pady=(10, 0))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 20))
        actions.grid_columnconfigure(2, weight=1)
        self.btn_yt_start = W.success_button(actions, "İndir",
                                             self._start_youtube_download_threaded,
                                             icon="download", width=150)
        self.btn_yt_start.grid(row=0, column=0, padx=(0, 10))
        self.btn_yt_add_queue = W.ghost_button(actions, "Sıraya ekle",
                                               self._add_current_yt_to_queue,
                                               icon="playlist_add", width=150)
        self.btn_yt_add_queue.grid(row=0, column=1)
        W.ghost_button(actions, "Klasörü aç", self._open_yt_folder, icon="folder_open",
                       width=140).grid(row=0, column=3, sticky="e")

    def _build_social_downloading(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 0))
        head.grid_columnconfigure(0, weight=1)
        self.lbl_yt_progress = W.label(head, "Durum: Hazır", size=T.SIZE_LG, weight=800)
        self.lbl_yt_progress.grid(row=0, column=0, sticky="w")
        self.lbl_yt_pct = W.label(head, "0%", size=T.SIZE_HERO, weight=600, mono=True,
                                  anchor="e")
        self.lbl_yt_pct.grid(row=0, column=1, rowspan=2, sticky="e")

        self.yt_pbar = W.ProgressBar(card, height=8)
        self.yt_pbar.grid(row=1, column=0, sticky="ew", padx=22, pady=16)

        tiles = ctk.CTkFrame(card, fg_color="transparent")
        tiles.grid(row=2, column=0, sticky="ew", padx=22)
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="yt")
        self.tile_yt_speed = W.StatTile(tiles, "Hız", "0.00 MB/s", T.WARNING)
        self.tile_yt_speed.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.tile_yt_eta = W.StatTile(tiles, "Kalan", "--:--")
        self.tile_yt_eta.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.tile_yt_elapsed = W.StatTile(tiles, "Geçen", "00:00")
        self.tile_yt_elapsed.grid(row=0, column=2, sticky="ew")
        self.lbl_yt_speed = self.tile_yt_speed._value
        self.lbl_yt_eta = self.tile_yt_eta._value
        self.lbl_yt_elapsed = self.tile_yt_elapsed._value

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=22, pady=(16, 20))
        controls.grid_columnconfigure(1, weight=1)
        self.btn_yt_cancel = W.danger_button(controls, "İptal",
                                             self._cancel_youtube_download,
                                             icon="cancel", width=120)
        self.btn_yt_cancel.grid(row=0, column=0)
        W.label(controls, "Bittiğinde bildirim gösterilecek", size=T.SIZE_SM,
                weight=600, color=T.TEXT_MUTED, anchor="e").grid(row=0, column=1, sticky="e")

        self.log_social = W.Collapsible(parent, "İşlem günlüğü", "0 satır")
        self.log_social.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.txt_yt_logs = ctk.CTkTextbox(self.log_social.body, height=150,
                                          font=F.mono(T.SIZE_SM, 500),
                                          fg_color=T.BG_APP, corner_radius=T.R_TILE,
                                          border_width=0, text_color=T.TEXT_MUTED)
        self.txt_yt_logs.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.txt_yt_logs.configure(state="disabled")
