# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Converter Page View Mixin.
Builds the audio extraction dropzone, output format pills, and conversion log panel.
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


class ConverterViewMixin:
    """
    Mixin containing page builder for the Converter & Audio Extraction tab.
    """

    def _build_converter_page(self, parent):
        drop = ctk.CTkFrame(parent, fg_color=T.BG_SIDEBAR, corner_radius=T.R_CARD,
                            border_width=2, border_color=T.DROPZONE_BORDER, height=150)
        drop.grid(row=0, column=0, sticky="ew")
        drop.grid_propagate(False)
        drop.grid_columnconfigure(0, weight=1)
        drop.grid_rowconfigure(0, weight=1)

        inner = ctk.CTkFrame(drop, fg_color="transparent")
        inner.grid(row=0, column=0)
        inner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(inner, text=W.icon_text("music"), font=F.icon(20),
                     text_color=T.PURPLE_LIGHT, fg_color=T.PURPLE_FILL,
                     corner_radius=12, width=40, height=40).grid(row=0, column=0)
        W.label(inner, "Video veya ses dosyasını seç", size=T.SIZE_MD, weight=800,
                anchor="center").grid(row=1, column=0, pady=(10, 0))

        hint = ctk.CTkFrame(inner, fg_color="transparent")
        hint.grid(row=2, column=0, pady=(6, 0))
        W.label(hint, "mp4, mkv, ts, webm · veya", size=T.SIZE_SM, weight=600,
                color=T.TEXT_MUTED).grid(row=0, column=0)
        W.link(hint, " dosya seç", self._browse_conv_input,
               color=T.PURPLE_LIGHT).grid(row=0, column=1)
        W.bind_click(drop, self._browse_conv_input)

        self.entry_conv_in = W.entry(parent, "Dönüştürülecek dosya yolu…",
                                     height=T.H_BUTTON_SM)
        self.entry_conv_in.grid(row=1, column=0, sticky="ew", pady=(14, 0))

        card = W.Card(parent)
        card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        W.section_label(card, "Çıktı biçimi").grid(row=0, column=0, sticky="w",
                                                   padx=20, pady=(18, 12))
        self.opt_conv_fmt = W.OptionPills(
            card,
            values=["MP3 (320 kbps Yüksek)", "MP3 (192 kbps Standart)", "WAV (Kayıpsız)"],
            accent=T.PURPLE, fill=T.PURPLE_FILL, ink=T.PURPLE_LIGHT)
        self.opt_conv_fmt.grid(row=1, column=0, sticky="w", padx=20)

        out = ctk.CTkFrame(card, fg_color="transparent")
        out.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 0))
        out.grid_columnconfigure(0, weight=1)
        self.entry_conv_out = W.entry(out, "Çıktı ses dosyası…", height=T.H_BUTTON_SM)
        self.entry_conv_out.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        W.ghost_button(out, "Gözat", self._browse_conv_output, icon="folder_open",
                       height=T.H_BUTTON_SM, width=110).grid(row=0, column=1)

        W.purple_button(card, "Dönüştür", self._start_convert_threaded, icon="convert",
                        width=170).grid(row=3, column=0, sticky="w", padx=20, pady=(16, 20))

        self.log_conv = W.Collapsible(parent, "İşlem günlüğü", "0 satır")
        self.log_conv.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.txt_conv_logs = ctk.CTkTextbox(self.log_conv.body, height=140,
                                            font=F.mono(T.SIZE_SM, 500),
                                            fg_color=T.BG_APP, corner_radius=T.R_TILE,
                                            border_width=0, text_color=T.TEXT_MUTED)
        self.txt_conv_logs.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.txt_conv_logs.configure(state="disabled")
