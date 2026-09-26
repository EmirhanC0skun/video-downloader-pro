# -*- coding: utf-8 -*-
"""
Video Downloader Pro — DPI Controller Mixin.
Controls GoodbyeDPI background process monitor, mode detection, and UI switching.
"""

import os
import sys
import time
import threading
import subprocess

try:
    from tkinter import messagebox
except Exception:
    messagebox = None

from logger import get_logger
from ui import theme as T
from ui.config import (
    find_goodbyedpi_dir,
    load_user_config,
    DEFAULT_AGGRESSIVE_DPI_DOMAINS,
    CONFIG_FILE,
)

logger = get_logger("ui.controllers.dpi")


class DPIControllerMixin:
    """
    Mixin managing GoodbyeDPI monitor, mode detection, and toggle actions.
    """

    def _start_dpi_monitor(self):
        def monitor_loop():
            while True:
                try:
                    mode = self._detect_dpi_mode()
                    self.after(0, lambda m=mode: self._update_dpi_ui(m))
                except Exception:
                    logger.debug("[ui.controllers.dpi] monitor_loop() sessiz istisna yutuldu", exc_info=True)
                time.sleep(5.0)

        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()

    def _is_goodbyedpi_running(self):
        try:
            import ctypes
            from ctypes import wintypes
            TH32CS_SNAPPROCESS = 0x00000002

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)
                ]

            hSnapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if hSnapshot == -1 or hSnapshot == 0xFFFFFFFF:
                return False
            pe32 = PROCESSENTRY32()
            pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
            running = False
            try:
                if ctypes.windll.kernel32.Process32First(hSnapshot, ctypes.byref(pe32)):
                    while True:
                        if pe32.szExeFile.lower() == b"goodbyedpi.exe":
                            running = True
                            break
                        if not ctypes.windll.kernel32.Process32Next(hSnapshot, ctypes.byref(pe32)):
                            break
            finally:
                ctypes.windll.kernel32.CloseHandle(hSnapshot)
            return running
        except Exception:
            return False

    def _detect_dpi_mode(self):
        if not self._is_goodbyedpi_running():
            return 0

        gd_dir = find_goodbyedpi_dir()
        if not gd_dir:
            return 1

        ini_path = os.path.join(gd_dir, "GoodbyeDPI_Tray.ini")
        if os.path.exists(ini_path):
            try:
                with open(ini_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "CurrentMode" in line:
                            val = line.split("=")[-1].strip()
                            return int(val)
            except Exception:
                logger.debug("[ui.controllers.dpi] _detect_dpi_mode() sessiz istisna yutuldu", exc_info=True)
        return 2

    def _update_dpi_ui(self, mode):
        self.current_dpi_mode = mode
        badge = getattr(self, "btn_dpi_badge", None)
        if badge is None:
            return
        if mode == 2:
            badge.configure(
                text="🚀 DPI: Agresif Mod",
                text_color="#10B981"
            )
        elif mode == 1:
            badge.configure(
                text="⚡ DPI: Standart Mod",
                text_color="#F59E0B"
            )
        else:
            badge.configure(
                text="⚪ DPI: Kapalı",
                text_color=T.TEXT_MUTED
            )

    def _toggle_dpi_mode(self):
        gd_dir = find_goodbyedpi_dir()
        if not gd_dir:
            if messagebox:
                messagebox.showinfo(
                    "GoodbyeDPI Bulunamadı",
                    "GoodbyeDPI kurulum klasörü bulunamadı.\n\n"
                    "Klasörü tanıtmak için VDP_GOODBYEDPI_DIR ortam değişkenini ayarlayın "
                    "veya ayar dosyasına 'goodbyedpi_dir' anahtarını ekleyin:\n"
                    f"{CONFIG_FILE}"
                )
            return
        if getattr(self, "current_dpi_mode", 0) == 2:
            target_cmd = os.path.join(gd_dir, "1_Standart_Mod.cmd")
            next_name = "⚡ Standart Mod"
        else:
            target_cmd = os.path.join(gd_dir, "2_Agresif_Mod.cmd")
            next_name = "🚀 Agresif Mod"

        if os.path.exists(target_cmd):
            try:
                subprocess.run(["taskkill", "/F", "/IM", "goodbyedpi.exe"],
                               capture_output=True, creationflags=0x08000000)
                subprocess.Popen(["cmd.exe", "/c", "start", "", "/min", target_cmd],
                                 creationflags=0x08000000)
                self._log(f"[DPI] Mod değiştirildi: {next_name}")
            except Exception as e:
                self._log(f"[!] DPI Mod değiştirme hatası: {e}")

    def _check_smart_mode_suggestion(self, url):
        if not url:
            return
        extra = load_user_config().get("aggressive_dpi_domains", [])
        agresif_domains = tuple(DEFAULT_AGGRESSIVE_DPI_DOMAINS) + tuple(
            str(d).lower() for d in extra if isinstance(d, str) and d.strip()
        )
        url_lower = str(url).lower()
        if any(d in url_lower for d in agresif_domains):
            if getattr(self, "current_dpi_mode", 0) != 2:
                self._log("💡 [Akıllı Tavsiye] Bu site derin sansürlüdür; en hızlı indirme için sağ üstten '🚀 DPI: Agresif Mod'a geçebilirsiniz.")
