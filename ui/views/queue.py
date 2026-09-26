# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Queue Page View Mixin.
Builds the batch queue page, controls, and renders dynamic queue item cards.
"""

try:
    import customtkinter as ctk
    from ui import widgets as W
except Exception:
    ctk = None
    W = None

from ui import theme as T


class QueueViewMixin:
    """
    Mixin containing page builder and dynamic row renderers for the Queue tab.
    """

    def _build_queue_page(self, parent):
        parent.grid_rowconfigure(2, weight=1)

        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        row.grid_columnconfigure(0, weight=1)
        self.entry_queue_url = W.entry(row, "Dizi sayfası veya bölüm linki…",
                                       height=T.H_BUTTON_SM + 2)
        self.entry_queue_url.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        W.ghost_button(row, "Yapıştır", self._paste_queue_url, icon="paste",
                       height=T.H_BUTTON_SM + 2, width=110).grid(row=0, column=1, padx=(0, 8))
        W.primary_button(row, "Tüm bölümleri tara",
                         lambda: self._scan_and_add_series(all_episodes=True),
                         height=T.H_BUTTON_SM + 2, width=180).grid(row=0, column=2, padx=(0, 8))
        W.ghost_button(row, "Tek ekle", self._add_to_queue, height=T.H_BUTTON_SM + 2,
                       width=110).grid(row=0, column=3)

        hint = ctk.CTkFrame(card, fg_color="transparent")
        hint.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        hint.grid_columnconfigure(1, weight=1)
        W.label(hint, "Sezon ve bölümler otomatik bulunur. Belirli aralık için",
                size=T.SIZE_SM, weight=600, color=T.TEXT_DIM).grid(row=0, column=0)
        W.link(hint, " Gelişmiş", lambda: self.adv_queue.toggle()).grid(row=0, column=1,
                                                                       sticky="w")

        self.adv_queue = W.Collapsible(parent, "Gelişmiş", "bölüm aralığı")
        self.adv_queue.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        body = self.adv_queue.body
        W.label(body, "Bölüm aralığı", size=T.SIZE_SM, weight=700,
                color=T.TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=(6, 6))
        span = ctk.CTkFrame(body, fg_color="transparent")
        span.grid(row=1, column=0, sticky="w")
        self.entry_start_ep = W.entry(span, height=T.H_BUTTON_SM, width=60)
        self.entry_start_ep.insert(0, "1")
        self.entry_start_ep.grid(row=0, column=0)
        W.label(span, "—", color=T.TEXT_DIM).grid(row=0, column=1, padx=8)
        self.entry_end_ep = W.entry(span, height=T.H_BUTTON_SM, width=60)
        self.entry_end_ep.insert(0, "10")
        self.entry_end_ep.grid(row=0, column=2, padx=(0, 12))
        W.ghost_button(span, "Aralığı ekle", self._add_range_to_queue,
                       height=T.H_BUTTON_SM, width=140).grid(row=0, column=3)

        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=2, column=0, sticky="ew", padx=4, pady=(18, 8))
        head.grid_columnconfigure(0, weight=1)
        self.lbl_queue_count = W.section_label(head, "Kuyruk")
        self.lbl_queue_count.grid(row=0, column=0, sticky="w")
        W.link(head, "Temizle", self._clear_queue, color=T.DANGER).grid(row=0, column=1)

        self.queue_list_frame = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=T.BG_ELEVATED,
            scrollbar_button_hover_color=T.BG_HOVER)
        self.queue_list_frame.grid(row=3, column=0, sticky="nsew")
        self.queue_list_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        foot = ctk.CTkFrame(parent, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        foot.grid_columnconfigure(2, weight=1)
        self.btn_q_start = W.success_button(foot, "Kuyruğu başlat",
                                            self._start_queue_processing, icon="play",
                                            height=T.H_BUTTON_SM + 2, width=190)
        self.btn_q_start.grid(row=0, column=0, padx=(0, 8))
        self.btn_q_stop = W.ghost_button(foot, "Duraklat", self._stop_queue_processing,
                                         icon="pause", height=T.H_BUTTON_SM + 2, width=140)
        self.btn_q_stop.grid(row=0, column=1)
        W.label(foot, "Sırayla, tek tek indirilir", size=T.SIZE_SM, weight=600,
                color=T.TEXT_MUTED, anchor="e").grid(row=0, column=2, sticky="e")

        self._refresh_queue_ui()

    def _refresh_queue_ui(self):
        self.queue_row_widgets = {}
        if hasattr(self, "lbl_queue_count"):
            count = len(self.download_queue)
            self.lbl_queue_count.configure(
                text=W.upper_tr(f"Kuyruk · {count}") if count else W.upper_tr("Kuyruk"))
        if hasattr(self, "nav"):
            pending = sum(1 for it in self.download_queue
                          if str(it.get("status", "")).lower() not in ("tamamlandı", "tamamlandi"))
            self.nav["queue"].set_badge(pending)
        for widget in self.queue_list_frame.winfo_children():
            widget.destroy()

        if not self.download_queue:
            lbl = ctk.CTkLabel(self.queue_list_frame, text="Kuyruk boş. Yukarıdan veya Film sekmesinden '➕ Sıraya Ekle' ile ekleyebilirsiniz.", font=ctk.CTkFont(size=11), text_color=T.TEXT_MUTED)
            lbl.pack(pady=20)
            return

        for idx, item in enumerate(self.download_queue):
            item_id = item["id"]
            row = ctk.CTkFrame(self.queue_list_frame, fg_color=T.BG_ELEVATED, height=38, corner_radius=6, border_color=T.BORDER, border_width=1)
            row.pack(fill="x", pady=2, padx=4)
            row.grid_columnconfigure(1, weight=1)

            lbl_num = ctk.CTkLabel(row, text=f"#{idx+1}", font=ctk.CTkFont(size=11, weight="bold"), text_color=T.TEXT_MUTED, width=28)
            lbl_num.grid(row=0, column=0, padx=(6, 2), pady=4)

            lbl_name = ctk.CTkLabel(row, text=f"{item['title']} - {item['url'][:36]}...", font=ctk.CTkFont(size=11), text_color=T.TEXT, anchor="w")
            lbl_name.grid(row=0, column=1, sticky="w", padx=6, pady=4)

            pbar = ctk.CTkProgressBar(row, width=90, height=8, corner_radius=4, fg_color=T.BG_CARD, progress_color=T.PRIMARY)
            pbar.set(item.get("progress", 0.0))
            pbar.grid(row=0, column=2, padx=4, pady=4)

            status_color = T.SUCCESS if "Tamamlandı" in item["status"] else (T.WARNING if "İndiriliyor" in item["status"] else (T.DANGER if "Hata" in item["status"] or "İptal" in item["status"] else T.TEXT_MUTED))
            lbl_st = ctk.CTkLabel(row, text=item["status"], font=ctk.CTkFont(size=10, weight="bold"), text_color=status_color, width=155, anchor="e")
            lbl_st.grid(row=0, column=3, padx=(4, 6), pady=4)

            # Hızlı Tekli Silme / Kaldırma Butonu
            btn_del = ctk.CTkButton(
                row,
                text="✕",
                width=24,
                height=24,
                corner_radius=4,
                fg_color="#2b1b22",
                hover_color="#b00020",
                text_color="#ff8080",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda i=item_id: self._remove_queue_item(i)
            )
            btn_del.grid(row=0, column=4, padx=(2, 6), pady=4)

            # Sağ tık menüsü bağlama (Tüm bileşenlere)
            for widget in [row, lbl_num, lbl_name, pbar, lbl_st]:
                widget.bind("<Button-3>", lambda e, i=item_id: self._show_queue_context_menu(e, i))
                widget.bind("<Button-2>", lambda e, i=item_id: self._show_queue_context_menu(e, i))

            self.queue_row_widgets[item_id] = {
                "row": row,
                "url": item["url"],
                "lbl_name": lbl_name,
                "pbar": pbar,
                "lbl_st": lbl_st,
                "btn_del": btn_del
            }
