# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Modal Dialogs View Mixin.
Provides the rich resolution completion modal and the crash recovery inspection modal.
"""

import os
try:
    import customtkinter as ctk
    from tkinter import messagebox
except Exception:
    ctk = None
    messagebox = None

from logger import get_logger
from engine import cleanup_filesystem_path
from ui import theme as T

logger = get_logger("ui.views.modals")


class ModalsMixin:
    """
    Mixin containing popup dialogs and modal interactions.
    """

    def _show_resolution_modal(self, title, media_type, quality_summary, size_summary, audio_summary, on_download, on_queue, subtitle_summary=None):
        """
        Çözümleme bittiğinde ekrana zengin, modern ve interaktif CustomTkinter modal penceresi açar.
        """
        try:
            if hasattr(self, "state") and self.state() == "iconic":
                try:
                    self.deiconify()
                    self.lift()
                except Exception:
                    logger.debug("[ui.views.modals] modal deiconify istisnasi", exc_info=True)

            modal = ctk.CTkToplevel(self)
            modal.title("🎬 Medya Çözümlendi")
            modal_h = 420 if subtitle_summary else 380
            modal.geometry(f"500x{modal_h}")
            modal.resizable(False, False)
            modal.configure(fg_color="#0F172A")
            modal.transient(self)

            def _safe_close():
                try:
                    modal.grab_release()
                except Exception:
                    logger.debug("[ui.views.modals] modal grab_release istisnasi", exc_info=True)
                try:
                    modal.destroy()
                except Exception:
                    logger.debug("[ui.views.modals] modal destroy istisnasi", exc_info=True)

            modal.protocol("WM_DELETE_WINDOW", _safe_close)
            modal.bind("<Escape>", lambda _e: _safe_close())

            try:
                modal.grab_set()
            except Exception:
                logger.debug("[ui.views.modals] modal grab_set istisnasi", exc_info=True)

            self.update_idletasks()
            x = self.winfo_x() + max(0, (self.winfo_width() // 2) - 250)
            y = self.winfo_y() + max(0, (self.winfo_height() // 2) - (modal_h // 2))
            modal.geometry(f"+{x}+{y}")

            header_frame = ctk.CTkFrame(modal, fg_color="transparent")
            header_frame.pack(fill="x", padx=20, pady=(20, 10))

            badge = ctk.CTkLabel(
                header_frame,
                text="  ● ÇÖZÜMLEME BAŞARILI  ",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=T.SUCCESS,
                fg_color="#064E3B",
                corner_radius=6
            )
            badge.pack(anchor="w", pady=(0, 6))

            lbl_title = ctk.CTkLabel(
                header_frame,
                text=title,
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=T.PRIMARY_LIGHT,
                wraplength=450,
                justify="left"
            )
            lbl_title.pack(anchor="w")

            card = ctk.CTkFrame(modal, fg_color=T.BG_CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
            card.pack(fill="x", padx=20, pady=10)

            r1 = ctk.CTkFrame(card, fg_color="transparent")
            r1.pack(fill="x", padx=14, pady=(10, 5))
            ctk.CTkLabel(r1, text="🌟 Algılanan Kalite:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(r1, text=f" {quality_summary}", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT).pack(side="left")

            r2 = ctk.CTkFrame(card, fg_color="transparent")
            r2.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(r2, text="📦 Boyut / Parça:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(r2, text=f" {size_summary}", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.WARNING).pack(side="left")

            r3 = ctk.CTkFrame(card, fg_color="transparent")
            r3.pack(fill="x", padx=14, pady=(5, 5 if subtitle_summary else 10))
            ctk.CTkLabel(r3, text="🔊 Ses Kanalları:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(r3, text=f" {audio_summary}", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT).pack(side="left")

            if subtitle_summary:
                r4 = ctk.CTkFrame(card, fg_color="transparent")
                r4.pack(fill="x", padx=14, pady=(0, 10))
                ctk.CTkLabel(r4, text="📝 Altyazı:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
                ctk.CTkLabel(r4, text=f" {subtitle_summary}", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.SUCCESS).pack(side="left")

            btn_frame = ctk.CTkFrame(modal, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(15, 20))

            def on_down_click():
                _safe_close()
                if on_download:
                    on_download()

            def on_q_click():
                _safe_close()
                if on_queue:
                    on_queue()

            def on_close_click():
                _safe_close()

            btn_close = ctk.CTkButton(
                btn_frame,
                text="⚙️ Detayları Seç",
                font=ctk.CTkFont(size=11, weight="bold"),
                width=110,
                height=36,
                fg_color=T.BORDER,
                hover_color="#475569",
                command=on_close_click
            )
            btn_close.pack(side="left", padx=(0, 6))

            btn_q = ctk.CTkButton(
                btn_frame,
                text="📋 Kuyruğa Ekle",
                font=ctk.CTkFont(size=11, weight="bold"),
                width=120,
                height=36,
                fg_color=T.PRIMARY,
                hover_color=T.PRIMARY_HOVER,
                command=on_q_click
            )
            btn_q.pack(side="left", padx=4)

            btn_down = ctk.CTkButton(
                btn_frame,
                text="🚀 Hemen İndir",
                font=ctk.CTkFont(size=12, weight="bold"),
                height=36,
                fg_color=T.SUCCESS,
                hover_color=T.SUCCESS_HOVER,
                command=on_down_click
            )
            btn_down.pack(side="right", fill="x", expand=True, padx=(6, 0))

        except Exception as ex:
            if hasattr(self, "_log"):
                self._log(f"[!] Modal pencere uyarısı: {ex}")

    def _show_recovery_modal(self, candidates):
        """Yarım kalan indirmeleri kullanıcıya şık bir bildirim kartı / diyalog ile sunar."""
        if not candidates or ctk is None:
            return

        candidate = candidates[0]
        c_title = candidate.get("title", "Bilinmeyen Medya")
        c_down = candidate.get("downloaded_segments", 0)
        c_tot = candidate.get("total_segments", 0)
        c_size_mb = candidate.get("size_mb", 0.0)
        c_temp = candidate.get("temp_dir", "")

        try:
            if hasattr(self, 'state') and self.state() == "iconic":
                try:
                    self.deiconify()
                    self.lift()
                except Exception:
                    logger.debug("[ui.views.modals] recovery modal deiconify istisnasi", exc_info=True)

            modal = ctk.CTkToplevel(self)
            modal.title("⚠️ Yarım Kalan İndirme Bulundu")
            modal.geometry("520x340")
            modal.resizable(False, False)
            modal.configure(fg_color="#0F172A")
            modal.transient(self)

            def _safe_close():
                try:
                    modal.grab_release()
                except Exception:
                    logger.debug("[ui.views.modals] recovery modal grab_release istisnasi", exc_info=True)
                try:
                    modal.destroy()
                except Exception:
                    logger.debug("[ui.views.modals] recovery modal destroy istisnasi", exc_info=True)

            modal.protocol("WM_DELETE_WINDOW", _safe_close)
            modal.bind("<Escape>", lambda _e: _safe_close())

            try:
                modal.grab_set()
            except Exception:
                logger.debug("[ui.views.modals] recovery modal grab_set istisnasi", exc_info=True)

            self.update_idletasks()
            x = self.winfo_x() + max(0, (self.winfo_width() // 2) - 260)
            y = self.winfo_y() + max(0, (self.winfo_height() // 2) - 170)
            modal.geometry(f"+{x}+{y}")

            header_frame = ctk.CTkFrame(modal, fg_color="transparent")
            header_frame.pack(fill="x", padx=20, pady=(20, 8))

            badge = ctk.CTkLabel(
                header_frame,
                text="  ⚠️ YARIM KALAN İNDİRME BULUNDU  ",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=T.WARNING,
                fg_color="#451A03",
                corner_radius=6
            )
            badge.pack(anchor="w", pady=(0, 6))

            lbl_title = ctk.CTkLabel(
                header_frame,
                text=c_title,
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=T.PRIMARY_LIGHT,
                wraplength=470,
                justify="left"
            )
            lbl_title.pack(anchor="w")

            card = ctk.CTkFrame(modal, fg_color=T.BG_CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
            card.pack(fill="x", padx=20, pady=12)

            r1 = ctk.CTkFrame(card, fg_color="transparent")
            r1.pack(fill="x", padx=14, pady=(12, 6))
            ctk.CTkLabel(r1, text="📊 İlerleme Durumu:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(r1, text=f" {c_down} / {c_tot} segment indirildi ({c_size_mb:.1f} MB diskte)", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT).pack(side="left")

            r2 = ctk.CTkFrame(card, fg_color="transparent")
            r2.pack(fill="x", padx=14, pady=(0, 12))
            ctk.CTkLabel(r2, text="ℹ️ Bilgi:", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(r2, text=" Önceki oturum aniden kapandığı için inen parçalar korundu.", font=ctk.CTkFont(size=12), text_color=T.TEXT_MUTED).pack(side="left")

            btn_frame = ctk.CTkFrame(modal, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(10, 16))

            def _on_resume():
                _safe_close()
                self._resume_incomplete_candidate(candidate)

            def _on_clean():
                _safe_close()
                if c_temp and os.path.exists(c_temp):
                    cleanup_filesystem_path(c_temp)
                    self._log(f"[✓] Temizlendi: {c_title} ({c_size_mb:.1f} MB geçici dosya silindi)")
                    self._set_status("Temizlendi", color=T.SUCCESS, detail=f"{c_size_mb:.1f} MB boşaltıldı")
                    if messagebox:
                        messagebox.showinfo("Disk Temizlendi", f"'{c_title}' için ayrılan {c_size_mb:.1f} MB geçici alan başarıyla temizlendi.")
                remaining = candidates[1:]
                if remaining:
                    self.after(300, lambda: self._show_recovery_modal(remaining))

            btn_clean = ctk.CTkButton(
                btn_frame,
                text="🗑️ Diski Temizle / İptal",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#334155",
                hover_color=T.DANGER,
                text_color="#FFFFFF",
                height=38,
                corner_radius=8,
                command=_on_clean
            )
            btn_clean.pack(side="left", fill="x", expand=True, padx=(0, 6))

            btn_resume = ctk.CTkButton(
                btn_frame,
                text="▶ Devam Et",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=T.PRIMARY,
                hover_color=T.PRIMARY_HOVER,
                text_color="#FFFFFF",
                height=38,
                corner_radius=8,
                command=_on_resume
            )
            btn_resume.pack(side="left", fill="x", expand=True, padx=(6, 0))

        except Exception as e:
            logger.debug(f"[ui.views.modals] Recovery modal error: {e}", exc_info=True)
