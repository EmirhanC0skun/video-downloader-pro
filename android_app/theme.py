# -*- coding: utf-8 -*-
"""Video Downloader Pro — Mobil (Flet) tasarım belirteçleri.

Bu modül masaüstündeki `ui/theme.py` ile **aynı** paleti taşır: iki uygulama
tek bir tasarım dilini konuşur, bir renk değiştiğinde iki tarafta birlikte
kayar. Renk adları masaüstündekiyle birebir aynıdır (`BG_CARD`, `PRIMARY`,
`TEXT_MUTED` …); eski `COLOR_*` adları alt tarafta takma ad olarak korunur,
böylece bu modülü kullanan mevcut kod kırılmaz.

**Alfa hakkında.** Tasarım `rgba(255,255,255,.06)` gibi yarı saydam katmanlar
kullanır. Flet alfayı destekler ama masaüstü (Tkinter) desteklemez; ortak
paletin ikisinde de aynı pikseli üretmesi için katmanlar burada da `over()`
ile önceden düzleştirilir. Aynı fonksiyon, aynı girdi, aynı çıktı.

Ölçüler masaüstünden **kopyalanmaz**: dokunmatik hedefler Android'in 48dp
tabanına göre büyütülür (bkz. `H_BUTTON`, `H_TOUCH`).
"""


def over(overlay: str, base: str, alpha: float) -> str:
    """`overlay` rengini `base` üzerine `alpha` opaklıkla düzleştirir.

    >>> over("#FFFFFF", "#11151F", 0.06)
    '#1f232c'
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha 0..1 araliginda olmali: {alpha}")
    fg = _rgb(overlay)
    bg = _rgb(base)
    mixed = tuple(round(b + (f - b) * alpha) for f, b in zip(fg, bg))
    return "#%02x%02x%02x" % mixed


def _rgb(value: str) -> tuple:
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"6 haneli hex renk bekleniyordu: {value!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Zeminler
# ---------------------------------------------------------------------------
BG_APP = "#0A0D14"          # ekran zemini, input dolgusu, stat kutusu
BG_SIDEBAR = "#0D1119"      # app bar, alt gezinme çubuğu
BG_CARD = "#11151F"         # kartlar, liste satirlari
BG_ELEVATED = "#181D2A"     # ikincil butonlar, rozetler, secili segment
BG_HOVER = "#1F2536"        # BG_ELEVATED uzerine dokunma/hover
BG_NAV_ACTIVE = "#161C2B"   # secili gezinme ogesi
BG_NAV_HOVER = "#141927"

# ---------------------------------------------------------------------------
# Kenarliklar
# ---------------------------------------------------------------------------
BORDER = over("#FFFFFF", BG_CARD, 0.06)            # kart kenarligi
BORDER_STRONG = over("#FFFFFF", BG_APP, 0.08)      # input kenarligi
BORDER_SIDEBAR = over("#FFFFFF", BG_SIDEBAR, 0.06)
DIVIDER = over("#FFFFFF", BG_CARD, 0.05)           # kart ici ayirici

# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
TEXT = "#F1F5F9"
TEXT_MUTED = "#8A94A8"
TEXT_DIM = "#7A8398"     # kart zemininde 4.80:1 — WCAG AA govde metni esigi
TEXT_CHIP = "#B6BECD"       # secili olmayan pill metni

# ---------------------------------------------------------------------------
# Aksan renkleri
# ---------------------------------------------------------------------------
PRIMARY = "#3B82F6"         # aksan: ikon, kenarlik, gosterge
PRIMARY_HOVER = "#2F74EA"
# Dolgulu mavi butonun zemini aksandan bir basamak koyudur. #3B82F6 uzerinde
# beyaz metin yalnizca 3.68:1 verir — buton etiketi buyuk metin sayilmadigi
# icin AA esigini (4.5:1) gecmez. #2563EB ile ayni mavi ailesinde kalip
# 5.17:1 elde edilir.
PRIMARY_BUTTON = "#2563EB"
PRIMARY_BUTTON_HOVER = "#1D4ED8"
PRIMARY_LIGHT = "#60A5FA"   # link, aktif nav ikonu
PRIMARY_TINT = "#93C5FD"    # secili pill metni, rozet metni

SUCCESS = "#22C55E"
SUCCESS_HOVER = "#2BD46B"
SUCCESS_INK = "#052E16"     # yesil buton uzerindeki metin

DANGER = "#F87171"
DANGER_HOVER = "#FCA5A5"
DANGER_BASE = "#EF4444"

WARNING = "#FBBF24"
WARNING_BASE = "#F59E0B"

PURPLE = "#8B5CF6"          # aksan
PURPLE_HOVER = "#9B6FF8"
# Ayni gerekce: #8B5CF6 uzerinde acik metin 3.87:1, #7C3AED uzerinde 5.70:1.
PURPLE_BUTTON = "#7C3AED"
PURPLE_BUTTON_HOVER = "#6D28D9"
PURPLE_LIGHT = "#A78BFA"

# ---------------------------------------------------------------------------
# Tint dolgular — kart zemini uzerinde aksan katmani
# ---------------------------------------------------------------------------
PRIMARY_FILL = over(PRIMARY, BG_CARD, 0.15)
PRIMARY_FILL_SOFT = over(PRIMARY, BG_CARD, 0.12)
PRIMARY_BADGE = over(PRIMARY, BG_SIDEBAR, 0.18)
SUCCESS_FILL = over(SUCCESS, BG_CARD, 0.15)
SUCCESS_BORDER = over(SUCCESS, BG_CARD, 0.35)
WARNING_FILL = over(WARNING_BASE, BG_CARD, 0.15)
DANGER_FILL = over(DANGER_BASE, BG_CARD, 0.10)
DANGER_BORDER = over(DANGER_BASE, BG_CARD, 0.35)
PURPLE_FILL = over(PURPLE, BG_CARD, 0.15)
PURPLE_BORDER = over(PURPLE, BG_CARD, 0.35)
DROPZONE_BORDER = over("#FFFFFF", BG_SIDEBAR, 0.12)

# Tur ikonu arkaliklari (Son Indirilenler / Indirilenler satirlari)
ICON_FILL_VIDEO = over(PRIMARY, BG_CARD, 0.14)
ICON_FILL_AUDIO = over(PURPLE, BG_CARD, 0.14)

# ---------------------------------------------------------------------------
# Yaricaplar — masaüstüyle ayni merdiven
# ---------------------------------------------------------------------------
R_CARD = 16
R_CARD_SM = 14
R_TILE = 12
R_INPUT = 12
R_BUTTON = 12
R_CHIP = 8
R_BADGE = 10
R_PILL = 999           # Flet gercek yuvarlak uc cizebilir
R_SHELL = 10

# ---------------------------------------------------------------------------
# Olculer — dokunmatik icin masaüstünden buyuk
# ---------------------------------------------------------------------------
# Android dokunma hedefi tabani 48dp'dir (iOS'ta 44pt). Masaüstünde 46/42 olan
# yukseklikler burada bu tabanin altina dusurulmez.
H_TOUCH = 48                # her dokunulabilir ogenin taban yuksekligi
H_INPUT = 52
H_BUTTON = 50
H_BUTTON_SM = 48
H_PILL = 40                 # pill'ler 8dp aralikla dizilir, taban 40 yeterli
H_NAV = 48
H_ROW = 64
GAP_TOUCH = 8               # bitisik dokunma hedefleri arasi en az bosluk

# Sayfa yerlesimi
PAGE_PAD = 16
CARD_PAD = 16
SECTION_GAP = 14
APPBAR_H = 56

# ---------------------------------------------------------------------------
# Tipografi
# ---------------------------------------------------------------------------
# Aile adlari `fonts.register(page)` tarafindan Flet'e kaydedilir. Fontlar
# paketlenmemisse Flet sistem varsayilanina duser; arayuz calismaya devam eder.
FONT_UI = "Manrope"
FONT_UI_BOLD = "Manrope Bold"
FONT_MONO = "JetBrains Mono"

# Boyut merdiveni. Masaüstü 13'lük tabanini kullanir; mobilde gövde metni
# Material'in 14sp tabanina cekilir, altindaki basamaklar korunur.
SIZE_XS = 11                # rozet, mono meta
SIZE_SM = 12                # ikincil metin
SIZE_BASE = 14              # govde metni
SIZE_MD = 15
SIZE_LG = 17
SIZE_XL = 20                # sayfa basligi
SIZE_TITLE = 17
SIZE_HERO = 40              # indirme yuzdesi

# Metin agirliklari — Flet `ft.FontWeight` degerlerine `widgets.py` cevirir.
W_MEDIUM = 500
W_SEMI = 600
W_BOLD = 700
W_EXTRA = 800


def all_colors() -> dict:
    """Modüldeki tüm renk belirteçlerini ad -> hex olarak döndürür.

    Testler belirteç bütünlüğünü bunun üzerinden doğrular.
    """
    return {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, str) and value.startswith("#")
    }


# ---------------------------------------------------------------------------
# Geriye donuk takma adlar
# ---------------------------------------------------------------------------
# Eski mobil palet adlari. Yeni kod yukaridaki belirtecleri kullanmali; bunlar
# yalnizca halen `COLOR_*` bekleyen cagri noktalari icin durur.
COLOR_BG = BG_APP
COLOR_CARD = BG_CARD
COLOR_CARD_ELEVATED = BG_ELEVATED
COLOR_BORDER = BORDER
COLOR_PRIMARY = PRIMARY
COLOR_PRIMARY_HOVER = PRIMARY_HOVER
COLOR_SUCCESS = SUCCESS
COLOR_WARNING = WARNING
COLOR_ERROR = DANGER
COLOR_TEXT_PRIMARY = TEXT
COLOR_TEXT_MUTED = TEXT_MUTED
COLOR_TEXT_CYAN = PRIMARY_LIGHT

__all__ = [
    "over",
    # zeminler
    "BG_APP", "BG_SIDEBAR", "BG_CARD", "BG_ELEVATED", "BG_HOVER",
    "BG_NAV_ACTIVE", "BG_NAV_HOVER",
    # kenarliklar
    "BORDER", "BORDER_STRONG", "BORDER_SIDEBAR", "DIVIDER",
    # metin
    "TEXT", "TEXT_MUTED", "TEXT_DIM", "TEXT_CHIP",
    # aksan
    "PRIMARY", "PRIMARY_HOVER", "PRIMARY_LIGHT", "PRIMARY_TINT",
    "PRIMARY_BUTTON", "PRIMARY_BUTTON_HOVER",
    "SUCCESS", "SUCCESS_HOVER", "SUCCESS_INK",
    "DANGER", "DANGER_HOVER", "DANGER_BASE",
    "WARNING", "WARNING_BASE",
    "PURPLE", "PURPLE_HOVER", "PURPLE_LIGHT",
    "PURPLE_BUTTON", "PURPLE_BUTTON_HOVER",
    # tint
    "PRIMARY_FILL", "PRIMARY_FILL_SOFT", "PRIMARY_BADGE",
    "SUCCESS_FILL", "SUCCESS_BORDER", "WARNING_FILL",
    "DANGER_FILL", "DANGER_BORDER", "PURPLE_FILL", "PURPLE_BORDER",
    "DROPZONE_BORDER", "ICON_FILL_VIDEO", "ICON_FILL_AUDIO",
    # yaricap / olcu
    "R_CARD", "R_CARD_SM", "R_TILE", "R_INPUT", "R_BUTTON", "R_CHIP",
    "R_BADGE", "R_PILL", "R_SHELL",
    "H_TOUCH", "H_INPUT", "H_BUTTON", "H_BUTTON_SM", "H_PILL", "H_NAV",
    "H_ROW", "GAP_TOUCH", "PAGE_PAD", "CARD_PAD", "SECTION_GAP", "APPBAR_H",
    # tipografi
    "FONT_UI", "FONT_UI_BOLD", "FONT_MONO",
    "SIZE_XS", "SIZE_SM", "SIZE_BASE", "SIZE_MD", "SIZE_LG", "SIZE_XL",
    "SIZE_TITLE", "SIZE_HERO",
    "W_MEDIUM", "W_SEMI", "W_BOLD", "W_EXTRA",
    "all_colors",
    # eski adlar
    "COLOR_BG", "COLOR_CARD", "COLOR_CARD_ELEVATED", "COLOR_BORDER",
    "COLOR_PRIMARY", "COLOR_PRIMARY_HOVER",
    "COLOR_SUCCESS", "COLOR_WARNING", "COLOR_ERROR",
    "COLOR_TEXT_PRIMARY", "COLOR_TEXT_MUTED", "COLOR_TEXT_CYAN",
]
