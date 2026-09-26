# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Settings Page View Mixin.
Builds the user settings page, speed presets, subtitle preferences, and directory choosers.
"""

import os
try:
    import customtkinter as ctk
    from tkinter import filedialog
    from ui import widgets as W
except Exception:
    ctk = None
    filedialog = None
    W = None

from ui import theme as T
from ui.constants import APP_VERSION
from ui.config import (
    get_default_download_directory,
    set_custom_download_directory,
    get_subtitle_output_mode,
    set_subtitle_output_mode,
    get_desktop_notification_enabled,
    set_desktop_notification_enabled,
    get_notification_sound_enabled,
    set_notification_sound_enabled,
    find_desktop_ffmpeg,
)


class SettingsViewMixin:
    """
    Mixin containing page builder and event handlers for the Settings tab.
    """

    def _build_settings_page(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        self.row_download_dir = W.SettingRow(
            card, "İndirme klasörü", get_default_download_directory(),
            lambda row: W.link(row, "Değiştir", self._browse_global_download_dir)
        )
        self.row_download_dir.grid(row=0, column=0, sticky="ew")

        self.opt_speed_preset = ctk.CTkOptionMenu(
            card,
            values=["🚀 GigaFiber Ultra (64x) - 1000 Mbps & Çok Çekirdekli PC",
                    "⚡ Turbo GigaFiber (32x) - Gigabit & Yüksek Hız (Önerilen)",
                    "⚡ Maksimum Fiber (16x) - Standart Fiber Bağlantı",
                    "⚡ Hızlı (8x) - Standart VDSL / Wi-Fi",
                    "⚡ Dengeli (4x) - Temel / Kararlı Bağlantı"],
            command=self._on_speed_preset_changed, height=1, width=1)
        self.opt_speed_preset.grid_forget()

        speed_row = W.SettingRow(
            card, "İndirme hızı", "Bağlantına göre kanal sayısını ayarlar",
            lambda row: W.Segmented(row, ["Dengeli", "Otomatik", "Turbo"], selected=1,
                                     command=self._on_speed_segment_changed))
        speed_row.grid(row=1, column=0, sticky="ew")
        self.seg_speed = speed_row.control

        sub_mode_row = W.SettingRow(
            card, "Altyazı Çıktı Modu", "İndirilen altyazının saklanma tercihi",
            lambda row: W.Segmented(
                row, ["Göm + SRT Kaydet", "Yalnızca Göm"],
                selected=0 if get_subtitle_output_mode() == "embed_and_keep_srt" else 1,
                command=self._on_subtitle_mode_changed))
        sub_mode_row.grid(row=2, column=0, sticky="ew")
        self.seg_sub_mode = sub_mode_row.control

        notify_row = W.SettingRow(
            card, "Masaüstü bildirimi", "İndirme tamamlandığında bildirim göster",
            lambda row: W.Toggle(row, get_desktop_notification_enabled(), command=self._on_notify_toggle_changed))
        notify_row.grid(row=3, column=0, sticky="ew")
        self.chk_notify = notify_row.control

        sound_row = W.SettingRow(
            card, "Bildirim sesi", "İndirme tamamlandığında kısa bir ses çal",
            lambda row: W.Toggle(row, get_notification_sound_enabled(), command=self._on_sound_toggle_changed))
        sound_row.grid(row=4, column=0, sticky="ew")
        self.chk_sound = sound_row.control

        shutdown_row = W.SettingRow(
            card, "Bitince bilgisayarı kapat", "Tüm indirmeler tamamlanınca",
            lambda row: W.Toggle(row, False))
        shutdown_row.grid(row=5, column=0, sticky="ew")
        self.chk_shutdown = shutdown_row.control

        disk_row = W.SettingRow(
            card, "Disk hijyeni & Geçici dosyalar", "Diskte kalmış yetim ve süresi dolmuş geçici segmentleri temizle",
            lambda row: W.ghost_button(row, "Diski Temizle", self._cleanup_temp_disk_ui), last=True)
        disk_row.grid(row=6, column=0, sticky="ew")

        net = W.Card(parent)
        net.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        net.grid_columnconfigure(0, weight=1)
        W.SettingRow(
            net, "Ağ koruması (DPI)",
            "Engelli veya kısıtlanmış akışlara doğrudan erişim sağlar",
            lambda row: self._make_dpi_badge(row)).grid(row=0, column=0,
                                                        sticky="ew")

        ff_path = find_desktop_ffmpeg()
        ff_ok = ff_path is not None
        ff_desc = f"Konum: {ff_path}" if ff_ok else "Bulunamadı (Gelişmiş remux ve format dönüştürme için gereklidir)"
        W.SettingRow(
            net, "FFmpeg Medya Motoru",
            ff_desc,
            lambda row: W.badge(row, "🚀 Kurulu" if ff_ok else "⚠️ Eksik",
                                color=T.SUCCESS if ff_ok else T.WARNING),
            last=True
        ).grid(row=1, column=0, sticky="ew")

        self.adv_settings = W.Collapsible(parent, "Gelişmiş",
                                          "Ağ koruması · Tarayıcı oturumu · cURL · Kanal sayısı")
        self.adv_settings.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        body = self.adv_settings.body
        W.label(body, "Bu ayarlar ilgili sayfaların Gelişmiş panellerinde de bulunur:",
                size=T.SIZE_SM, weight=600, color=T.TEXT_MUTED).grid(row=0, column=0,
                                                                     sticky="w", pady=(6, 8))
        for row, (text, page) in enumerate(
                [("cURL içe aktarma ve kanal sayısı → Film & Web", "film"),
                 ("Tarayıcı oturumu ve çerez dosyası → Sosyal Medya", "social"),
                 ("Bölüm aralığı → Kuyruk", "queue")], start=1):
            W.link(body, text, lambda p=page: self._show_page(p),
                   color=T.PRIMARY_LIGHT).grid(row=row, column=0, sticky="w", pady=2)

        foot = ctk.CTkFrame(parent, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        W.label(foot, f"Video Downloader Pro v{APP_VERSION}", size=T.SIZE_SM,
                weight=600, color=T.TEXT_DIM).grid(row=0, column=0, padx=(6, 8))
        self.lbl_dpi_state = W.StatusDot(foot, T.SUCCESS, size=6)
        self.lbl_dpi_state.grid(row=0, column=1)

    def _make_dpi_badge(self, parent):
        self.btn_dpi_badge = W.ghost_button(parent, "DPI: Kontrol…", self._toggle_dpi_mode,
                                            icon="shield", height=T.H_BUTTON_SM, width=180)
        return self.btn_dpi_badge

    def _on_speed_segment_changed(self, index, _text):
        """Segment seçimi eski hız ön ayarı handler'ına köprülenir."""
        preset_values = self.opt_speed_preset.cget("values")
        choice = {0: preset_values[3], 1: preset_values[1], 2: preset_values[0]}[index]
        self.opt_speed_preset.set(choice)
        self._on_speed_preset_changed(choice)

    def _on_subtitle_mode_changed(self, index, _text):
        """Altyazı çıktı modu seçimi (Göm + SRT / Yalnızca Göm) kaydedilir."""
        mode = "embed_and_keep_srt" if index == 0 else "embed_only"
        set_subtitle_output_mode(mode)

    def _on_notify_toggle_changed(self):
        """Masaüstü bildirimi tercihi kaydedilir."""
        if hasattr(self, 'chk_notify'):
            set_desktop_notification_enabled(bool(self.chk_notify.get()))

    def _on_sound_toggle_changed(self):
        """Bildirim sesi tercihi kaydedilir."""
        if hasattr(self, 'chk_sound'):
            set_notification_sound_enabled(bool(self.chk_sound.get()))

    def _on_speed_preset_changed(self, choice):
        if "64x" in choice:
            self.slider_threads.set(64)
            self._on_thread_slider_changed(64)
        elif "32x" in choice:
            self.slider_threads.set(32)
            self._on_thread_slider_changed(32)
        elif "16x" in choice:
            self.slider_threads.set(16)
            self._on_thread_slider_changed(16)
        elif "8x" in choice:
            self.slider_threads.set(8)
            self._on_thread_slider_changed(8)
        elif "4x" in choice:
            self.slider_threads.set(4)
            self._on_thread_slider_changed(4)

    def _on_thread_slider_changed(self, value):
        threads = int(value)
        if threads >= 48:
            speed_tag = f"🚀 GigaFiber Ultra ({threads}x)"
        elif threads >= 32:
            speed_tag = f"⚡ Turbo GigaFiber ({threads}x)"
        elif threads >= 16:
            speed_tag = f"⚡ Maksimum Fiber ({threads}x)"
        elif threads >= 8:
            speed_tag = f"⚡ Hızlı ({threads}x)"
        else:
            speed_tag = f"⚡ Dengeli ({threads}x)"
        if hasattr(self, 'lbl_threads'):
            self.lbl_threads.configure(text=f"Hız: {speed_tag}")
        if hasattr(self, 'lbl_top_threads'):
            self.lbl_top_threads.configure(text=speed_tag)

    def _browse_save_path(self):
        current_val = self.entry_output.get().strip() if hasattr(self, 'entry_output') else ""
        initial_dir = os.path.dirname(current_val) if current_val else ""
        if not initial_dir or not os.path.exists(initial_dir):
            initial_dir = get_default_download_directory()

        filename = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile=os.path.basename(current_val) if current_val else "film.mp4",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("Transport Stream", "*.ts"), ("Tüm Dosyalar", "*.*")],
            title="Kayıt Konumunu Seçin"
        )
        if filename:
            chosen_dir = os.path.dirname(filename)
            set_custom_download_directory(chosen_dir)
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, filename)
            if hasattr(self, 'entry_yt_dir'):
                self.entry_yt_dir.delete(0, "end")
                self.entry_yt_dir.insert(0, chosen_dir)
            if hasattr(self, 'lbl_save_hint'):
                self.lbl_save_hint.configure(text=W.elide(os.path.basename(filename), 28))
            if hasattr(self, 'btn_header_folder'):
                self.btn_header_folder.configure(text=f"{W.icon_text('folder')}  {os.path.basename(chosen_dir) or 'VideoDownloaderPro'}")
            if hasattr(self, 'row_download_dir') and hasattr(self.row_download_dir, 'desc'):
                self.row_download_dir.desc.configure(text=chosen_dir)

    def _browse_global_download_dir(self):
        initial_dir = get_default_download_directory()
        d = filedialog.askdirectory(initialdir=initial_dir, title="Varsayılan İndirme Klasörünü Seçin")
        if d:
            set_custom_download_directory(d)
            if hasattr(self, 'entry_output'):
                cur_fname = os.path.basename(self.entry_output.get().strip()) or "film.mp4"
                self.entry_output.delete(0, "end")
                self.entry_output.insert(0, os.path.join(d, cur_fname))
            if hasattr(self, 'entry_yt_dir'):
                self.entry_yt_dir.delete(0, "end")
                self.entry_yt_dir.insert(0, d)
            if hasattr(self, 'btn_header_folder'):
                self.btn_header_folder.configure(text=f"{W.icon_text('folder')}  {os.path.basename(d) or 'VideoDownloaderPro'}")
            if hasattr(self, 'row_download_dir') and hasattr(self.row_download_dir, 'desc'):
                self.row_download_dir.desc.configure(text=d)
            if hasattr(self, 'lbl_save_hint') and hasattr(self, 'entry_output'):
                self.lbl_save_hint.configure(text=W.elide(os.path.basename(self.entry_output.get().strip()), 28))
