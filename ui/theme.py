"""Tasarım belirteçleri (design tokens).

Değerler Claude Design projesindeki `Yeni Tasarım.dc.html` dosyasından
alınmıştır. Bu modül bilinçli olarak Tk'den bağımsızdır: ekran olmadan
içe aktarılabilir, böylece belirteç bütünlüğü ekransız test edilebilir.

**Alfa hakkında.** Tasarım `rgba(255,255,255,.06)` gibi yarı saydam
katmanlar kullanır; Tkinter alfa kanalı desteklemez. Bunun yerine katmanlar
`over()` ile bindikleri zemine göre önceden düzleştirilir. Değerleri elle
yazmak yerine hesaplamak, zemin rengi değiştiğinde türetilmiş renklerin
birlikte kaymasını sağlar.
"""


def over(overlay: str, base: str, alpha: float) -> str:
    """`overlay` rengini `base` üzerine `alpha` opaklıkla düzleştirir.

    Tasarımdaki `rgba()` katmanlarının Tkinter karşılığını üretir.

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
BG_APP = "#0A0D14"          # pencere zemini, input dolgusu, stat kutusu
BG_SIDEBAR = "#0D1119"      # sol menu, dropzone
BG_CARD = "#11151F"         # kartlar, liste satirlari
BG_ELEVATED = "#181D2A"     # ikincil butonlar, rozetler, secili segment
BG_HOVER = "#1F2536"        # BG_ELEVATED uzerine hover
BG_NAV_ACTIVE = "#161C2B"   # sidebar'da secili oge
BG_NAV_HOVER = "#141927"    # sidebar'da hover

# ---------------------------------------------------------------------------
# Kenarliklar — tasarimdaki rgba(255,255,255,.06) ve .08 katmanlari
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
# Tint dolgular — rgba(<aksan>, .12 .. .18) kart zemini uzerinde
# ---------------------------------------------------------------------------
PRIMARY_FILL = over(PRIMARY, BG_CARD, 0.15)
PRIMARY_FILL_SOFT = over(PRIMARY, BG_CARD, 0.12)
PRIMARY_BADGE = over(PRIMARY, BG_SIDEBAR, 0.18)
SUCCESS_FILL = over(SUCCESS, BG_CARD, 0.15)
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
# Yaricaplar
# ---------------------------------------------------------------------------
R_CARD = 16
R_CARD_SM = 14
R_TILE = 12
R_INPUT = 12
R_BUTTON = 12
R_CHIP = 8
R_BADGE = 10
R_PILL = 17            # tasarimdaki border-radius:999px karsiligi
R_SHELL = 10

# ---------------------------------------------------------------------------
# Olculer
# ---------------------------------------------------------------------------
SIDEBAR_W = 216
HEADER_H = 64
CONTENT_MAX_W = 800
WINDOW_W = 1100
WINDOW_H = 700
WINDOW_MIN_W = 980
WINDOW_MIN_H = 640

H_INPUT = 46
H_BUTTON = 46
H_BUTTON_SM = 42
H_PILL = 34
H_NAV = 40
H_ROW = 56

# ---------------------------------------------------------------------------
# Tipografi — her agirlik kendi aile adini tasir (bkz. tools/build_ui_fonts.py)
# ---------------------------------------------------------------------------
FONT_UI = {
    500: "Manrope Medium",
    600: "Manrope SemiBold",
    700: "Manrope Bold",
    800: "Manrope ExtraBold",
}
FONT_MONO = {
    500: "JetBrains Mono Medium",
    600: "JetBrains Mono SemiBold",
}
FONT_ICON = "VDP Icons"

# Gomulu fontlar yuklenemezse kullanilan sistem karsiliklari.
FALLBACK_UI = "Segoe UI"
FALLBACK_MONO = "Consolas"

# Boyut merdiveni (tasarimdan). CTkFont tam sayi ister, tasarimdaki 13.5 gibi
# degerler en yakin tam sayiya yuvarlanir.
SIZE_XS = 11
SIZE_SM = 12
SIZE_BASE = 13
SIZE_MD = 14
SIZE_LG = 15
SIZE_XL = 17
SIZE_TITLE = 16
SIZE_HERO = 40


def all_colors() -> dict:
    """Modüldeki tüm renk belirteçlerini ad -> hex olarak döndürür.

    Testler belirteç bütünlüğünü bunun üzerinden doğrular.
    """
    return {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, str) and value.startswith("#")
    }
