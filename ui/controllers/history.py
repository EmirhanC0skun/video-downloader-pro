# -*- coding: utf-8 -*-
"""
Video Downloader Pro — History & File Execution Controller Mixin.
Handles history deletion, re-downloading, clipboard copies, and detached process launches.
"""

import os
import sys
import threading
import subprocess
try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None
    messagebox = None

from logger import get_logger
from history import clear_all_history, delete_history_entry
from ui import theme as T
from ui.config import get_default_download_directory

logger = get_logger("ui.controllers.history")


class HistoryControllerMixin:
    """
    Mixin managing download history items, file open operations, and context menu actions.
    """

    def _show_history_context_menu(self, event, item):
        """Geçmiş kaydına sağ tıklandığında modern koyu tema sağ tık menüsünü açar."""
        if not item or tk is None:
            return

        item_id = item.get("id")
        path = item.get("file_path", "")
        url = item.get("source_url", "")

        menu = tk.Menu(self, tearoff=0, bg="#1a1d24", fg="#ffffff", activebackground="#00adb5", activeforeground="#ffffff", relief="flat", bd=1)

        menu.add_command(label="▶️ Oynat", command=lambda: self._safe_open_file(path))
        if url:
            menu.add_command(label="🔄 Tekrar İndir", command=lambda: self._repeat_download_from_history(item))
            menu.add_command(label="📋 Linki Kopyala", command=lambda: self._copy_to_clipboard(url))
        if path:
            menu.add_command(label="📂 Dosya Konumunu Aç", command=lambda: self._safe_open_dir(path))
        menu.add_separator()
        if item_id is not None:
            menu.add_command(label="🗑️ Listeden Sil", command=lambda: self._delete_single_history_entry_ui(item_id))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_single_history_entry_ui(self, entry_id):
        """Tekil geçmiş kaydını veritabanından siler ve geçmiş listesini anında yeniler."""
        try:
            delete_history_entry(entry_id)
            self._refresh_history_ui()
            self._set_status("Geçmiş Kaydı Silindi", color=T.PRIMARY_LIGHT)
        except Exception:
            logger.debug("[ui.controllers.history] _delete_single_history_entry_ui istisnası", exc_info=True)

    def _copy_to_clipboard(self, text):
        """Metni panoya kopyalar."""
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("Link Panoya Kopyalandı", color=T.SUCCESS)
        except Exception:
            logger.debug("[ui.controllers.history] _copy_to_clipboard istisnası", exc_info=True)

    def _repeat_download_from_history(self, item):
        url = item.get("source_url")
        if not url:
            return
        if any(d in url.lower() for d in ("youtube.com", "youtu.be", "instagram.com", "tiktok.com", "twitter.com", "x.com")):
            self._show_page("social")
            self.entry_yt_url.delete(0, "end")
            self.entry_yt_url.insert(0, url)
            self._resolve_youtube_url_threaded()
        else:
            self._show_page("film")
            self.entry_film_page.delete(0, "end")
            self.entry_film_page.insert(0, url)
            self._resolve_film_threaded()

    def _clear_history_ui(self):
        if messagebox and messagebox.askyesno("Geçmişi Temizle", "Tüm indirme geçmişi silinsin mi?"):
            clear_all_history()
            self._refresh_history_ui()

    def _safe_open_file(self, path):
        if path and os.path.exists(path):
            self._open_path_with_default_app(path)
        else:
            if messagebox:
                messagebox.showwarning("Dosya Bulunamadı", f"Dosya taşınmış veya silinmiş:\n{path}")

    def _safe_open_dir(self, path):
        folder = os.path.dirname(path) if path else ""
        if folder and os.path.exists(folder):
            self._reveal_in_file_manager(folder)
        else:
            self._reveal_in_file_manager(get_default_download_directory())

    @staticmethod
    def _open_path_with_default_app(path):
        """
        Dosyayı harici oynatıcıda (VLC / varsayılan medya oynatıcı) açar.
        FAZ 1 (Detached Process): Ana GUI'nin kapanmasını veya oynatıcı kapanana
        kadar donmasını önlemek için süreci bağımsız daemon olarak başlatır.
        """
        if not path or not os.path.exists(path):
            return
        def _runner():
            try:
                if sys.platform == "win32":
                    norm_path = os.path.normpath(path)
                    # ShellExecute tabanli os.startfile yolu tek bir dosya yolu
                    # olarak ele alir. `cmd /c start` ise bosluk, &, # ve Unicode
                    # karakterleri ikinci kez komut satiri olarak ayrıştırarak
                    # mevcut dosyalarda bile "Windows bulamıyor" hatasi uretebilir.
                    os.startfile(norm_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(
                        ["open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True
                    )
                else:
                    subprocess.Popen(
                        ["xdg-open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True
                    )
            except Exception:
                logger.warning("Dosya bağımsız süreçte açılamadı: %s", path, exc_info=True)
        threading.Thread(target=_runner, daemon=True).start()

    @staticmethod
    def _reveal_in_file_manager(folder):
        """Platformdan bağımsız klasör açma (os.startfile yalnızca Windows'ta vardır)."""
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            logger.warning("Klasor acilamadi: %s", folder, exc_info=True)
