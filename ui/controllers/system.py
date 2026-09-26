# -*- coding: utf-8 -*-
"""
Video Downloader Pro — System Controller Mixin.
Handles sound effects, native Windows desktop notifications, and automatic shutdown.
"""

import sys
import base64
import threading
import subprocess

try:
    import winsound
except Exception:
    winsound = None

from logger import get_logger
from ui.config import (
    get_notification_sound_enabled,
    get_desktop_notification_enabled,
)

logger = get_logger("ui.controllers.system")


class SystemControllerMixin:
    """
    Mixin providing notifications, audio feedback, and system shutdown automation.
    """

    def _play_notification_sound(self):
        try:
            if hasattr(self, "chk_sound"):
                if not bool(self.chk_sound.get()):
                    return
            elif not get_notification_sound_enabled():
                return

            if winsound:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            logger.debug("[ui.controllers.system] _play_notification_sound() istisnası", exc_info=True)

    def _send_desktop_notification(self, title: str, message: str):
        """Kullanıcı izni varsa yerel Windows Toast bildirimi gönderir."""
        try:
            if hasattr(self, "chk_notify"):
                if not bool(self.chk_notify.get()):
                    return
            elif not get_desktop_notification_enabled():
                return

            if sys.platform != "win32":
                return

            def _toast_worker():
                try:
                    t = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', '&quot;').replace("'", "&apos;")
                    m = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', '&quot;').replace("'", "&apos;")
                    xml_str = f"<toast><visual><binding template='ToastGeneric'><text>{t}</text><text>{m}</text></binding></visual></toast>"
                    ps_code = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("{xml_str}")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Video Downloader Pro').Show($toast)
"""
                    encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                        timeout=5,
                    )
                except Exception:
                    logger.debug("[ui.controllers.system] Windows toast notification istisnası", exc_info=True)

            threading.Thread(target=_toast_worker, daemon=True).start()
        except Exception:
            logger.debug("[ui.controllers.system] _send_desktop_notification istisnası", exc_info=True)

    def _handle_shutdown(self):
        """
        Otomatik kapatma. Yalnızca ana iş parçacığından çağrılmalıdır:
        chk_shutdown bir Tk widget'ıdır ve çalışan iş parçacığından okunamaz.
        """
        if not (hasattr(self, "chk_shutdown") and self.chk_shutdown.get()):
            return
        if sys.platform != "win32":
            self._log("[!] Otomatik kapatma yalnızca Windows üzerinde desteklenir.")
            return
        self._log("[!] Otomatik kapatma devrede: Bilgisayar 60 saniye içinde kapatılacak.")
        self._log("[i] Vazgeçmek için komut isteminde 'shutdown /a' çalıştırın.")
        try:
            subprocess.run(
                ["shutdown", "/s", "/t", "60"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            logger.debug("[ui.controllers.system] _handle_shutdown() sessiz istisna yutuldu", exc_info=True)
