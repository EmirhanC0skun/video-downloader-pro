# -*- coding: utf-8 -*-
"""Gömülü arayüz fontlarını Flet'e kaydeder.

Masaüstü sürüm `assets/fonts/` altındaki Manrope ve JetBrains Mono TTF'lerini
sürece kaydeder (bkz. `ui/fonts.py`). Mobilde aynı dosyalar
`android_app/assets/fonts/` altında durur ve `page.fonts` üzerinden Flutter'a
verilir — iki uygulama aynı harf formunu çizer.

Kayıt başarısız olursa (varlıklar paketlenmemiş, yol farklı) modül sessizce
sistem fontuna düşer: `theme.FONT_UI` çözümlenemeyen bir aile adı olur ve
Flutter varsayılana iner. Arayüz çalışmaya devam eder, yalnızca harf formu
değişir.
"""

import os

try:
    import theme as T
except ImportError:  # paket olarak import edildiginde
    from android_app import theme as T


# Flet'e verilen aile adi -> assets dizinine gore goreli yol.
FONT_FILES = {
    T.FONT_UI: "fonts/Manrope-SemiBold.ttf",
    T.FONT_UI_BOLD: "fonts/Manrope-ExtraBold.ttf",
    T.FONT_MONO: "fonts/JetBrainsMono-Medium.ttf",
}


def assets_dir() -> str:
    """Varlık dizininin mutlak yolu (`android_app/assets`)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def available() -> bool:
    """Tüm font dosyaları yerinde mi?"""
    base = assets_dir()
    return all(os.path.isfile(os.path.join(base, path))
               for path in FONT_FILES.values())


def register(page) -> bool:
    """`page.fonts` sözlüğünü doldurur ve varsayılan aileyi ayarlar.

    `ft.run(..., assets_dir=...)` ile birlikte çalışır: yollar varlık dizinine
    görelidir. Dosyalar eksikse hiçbir şey yapmaz ve `False` döndürür.
    """
    if not available():
        return False
    try:
        page.fonts = dict(FONT_FILES)
        return True
    except Exception:
        return False
