"""İkon glyph eşlemesi.

Tasarım ikonları SVG path'i olarak tanımlar; Tk SVG çizemez. Bunun yerine
Material Symbols Rounded'dan indirgenmiş `VDP Icons` fontu gömülür ve ikonlar
metin gibi çizilir — her boyutta keskin kalır ve `text_color` ile renklenir.

Tk 8.6 ligatür ikamesi yapmadığı için `movie` gibi adlar çalışmaz; glyph'lere
doğrudan PUA kod noktalarıyla erişilir. Aşağıdaki tablo
`tools/build_ui_fonts.py` çıktısıyla üretilmiştir ve `--check` ile doğrulanır.

Font yüklenemediğinde `text()` bir ASCII karşılığına düşer, böylece arayüz
ikonsuz da okunabilir kalır.
"""

GLYPHS = {
    "audio_file": "\ueb82",
    "back": "\ue5c4",
    "battery": "\ue19c",
    "bell": "\ue7f5",
    "bolt": "\uea0b",
    "cancel": "\ue5cd",
    "check": "\ue668",
    "chevron": "\ue5cc",
    "chevron_down": "\ue5cf",
    "clock": "\uefd6",
    "convert": "\ue863",
    "cookie": "\ueaac",
    "copy": "\ue14d",
    "delete": "\ue92e",
    "dots": "\ue5d3",
    "dots_v": "\ue5d4",
    "download": "\uf090",
    "error": "\uf8b6",
    "film": "\ue404",
    "folder": "\ue2c7",
    "folder_open": "\ue2c8",
    "image": "\ue3f4",
    "info": "\ue88e",
    "library": "\ue2c7",
    "link": "\ue250",
    "music": "\ue405",
    "open_new": "\ue89e",
    "paste": "\ue14f",
    "pause": "\ue034",
    "play": "\ue037",
    "playlist_add": "\ue03b",
    "plus": "\ue145",
    "power": "\uf8c7",
    "queue": "\ue241",
    "refresh": "\ue5d5",
    "search": "\uef7a",
    "settings": "\ue429",
    "shield": "\ue9e0",
    "sliders": "\ue429",
    "social": "\ue1c4",
    "speed": "\ue9e4",
    "storage": "\ue1db",
    "subtitles": "\ue048",
    "terminal": "\ueb8e",
    "video_file": "\ueb87",
    "volume": "\ue050",
    "warning": "\uf083",
    "wifi": "\ue63e",
}

# İkon fontu yoksa kullanılacak ASCII karşılıkları. Amaç güzellik değil,
# arayüzün fontsuz bir makinede de anlaşılır kalması.
FALLBACK = {
    "back": "<",
    "cancel": "X",
    "check": "OK",
    "chevron": ">",
    "chevron_down": "v",
    "dots": "...",
    "dots_v": ":",
    "download": "v",
    "pause": "||",
    "play": ">",
    "plus": "+",
    "search": "?",
}


def glyph(name: str) -> str:
    """`name` ikonunun glyph karakterini döndürür.

    Bilinmeyen ad sessizce boş dizeye düşmez — arayüzde görünmez bir eksik
    bırakmak yerine yazım hatasını geliştirme sırasında ortaya çıkarır.
    """
    try:
        return GLYPHS[name]
    except KeyError:
        raise KeyError(
            f"bilinmeyen ikon {name!r}. Kullanilabilir: {', '.join(sorted(GLYPHS))}"
        ) from None


def text(name: str, has_icon_font: bool) -> str:
    """İkon fontunun varlığına göre glyph veya ASCII karşılığı döndürür."""
    if has_icon_font:
        return glyph(name)
    glyph(name)  # adin gecerliligini fallback'te de dogrula
    return FALLBACK.get(name, "")
