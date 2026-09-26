# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Film & Web Page View Mixin.
Builds the idle, advanced settings, resolved media, and downloading views for the Film tab.
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
from ui.config import get_default_download_directory


class FilmViewMixin:
    """
    Mixin containing page builder and state sub-views for the Film & Web tab.
    """

    def _build_film_page(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        host = ctk.CTkFrame(parent, fg_color="transparent")
        host.grid(row=0, column=0, sticky="new")
        host.grid_columnconfigure(0, weight=1)

        self.film_states = {
            "bos": ctk.CTkFrame(host, fg_color="transparent"),
            "cozumlendi": ctk.CTkFrame(host, fg_color="transparent"),
            "indiriliyor": ctk.CTkFrame(host, fg_color="transparent"),
        }
        for frame in self.film_states.values():
            frame.grid(row=0, column=0, sticky="new")
            frame.grid_columnconfigure(0, weight=1)

        self._build_film_idle(self.film_states["bos"])
        self._build_film_resolved(self.film_states["cozumlendi"])
        self._build_film_downloading(self.film_states["indiriliyor"])
        self._set_film_state("bos")

        self._log("Hazır. Film linkini yapıştırıp 'Çözümle' butonuna basın.")

    def _build_film_idle(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        W.label(card, "Film veya dizi linki", size=T.SIZE_BASE, weight=700,
                color=T.TEXT_MUTED).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=20, pady=12)
        row.grid_columnconfigure(0, weight=1)

        self.entry_film_page = W.entry(row, "Film sayfası linkini yapıştır…")
        self.entry_film_page.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        W.ghost_button(row, "Yapıştır", self._paste_film_url, icon="paste",
                       width=118).grid(row=0, column=1, padx=(0, 8))
        self.btn_resolve = W.primary_button(row, "Çözümle", self._resolve_film_threaded,
                                            width=120)
        self.btn_resolve.grid(row=0, column=2)

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        foot.grid_columnconfigure(1, weight=1)
        W.StepHint(foot, ["Linki yapıştır", "Çözümle", "Kaliteyi seç, indir"]).grid(
            row=0, column=0, sticky="w")
        W.link(foot, "Gelişmiş  ›", lambda: self.adv_film.toggle(),
               color=T.TEXT_MUTED).grid(row=0, column=2, sticky="e")

        self.adv_film = self._build_film_advanced(parent)
        self.adv_film.grid(row=1, column=0, sticky="ew", pady=(14, 0))

        recent = ctk.CTkFrame(parent, fg_color="transparent")
        recent.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        recent.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(recent, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)
        W.section_label(head, "Son indirilenler").grid(row=0, column=0, sticky="w")
        W.link(head, "Tümünü gör", lambda: self._show_page("library")).grid(
            row=0, column=1, sticky="e")

        self.recent_list_frame = ctk.CTkFrame(recent, fg_color="transparent")
        self.recent_list_frame.grid(row=1, column=0, sticky="ew")
        self.recent_list_frame.grid_columnconfigure(0, weight=1)

    def _build_film_advanced(self, parent):
        panel = W.Collapsible(parent, "Gelişmiş", "cURL · kanal sayısı · kayıt yolu")
        body = panel.body
        body.grid_columnconfigure(1, weight=1)

        W.ghost_button(body, "cURL komutundan içe aktar", self._import_from_curl,
                       icon="terminal", height=T.H_BUTTON_SM).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(6, 12))

        self.lbl_threads = W.label(body, "Kanal: 32x", size=T.SIZE_SM, weight=700,
                                   color=T.TEXT_MUTED)
        self.lbl_threads.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.slider_threads = ctk.CTkSlider(
            body, from_=2, to=64, number_of_steps=62, height=14,
            command=self._on_thread_slider_changed,
            fg_color=T.BG_APP, button_color=T.PRIMARY,
            button_hover_color=T.PRIMARY_HOVER, progress_color=T.PRIMARY)
        self.slider_threads.set(32)
        self.slider_threads.grid(row=1, column=1, sticky="ew")
        self.lbl_top_threads = W.label(body, "Maksimum (32x)", size=T.SIZE_XS,
                                       weight=700, color=T.TEXT_DIM)
        self.lbl_top_threads.grid(row=1, column=2, sticky="e", padx=(12, 0))

        W.label(body, "Kayıt yolu", size=T.SIZE_SM, weight=700,
                color=T.TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.entry_output = W.entry(body, height=T.H_BUTTON_SM)
        self.entry_output.insert(0, os.path.join(get_default_download_directory(), "film.mp4"))
        self.entry_output.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        W.ghost_button(body, "Gözat", self._browse_save_path, icon="folder_open",
                       height=T.H_BUTTON_SM, width=110).grid(row=3, column=2,
                                                             sticky="e", padx=(8, 0))
        return panel

    def _build_film_resolved(self, parent):
        strip = W.Card(parent, radius=T.R_TILE)
        strip.grid(row=0, column=0, sticky="ew")
        strip.grid_columnconfigure(1, weight=1)
        W.icon_label(strip, "check", 16, T.SUCCESS).grid(row=0, column=0, padx=(14, 10),
                                                         pady=12)
        self.lbl_resolved_url = W.label(strip, "", size=T.SIZE_BASE, weight=600,
                                        color=T.TEXT_MUTED)
        self.lbl_resolved_url.grid(row=0, column=1, sticky="w")
        W.link(strip, "Değiştir", lambda: self._set_film_state("bos")).grid(
            row=0, column=2, padx=(10, 14))

        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=W.icon_text("film"), font=F.icon(24),
                     text_color=T.PRIMARY, fg_color=T.BG_APP, corner_radius=10,
                     width=112, height=64).grid(row=0, column=0, padx=(20, 16), pady=(20, 0))

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=(20, 0))
        info.grid_columnconfigure(0, weight=1)
        self.lbl_resolved_title = W.label(info, "Medya: Henüz taranmadı",
                                          size=T.SIZE_TITLE, weight=800)
        self.lbl_resolved_title.grid(row=0, column=0, sticky="w")
        self.resolved_meta_frame = ctk.CTkFrame(info, fg_color="transparent")
        self.resolved_meta_frame.grid(row=1, column=0, sticky="w", pady=(6, 0))

        picks = ctk.CTkFrame(card, fg_color="transparent")
        picks.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=16)
        picks.grid_columnconfigure((0, 1), weight=1, uniform="pick")

        W.section_label(picks, "Kalite").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.opt_quality = W.OptionPills(picks, values=["🌟 En Yüksek Kalite"],
                                         command=self._on_quality_changed)
        self.opt_quality.grid(row=1, column=0, sticky="nw", padx=(0, 20))

        W.section_label(picks, "Ses").grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.opt_audio_track = W.OptionPills(picks, values=["🎧 Varsayılan Ses"],
                                             command=self._on_audio_track_changed)
        self.opt_audio_track.grid(row=1, column=1, sticky="nw")

        W.Divider(card).grid(row=2, column=0, columnspan=2, sticky="ew", padx=20)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 20))
        actions.grid_columnconfigure(2, weight=1)
        self.btn_start = W.success_button(actions, "İndir", self._start_film_download_threaded,
                                          icon="download", width=150)
        self.btn_start.grid(row=0, column=0, padx=(0, 10))
        self.btn_add_to_queue = W.ghost_button(actions, "Sıraya ekle",
                                               self._add_current_film_to_queue,
                                               icon="playlist_add", width=150)
        self.btn_add_to_queue.grid(row=0, column=1)
        self.lbl_save_hint = W.label(actions, "", size=T.SIZE_SM, weight=600,
                                     color=T.TEXT_MUTED, anchor="e")
        self.lbl_save_hint.grid(row=0, column=2, sticky="e", padx=(12, 8))
        W.link(actions, "Değiştir", self._browse_save_path).grid(row=0, column=3)

    def _build_film_downloading(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 0))
        head.grid_columnconfigure(0, weight=1)
        self.lbl_dl_title = W.label(head, "İndiriliyor", size=T.SIZE_LG, weight=800)
        self.lbl_dl_title.grid(row=0, column=0, sticky="w")
        self.lbl_status_metric = W.label(head, "Durum: Hazır", size=T.SIZE_SM,
                                         weight=600, color=T.TEXT_MUTED)
        self.lbl_status_metric.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.lbl_progress_text = W.label(head, "0%", size=T.SIZE_HERO, weight=600,
                                         mono=True, anchor="e")
        self.lbl_progress_text.grid(row=0, column=1, rowspan=2, sticky="e")

        self.progress_bar = W.ProgressBar(card, height=8)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=22, pady=16)

        tiles = ctk.CTkFrame(card, fg_color="transparent")
        tiles.grid(row=2, column=0, sticky="ew", padx=22)
        tiles.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="tile")
        self.tile_speed = W.StatTile(tiles, "Hız", "0.00 MB/s", T.WARNING)
        self.tile_speed.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.tile_eta = W.StatTile(tiles, "Kalan", "--:--")
        self.tile_eta.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.tile_elapsed = W.StatTile(tiles, "Geçen", "00:00")
        self.tile_elapsed.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        self.tile_size = W.StatTile(tiles, "Boyut", "0.0 MB")
        self.tile_size.grid(row=0, column=3, sticky="ew")

        self.lbl_speed_text = self.tile_speed._value
        self.lbl_eta_time = self.tile_eta._value
        self.lbl_elapsed_time = self.tile_elapsed._value
        self.lbl_size_text = self.tile_size._value

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=22, pady=(16, 20))
        controls.grid_columnconfigure(3, weight=1)
        self.btn_pause = W.ghost_button(controls, "Duraklat", self._toggle_pause_download,
                                        icon="pause", height=T.H_BUTTON_SM, width=140)
        self.btn_pause.grid(row=0, column=0, padx=(0, 8))
        self.btn_cancel = W.danger_button(controls, "İptal", self._cancel_download,
                                          icon="cancel", width=120)
        self.btn_cancel.grid(row=0, column=1, padx=(0, 8))
        self.btn_open_folder = W.ghost_button(controls, "Klasör", self._open_output_folder,
                                              icon="folder_open", height=T.H_BUTTON_SM,
                                              width=120)
        self.btn_open_folder.grid(row=0, column=2)
        W.label(controls, "Bittiğinde bildirim gösterilecek", size=T.SIZE_SM,
                weight=600, color=T.TEXT_MUTED, anchor="e").grid(row=0, column=3, sticky="e")

        self.log_film = W.Collapsible(parent, "İşlem günlüğü", "0 satır")
        self.log_film.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.txt_logs = ctk.CTkTextbox(self.log_film.body, height=150,
                                       font=F.mono(T.SIZE_SM, 500),
                                       fg_color=T.BG_APP, corner_radius=T.R_TILE,
                                       border_width=0, text_color=T.TEXT_MUTED)
        self.txt_logs.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.txt_logs.configure(state="disabled")
        W.link(self.log_film.body, "Temizle", self._clear_film_logs,
               color=T.TEXT_MUTED).grid(row=1, column=0, sticky="e", pady=(6, 0))
