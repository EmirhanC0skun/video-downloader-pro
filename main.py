# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Uygulama giriş noktası.

    python main.py            # masaüstü arayüzü
    python main.py --cli ...  # komut satırı indiricisi
"""

import sys
import os
import io

# --noconsole modunda sys.stdout ve sys.stderr None olabilir; loglama veya
# print çağrılarının çökmesini önlemek için koruyucu NullWriter atanır.
class _NullWriter(io.StringIO):
    def write(self, s):
        return len(s) if s else 0
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()

# Windows konsolunun varsayılan kod sayfası (cp1254 vb.) emoji ve Türkçe
# karakterleri kodlayamıyor. Çıktı bir dosyaya/boruya yönlendirildiğinde CLI
# ilk print satırında UnicodeEncodeError ile çöküyordu.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(sys.executable)))
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)
else:
    app_dir = os.path.abspath(os.path.dirname(__file__))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

import gui
import downloader


def main():
    if "--test-gui" in sys.argv:
        app = gui.VideoDownloaderGUI()
        if hasattr(app, "update"):
            app.update()
        if hasattr(app, "destroy"):
            app.destroy()
        sys.exit(0)
    elif "--cli" in sys.argv or "-c" in sys.argv:
        if "--cli" in sys.argv:
            sys.argv.remove("--cli")
        if "-c" in sys.argv:
            sys.argv.remove("-c")
        downloader.main_cli()
    else:
        gui.main()


if __name__ == "__main__":
    main()
