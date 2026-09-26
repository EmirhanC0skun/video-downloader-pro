# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Library / History Page View Mixin.
Builds the downloads library page, media type filtering, metadata chips, and list rows.
"""

import os
try:
    import customtkinter as ctk
    from ui import widgets as W
except Exception:
    ctk = None
    W = None

from logger import get_logger
from history import load_history
from ui import theme as T
from ui.config import get_default_download_directory

logger = get_logger("ui.views.library")


class LibraryViewMixin:
    """
    Mixin containing page builder and history row renderers for the Library & Downloads tab.
    """

    AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus")

    def _build_library_page(self, parent):
        parent.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self.entry_history_search = W.entry(top, "Ara: film, dizi, müzik…",
                                            height=T.H_BUTTON_SM + 2)
        self.entry_history_search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry_history_search.bind("<KeyRelease>", lambda e: self._refresh_history_ui())
        self.seg_library = W.Segmented(top, ["Tümü", "Video", "Ses"],
                                       command=lambda *_: self._refresh_history_ui(),
                                       fill=T.BG_CARD)
        self.seg_library.grid(row=0, column=1, padx=(0, 8))
        W.ghost_button(top, "Temizle", self._clear_history_ui, icon="delete",
                       height=T.H_BUTTON_SM + 2, width=120).grid(row=0, column=2)

        self.lbl_library_summary = W.label(parent, "0 dosya", size=T.SIZE_SM, weight=700,
                                           color=T.TEXT_MUTED)
        self.lbl_library_summary.grid(row=1, column=0, sticky="w", padx=4, pady=(14, 8))

        self.history_list_frame = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=T.BG_ELEVATED,
            scrollbar_button_hover_color=T.BG_HOVER)
        self.history_list_frame.grid(row=2, column=0, sticky="nsew")
        self.history_list_frame.grid_columnconfigure(0, weight=1)

        self._refresh_history_ui()

    def _history_is_audio(self, item):
        """Kayıt ses mi video mu — kütüphane filtresi buna göre çalışır."""
        path = str(item.get("file_path", "")).lower()
        media = str(item.get("media_type", "")).lower()
        return path.endswith(self.AUDIO_EXTENSIONS) or "ses" in media or "mp3" in media

    def _set_film_meta(self, data):
        """Çözümlenen medyanın mono meta rozetlerini yeniden kurar."""
        for widget in self.resolved_meta_frame.winfo_children():
            widget.destroy()

        chips = []
        qualities = data.get("qualities") or []
        if qualities:
            chips.append(str(qualities[0].get("label", "")).lstrip("🌟🎬📺📱⚡ ").strip())
        tracks = data.get("audio_tracks") or []
        if tracks:
            chips.append(f"{len(tracks)} ses kanalı")
        subs = data.get("subtitles") or []
        if subs:
            s_lbl = subs[0].get("name") or subs[0].get("label") or "Türkçe"
            chips.append(f"📝 {s_lbl} Altyazı")
        if data.get("total_segments"):
            chips.append(f"{data['total_segments']} parça")

        for column, text in enumerate(c for c in chips if c):
            W.MetaChip(self.resolved_meta_frame, text).grid(row=0, column=column,
                                                            padx=(0, 6))

        save_path = self.entry_output.get().strip()
        if save_path:
            self.lbl_save_hint.configure(text=W.elide(os.path.basename(save_path), 28))

    def _refresh_history_ui(self):
        """`İndirilenler` sayfasını tasarımın kütüphane satırlarıyla kurar."""
        try:
            self._refresh_recent_list()
        except Exception:
            logger.debug("[ui.views.library] _refresh_recent_list istisnası", exc_info=True)

        if not hasattr(self, "history_list_frame"):
            return
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()

        items = load_history()
        query = (self.entry_history_search.get().strip().lower()
                 if hasattr(self, "entry_history_search") else "")
        if query:
            items = [
                it for it in items
                if query in str(it.get("title", "")).lower()
                or query in str(it.get("source_url", "")).lower()
                or query in str(it.get("file_path", "")).lower()
                or query in str(it.get("media_type", "")).lower()
            ]

        kind = self.seg_library.value() if hasattr(self, "seg_library") else "Tümü"
        if kind == "Ses":
            items = [it for it in items if self._history_is_audio(it)]
        elif kind == "Video":
            items = [it for it in items if not self._history_is_audio(it)]

        total_mb = sum(float(it.get("size_mb", 0) or 0) for it in items)
        size_text = (f"{total_mb / 1024:.1f} GB" if total_mb >= 1024
                     else f"{total_mb:.0f} MB")
        if hasattr(self, "lbl_library_summary"):
            download_dir = get_default_download_directory()
            folder_name = os.path.basename(os.path.normpath(download_dir)) or "VideoDownloaderPro"
            self.lbl_library_summary.configure(
                text=(
                    f"{len(items)} dosya · {size_text} · {folder_name} klasörüne kaydedildi"
                    if items
                    else f"0 dosya · İndirilenler {folder_name} klasörüne kaydedilir"
                )
            )

        if not items:
            empty = (f"'{query}' ile eşleşen kayıt yok." if query
                     else "Henüz indirme geçmişi bulunmuyor.")
            W.label(self.history_list_frame, empty, size=T.SIZE_BASE, weight=600,
                    color=T.TEXT_MUTED, anchor="center").grid(row=0, column=0, pady=30)
            return

        for row, item in enumerate(items):
            self._build_history_row(self.history_list_frame, item).grid(
                row=row, column=0, sticky="ew", pady=(0, 8))

    def _build_history_row(self, parent, item):
        audio = self._history_is_audio(item)
        path = item.get("file_path", "")
        item_id = item.get("id")
        meta = " · ".join(part for part in (
            f"{item.get('size_mb', 0)} MB",
            str(item.get("timestamp", "")),
            str(item.get("media_type", "")),
        ) if part.strip(" ·"))

        actions = [("Oynat", lambda p=path: self._safe_open_file(p))]
        if item.get("source_url"):
            actions.append(("Tekrar indir",
                            lambda it=item: self._repeat_download_from_history(it)))
        actions.append(("Konum", lambda p=path: self._safe_open_dir(p)))
        if item_id is not None:
            actions.append(("Sil", lambda i_id=item_id: self._delete_single_history_entry_ui(i_id)))

        row = W.ListRow(
            parent,
            item.get("title", "İsimsiz"),
            meta,
            icon_name="music" if audio else "film",
            icon_fill=T.ICON_FILL_AUDIO if audio else T.ICON_FILL_VIDEO,
            icon_color=T.PURPLE_LIGHT if audio else T.PRIMARY_LIGHT,
            actions=actions,
        )

        for w in (row, getattr(row, "_title", None), getattr(row, "_meta", None)):
            if w:
                try:
                    w.bind("<Button-3>", lambda e, it=item: self._show_history_context_menu(e, it))
                    w.bind("<Button-2>", lambda e, it=item: self._show_history_context_menu(e, it))
                except Exception:
                    logger.debug("[ui.views.library] bind context menu istisnası", exc_info=True)

        return row

    def _refresh_recent_list(self, limit=3):
        """Film sayfasındaki `Son İndirilenler` şeridini tazeler."""
        if not hasattr(self, "recent_list_frame"):
            return
        for widget in self.recent_list_frame.winfo_children():
            widget.destroy()

        items = load_history()[:limit]
        if not items:
            # Baslik altini bos birakmak, sayfada aciklanmayan bir boslugu
            # birakiyordu; kutuphane sayfasi gibi burada da ne olacagi soylenir.
            W.label(self.recent_list_frame,
                    "Henüz indirme yok. İlk indirmen bittiğinde burada görünecek.",
                    size=T.SIZE_SM, weight=600, color=T.TEXT_MUTED).grid(
                row=0, column=0, sticky="w", padx=4, pady=(2, 6))
            return

        for row, item in enumerate(items):
            self._build_history_row(self.recent_list_frame, item).grid(
                row=row, column=0, sticky="ew", pady=(0, 8))
