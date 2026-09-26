"""Gömülü arayüz fontlarını yükler ve `CTkFont` nesneleri üretir.

`assets/fonts/` altındaki TTF'ler `AddFontResourceExW(..., FR_PRIVATE)` ile
**sürece özel** kaydedilir: sisteme kurulum yapılmaz, kullanıcı profilinde iz
bırakılmaz, uygulama kapanınca kayıt düşer.

Sıralama kritiktir — Tk font tablosunu ilk kök oluşturulurken kurar, bu yüzden
`load()` **`ctk.CTk()` çağrılmadan önce** çalışmalıdır. `gui.py` bunu
`VideoDownloaderGUI.__init__` içindeki `super().__init__()` öncesinde yapar.

Yükleme başarısız olursa (fontlar yok, Windows dışı, GDI reddetti) modül
sessizce sistem fontlarına düşer ve `has_ui_font` / `has_icon_font` bayrakları
`False` olur. Arayüz çalışmaya devam eder; yalnızca harf formu değişir ve
ikonlar ASCII karşılıklarına iner.
"""

import os
import sys

from logger import get_logger

from . import theme

logger = get_logger("ui.fonts")

FR_PRIVATE = 0x10

# Yuklendikten sonra Tk'de hangi ailelerin gercekten gorundugunu tutar.
_state = {"loaded": False, "families": set(), "ui": False, "mono": False, "icon": False}

_font_cache = {}


def assets_dir() -> str:
    """Gömülü fontların bulunduğu dizin.

    PyInstaller onefile derlemesinde veriler `sys._MEIPASS` altına açılır;
    kaynaktan çalışırken depo kökü kullanılır.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "fonts")


def load() -> dict:
    """TTF'leri sürece kaydeder. `ctk.CTk()` öncesinde çağrılmalıdır.

    Birden fazla çağrı zararsızdır; ilk sonuç önbelleklenir.
    """
    if _state["loaded"]:
        return dict(_state)
    _state["loaded"] = True

    directory = assets_dir()
    if not os.path.isdir(directory):
        logger.debug("[ui.fonts] gomulu font dizini yok: %s", directory)
        return dict(_state)

    if sys.platform != "win32":
        # AddFontResourceExW yalnizca Windows'ta var. Uygulama zaten Windows
        # masaustu hedefli; diger platformlarda sistem fontlariyla calisir.
        logger.debug("[ui.fonts] win32 disi platform, sistem fontlari kullanilacak")
        return dict(_state)

    try:
        import ctypes

        gdi32 = ctypes.windll.gdi32
    except Exception:
        logger.debug("[ui.fonts] gdi32 yuklenemedi", exc_info=True)
        return dict(_state)

    loaded_files = 0
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith(".ttf"):
            continue
        path = os.path.join(directory, name)
        try:
            faces = gdi32.AddFontResourceExW(ctypes.c_wchar_p(path), FR_PRIVATE, 0)
        except Exception:
            logger.debug("[ui.fonts] AddFontResourceExW hatasi: %s", name, exc_info=True)
            continue
        if faces:
            loaded_files += 1
        else:
            logger.debug("[ui.fonts] font reddedildi (0 face): %s", name)

    logger.debug("[ui.fonts] %d font dosyasi yuklendi", loaded_files)
    return dict(_state)


def detect_families() -> dict:
    """Tk kökü hazır olduktan sonra hangi ailelerin çizilebildiğini belirler.

    `load()` fontu sürece kaydeder ama gerçekten kullanılabilir olduğunu
    yalnızca Tk'ye sorarak bilebiliriz. `gui.py` bunu kök oluştuktan hemen
    sonra çağırır.
    """
    try:
        from tkinter import font as tkfont

        families = set(tkfont.families())
    except Exception:
        logger.debug("[ui.fonts] aile listesi alinamadi", exc_info=True)
        families = set()

    _state["families"] = families
    _state["ui"] = all(f in families for f in theme.FONT_UI.values())
    _state["mono"] = all(f in families for f in theme.FONT_MONO.values())
    _state["icon"] = theme.FONT_ICON in families

    if not _state["ui"]:
        logger.debug("[ui.fonts] Manrope bulunamadi, %s kullanilacak", theme.FALLBACK_UI)
    if not _state["icon"]:
        logger.debug("[ui.fonts] ikon fontu bulunamadi, ASCII karsiliklarina dusuluyor")
    return dict(_state)


def has_icon_font() -> bool:
    return bool(_state["icon"])


def has_ui_font() -> bool:
    return bool(_state["ui"])


def _make(family: str, size: int, bold: bool = False):
    """CTkFont üretir ve önbelleğe alır.

    CTk font nesneleri Tk kaynağı tutar; her etikette yenisini üretmek
    yüzlerce widget'ta gözle görülür bellek ve kurulum maliyeti demektir.
    """
    key = (family, size, bold)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    import customtkinter as ctk

    font = ctk.CTkFont(family=family, size=size, weight="bold" if bold else "normal")
    _font_cache[key] = font
    return font


def ui(size: int = theme.SIZE_BASE, weight: int = 600):
    """Arayüz metni fontu. `weight` 500/600/700/800 olabilir.

    Her ağırlık kendi aile adını taşıdığı için sentetik kalınlaştırma
    kullanılmaz — gerçek Manrope çizimleri elde edilir. Font yoksa Segoe UI'a
    düşülür ve 700+ ağırlıklar sentetik bold ile taklit edilir.
    """
    if weight not in theme.FONT_UI:
        raise ValueError(f"desteklenmeyen agirlik {weight}; {sorted(theme.FONT_UI)}")
    if _state["ui"]:
        return _make(theme.FONT_UI[weight], size)
    return _make(theme.FALLBACK_UI, size, bold=weight >= 700)


def mono(size: int = theme.SIZE_BASE, weight: int = 600):
    """Rakam fontu (yüzde, hız, süre, boyut)."""
    if weight not in theme.FONT_MONO:
        raise ValueError(f"desteklenmeyen agirlik {weight}; {sorted(theme.FONT_MONO)}")
    if _state["mono"]:
        return _make(theme.FONT_MONO[weight], size)
    return _make(theme.FALLBACK_MONO, size, bold=weight >= 600)


def icon(size: int = 18):
    """İkon fontu. Yoksa ASCII karşılıkları için arayüz fontuna düşer."""
    if _state["icon"]:
        return _make(theme.FONT_ICON, size)
    return ui(max(size - 4, theme.SIZE_XS), 700)
