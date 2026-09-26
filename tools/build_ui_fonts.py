"""`assets/fonts/` altındaki gömülü arayüz fontlarını üretir.

Arayüz üç font ailesi kullanır:

* **Manrope** (500/600/700/800) — tüm arayüz metni
* **JetBrains Mono** (500/600) — rakamlar: yüzde, hız, süre, boyut
* **VDP Icons** — Material Symbols Rounded'dan indirgenmiş ikon seti

Üçü de kaynağında depoya işlenemeyecek kadar büyüktür: Material Symbols 14 MB,
Manrope ve JetBrains Mono ise arayüzün hiç kullanmadığı yüzlerce dile ait
glyph taşır. Bu betik hepsini indirir, gerekli hale getirir ve toplam ~350 KB
olacak şekilde kırpar.

    python tools/build_ui_fonts.py

Ağ erişimi ister. Üretilen `.ttf` dosyaları depoya işlenir; çalışma zamanında
ne ağ ne de sisteme font kurulumu gerekir (`ui/fonts.py` süreç-özel yükler).

Üç uyarlama notu:

1. **Statik örnekleme.** Manrope yalnızca değişken font olarak yayımlanıyor.
   GDI değişken fonttan sadece varsayılan örneği (wght=400) çizdiği için
   istenen ağırlıklar `fontTools.varLib.instancer` ile statik dosyalara
   ayrıştırılır.
2. **Aile adı başına tek ağırlık.** GDI süreç-özel fontlarda ağırlık
   eşleştirmesini güvenilir yapmaz. Bu yüzden her ağırlık kendi aile adını
   alır ("Manrope SemiBold"), tıpkı JetBrains Mono'nun yaptığı gibi.
   `ui/theme.py` bu adları birebir kullanır.
3. **Ligatür yok.** Tk 8.6 ligatür ikamesi yapmaz, bu yüzden ikonlar `movie`
   gibi adlarla değil doğrudan PUA kod noktalarıyla çizilir; eşleme
   `ui/icons.py` içindedir ve `--check` ile doğrulanır.
"""

import argparse
import io
import os
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(REPO, "assets", "fonts")

_SYMBOLS = (
    "https://github.com/google/material-design-icons/raw/master/variablefont/"
    "MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D"
)
URL_ICON_TTF = _SYMBOLS + ".ttf"
URL_ICON_CODEPOINTS = _SYMBOLS + ".codepoints"
URL_MANROPE = "https://github.com/google/fonts/raw/main/ofl/manrope/Manrope%5Bwght%5D.ttf"
URL_JETBRAINS = (
    "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-{}.ttf"
)

# Arayüzün kullandığı Manrope ağırlıkları: (dosya soneki, aile adı, wght)
MANROPE_WEIGHTS = [
    ("Medium", "Manrope Medium", 500),
    ("SemiBold", "Manrope SemiBold", 600),
    ("Bold", "Manrope Bold", 700),
    ("ExtraBold", "Manrope ExtraBold", 800),
]

JETBRAINS_WEIGHTS = ["Medium", "SemiBold"]

# Latin temel + Latin-1 ek + Türkçe'ye özgü harfler ve arayüzün kullandığı
# noktalama. Metin fontlarını bu aralığa indirgemek dosya başına ~250 KB
# tasarruf sağlar.
TEXT_UNICODES = (
    "U+0020-007E,U+00A0-00FF,U+0100-0131,U+0150-0153,U+015E-0161,"
    "U+016E-0173,U+2018-201A,U+201C-201E,U+2022,U+2026,U+2030,"
    "U+2039-203A,U+2044,U+20BA,U+2122,U+2190-2193,U+2212,U+00B7"
)

# Mantıksal ad -> Material Symbols glyph adı.
# `ui/icons.py` içindeki GLYPHS bu anahtarlarla birebir örtüşmelidir.
ICONS = {
    "audio_file": "audio_file",
    "back": "arrow_back",
    "battery": "battery_alert",
    "bell": "notifications",
    "bolt": "bolt",
    "cancel": "close",
    "check": "check",
    "chevron": "chevron_right",
    "chevron_down": "expand_more",
    "clock": "schedule",
    "convert": "autorenew",
    "cookie": "cookie",
    "copy": "content_copy",
    "delete": "delete",
    "dots": "more_horiz",
    "dots_v": "more_vert",
    "download": "download",
    "error": "error",
    "film": "movie",
    "folder": "folder",
    "folder_open": "folder_open",
    "image": "image",
    "info": "info",
    "library": "folder",
    "link": "link",
    "music": "music_note",
    "open_new": "open_in_new",
    "paste": "content_paste",
    "pause": "pause",
    "play": "play_arrow",
    "playlist_add": "playlist_add",
    "plus": "add",
    "power": "power_settings_new",
    "queue": "format_list_bulleted",
    "refresh": "refresh",
    "search": "search",
    "settings": "tune",
    "shield": "shield",
    "sliders": "tune",
    "social": "play_circle",
    "speed": "speed",
    "storage": "storage",
    "subtitles": "subtitles",
    "terminal": "terminal",
    "video_file": "video_file",
    "volume": "volume_up",
    "warning": "warning",
    "wifi": "wifi",
}


def _fetch(url: str) -> bytes:
    print(f"  indiriliyor  {url.rsplit('/', 1)[-1][:52]}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        data = resp.read()
    if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf") and not url.endswith(
        ".codepoints"
    ):
        raise RuntimeError(f"gecerli bir font gelmedi ({len(data)} bayt): {url}")
    return data


def _rename(font, family: str, postscript: str) -> None:
    """Aile / alt aile adlarını tek ağırlıklı bir aile olacak şekilde yazar."""
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = family
        elif record.nameID in (2, 17):
            record.string = "Regular"
        elif record.nameID == 4:
            record.string = family
        elif record.nameID == 6:
            record.string = postscript


def _subset_text(font, unicodes: str):
    from fontTools import subset

    options = subset.Options(layout_features=["kern", "liga"], name_IDs="*", notdef_outline=True)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=subset.parse_unicodes(unicodes))
    subsetter.subset(font)
    return font


def build_manrope() -> list:
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    print("Manrope (degisken font -> statik agirliklar)")
    raw = _fetch(URL_MANROPE)
    written = []
    for suffix, family, wght in MANROPE_WEIGHTS:
        font = TTFont(io.BytesIO(raw))
        font = instancer.instantiateVariableFont(font, {"wght": wght}, inplace=True)
        _subset_text(font, TEXT_UNICODES)
        _rename(font, family, f"Manrope-{suffix}")
        path = os.path.join(FONT_DIR, f"Manrope-{suffix}.ttf")
        font.save(path)
        written.append(path)
        print(f"    {family:22} {os.path.getsize(path) / 1024:6.1f} KB")
    return written


def build_jetbrains() -> list:
    from fontTools.ttLib import TTFont

    print("JetBrains Mono")
    written = []
    for suffix in JETBRAINS_WEIGHTS:
        font = TTFont(io.BytesIO(_fetch(URL_JETBRAINS.format(suffix))))
        _subset_text(font, TEXT_UNICODES)
        family = f"JetBrains Mono {suffix}"
        _rename(font, family, f"JetBrainsMono-{suffix}")
        path = os.path.join(FONT_DIR, f"JetBrainsMono-{suffix}.ttf")
        font.save(path)
        written.append(path)
        print(f"    {family:22} {os.path.getsize(path) / 1024:6.1f} KB")
    return written


def load_codepoints(raw: bytes) -> dict:
    table = {}
    for line in raw.decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            table[parts[0]] = int(parts[1], 16)
    return table


def build_icons() -> dict:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    print("VDP Icons (Material Symbols Rounded alt kumesi)")
    codepoints = load_codepoints(_fetch(URL_ICON_CODEPOINTS))
    missing = sorted({g for g in ICONS.values() if g not in codepoints})
    if missing:
        raise RuntimeError(f"fontta bulunmayan glyph adlari: {missing}")

    font = TTFont(io.BytesIO(_fetch(URL_ICON_TTF)))
    wanted = sorted({codepoints[g] for g in ICONS.values()})
    subsetter = subset.Subsetter(
        options=subset.Options(layout_features=[], name_IDs="*", notdef_outline=True)
    )
    subsetter.populate(unicodes=wanted)
    subsetter.subset(font)
    _rename(font, "VDP Icons", "VDPIcons-Regular")
    path = os.path.join(FONT_DIR, "VdpIcons.ttf")
    font.save(path)
    print(f"    {'VDP Icons':22} {os.path.getsize(path) / 1024:6.1f} KB  ({len(wanted)} glyph)")
    return {name: codepoints[glyph] for name, glyph in ICONS.items()}


def check_icon_mapping(mapping: dict) -> int:
    """Uretilen kod noktalarinin ui/icons.py ile ortustugunu dogrular."""
    sys.path.insert(0, REPO)
    from ui.icons import GLYPHS

    problems = []
    for name, cp in sorted(mapping.items()):
        actual = GLYPHS.get(name)
        if actual is None:
            problems.append(f"ui/icons.py eksik: {name}")
        elif ord(actual) != cp:
            problems.append(f"{name}: ui/icons.py U+{ord(actual):04X}, font U+{cp:04X}")
    for name in sorted(set(GLYPHS) - set(mapping)):
        problems.append(f"ui/icons.py fazla (fontta yok): {name}")

    if problems:
        print("\nEsleme hatalari:", file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"\nui/icons.py esleme dogru ({len(mapping)} ikon).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fontlari yeniden uretmeden ui/icons.py eslemesini dogrula",
    )
    args = parser.parse_args()

    try:
        import fontTools  # noqa: F401
    except ImportError:
        print("fontTools gerekli:  pip install fonttools", file=sys.stderr)
        return 1

    os.makedirs(FONT_DIR, exist_ok=True)

    if args.check:
        return check_icon_mapping({n: ord(c) for n, c in _current_mapping().items()})

    build_manrope()
    build_jetbrains()
    mapping = build_icons()

    total = sum(
        os.path.getsize(os.path.join(FONT_DIR, f))
        for f in os.listdir(FONT_DIR)
        if f.endswith(".ttf")
    )
    print(f"\ntoplam gomulu font boyutu: {total / 1024:.1f} KB")

    print("\nui/icons.py icin GLYPHS:")
    for name in sorted(mapping):
        print(f'    "{name}": "\\u{mapping[name]:04x}",')
    return 0


def _current_mapping() -> dict:
    sys.path.insert(0, REPO)
    from ui.icons import GLYPHS

    return dict(GLYPHS)


if __name__ == "__main__":
    raise SystemExit(main())
