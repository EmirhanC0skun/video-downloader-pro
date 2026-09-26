# -*- coding: utf-8 -*-
"""Mobil arayüz — tasarım belirteçleri, bileşen kitaplığı ve ekran sözleşmeleri.

Bu dosya arayüzün *görünüşünü* değil, görünüşü mümkün kılan sözleşmeleri
doğrular: iki uygulamanın aynı paleti taşıması, dokunma hedeflerinin platform
tabanının altına düşmemesi, kontrast eşiklerinin tutması ve — en önemlisi —
sessizce hiçbir şey yapmayan Flet API'lerinin geri sızmaması.

Son madde ucuz görünüp pahalıya patlayan bir sınıftır: Flet 0.86'da
`page.snack_bar = …` ve `dropdown.on_change = …` hata vermez, yalnızca ölü bir
Python niteliği yaratır. Kod çalışır, test geçer, kullanıcı hiçbir bildirim
görmez. Bu yüzden burada kaynak düzeyinde yasaklanırlar.
"""

import importlib.util
import os
import re
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_DIR = os.path.join(ROOT, "android_app")
for path in (ROOT, APP_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    import flet  # noqa: F401
    HAS_FLET = True
except Exception:
    HAS_FLET = False

import theme as mobile_theme
from ui import theme as desktop_theme

VIEW_FILES = [
    os.path.join(APP_DIR, "main.py"),
    os.path.join(APP_DIR, "views", "film_view.py"),
    os.path.join(APP_DIR, "views", "social_view.py"),
    os.path.join(APP_DIR, "views", "queue_view.py"),
    os.path.join(APP_DIR, "views", "converter_view.py"),
    os.path.join(APP_DIR, "views", "downloads_view.py"),
    os.path.join(APP_DIR, "views", "settings_view.py"),
]


def relative_luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def load_mobile_shell():
    """`android_app/main.py`yi dosya yolundan yukler.

    Duz `import main` depo kokundeki `main.py`ye carpar — ikisinin de adi
    `main` ve hangisinin kazanacagi `sys.path` sirasina bagli. Testin hangi
    modulu olctugu siraya kalmamali.
    """
    spec = importlib.util.spec_from_file_location(
        "vdpro_mobile_main", os.path.join(APP_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_source(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestThemeParity(unittest.TestCase):
    """Mobil ve masaüstü tek bir paleti paylaşır."""

    def test_shared_tokens_have_identical_values(self):
        mobile = mobile_theme.all_colors()
        desktop = desktop_theme.all_colors()
        shared = set(mobile) & set(desktop)
        self.assertGreater(len(shared), 25,
                           "iki tema arasinda paylasilan belirtec sayisi dustu")
        mismatched = {name: (mobile[name], desktop[name])
                      for name in shared if mobile[name] != desktop[name]}
        self.assertEqual({}, mismatched,
                         f"mobil ve masaustu palet ayristi: {mismatched}")

    def test_over_matches_desktop_implementation(self):
        for overlay, base, alpha in (("#FFFFFF", "#11151F", 0.06),
                                     ("#3B82F6", "#11151F", 0.15),
                                     ("#EF4444", "#11151F", 0.35)):
            self.assertEqual(desktop_theme.over(overlay, base, alpha),
                             mobile_theme.over(overlay, base, alpha))

    def test_legacy_color_aliases_still_resolve(self):
        # Eski `COLOR_*` adlarini kullanan cagri noktalari kirilmamali.
        self.assertEqual(mobile_theme.BG_APP, mobile_theme.COLOR_BG)
        self.assertEqual(mobile_theme.BG_CARD, mobile_theme.COLOR_CARD)
        self.assertEqual(mobile_theme.PRIMARY, mobile_theme.COLOR_PRIMARY)
        self.assertEqual(mobile_theme.TEXT, mobile_theme.COLOR_TEXT_PRIMARY)


class TestContrast(unittest.TestCase):
    """Her metin/zemin çifti WCAG AA gövde metni eşiğini (4.5:1) geçer."""

    PAIRS = [
        ("TEXT / BG_APP", "TEXT", "BG_APP"),
        ("TEXT / BG_CARD", "TEXT", "BG_CARD"),
        ("TEXT / BG_ELEVATED", "TEXT", "BG_ELEVATED"),
        ("TEXT_MUTED / BG_APP", "TEXT_MUTED", "BG_APP"),
        ("TEXT_MUTED / BG_CARD", "TEXT_MUTED", "BG_CARD"),
        ("TEXT_DIM / BG_APP", "TEXT_DIM", "BG_APP"),
        ("TEXT_DIM / BG_CARD", "TEXT_DIM", "BG_CARD"),
        ("TEXT_CHIP / BG_ELEVATED", "TEXT_CHIP", "BG_ELEVATED"),
        ("PRIMARY_LIGHT / BG_CARD", "PRIMARY_LIGHT", "BG_CARD"),
        ("PRIMARY_TINT / PRIMARY_FILL", "PRIMARY_TINT", "PRIMARY_FILL"),
        ("SUCCESS / BG_CARD", "SUCCESS", "BG_CARD"),
        ("WARNING / BG_CARD", "WARNING", "BG_CARD"),
        ("DANGER / BG_CARD", "DANGER", "BG_CARD"),
        ("PURPLE_LIGHT / BG_CARD", "PURPLE_LIGHT", "BG_CARD"),
        ("SUCCESS_INK / SUCCESS", "SUCCESS_INK", "SUCCESS"),
    ]

    def _assert_pairs(self, module, label):
        for name, foreground, background in self.PAIRS:
            with self.subTest(theme=label, pair=name):
                ratio = contrast(getattr(module, foreground),
                                 getattr(module, background))
                self.assertGreaterEqual(
                    ratio, 4.5,
                    f"{label} {name} kontrasti {ratio:.2f}:1 — AA esigi 4.5:1")

    def test_mobile_palette_meets_aa(self):
        self._assert_pairs(mobile_theme, "mobil")

    def test_desktop_palette_meets_aa(self):
        self._assert_pairs(desktop_theme, "masaustu")

    def test_filled_button_labels_meet_aa(self):
        """Dolgulu butonların etiketi büyük metin sayılmaz; 4.5:1 gerekir."""
        for module, label in ((mobile_theme, "mobil"), (desktop_theme, "masaustu")):
            with self.subTest(theme=label, button="primary"):
                self.assertGreaterEqual(
                    contrast("#FFFFFF", module.PRIMARY_BUTTON), 4.5)
            with self.subTest(theme=label, button="purple"):
                self.assertGreaterEqual(
                    contrast("#FFFFFF", module.PURPLE_BUTTON), 4.5)
            with self.subTest(theme=label, button="success"):
                self.assertGreaterEqual(
                    contrast(module.SUCCESS_INK, module.SUCCESS), 4.5)


class TestTouchTargets(unittest.TestCase):
    """Dokunma hedefleri platform tabanının altına düşmez."""

    # iOS 44pt, Android 48dp. Ortak taban olarak 44 alinir; Android'e ozgu
    # bilesenler (buton, ikon buton) 48'i tutmali.
    MIN_TOUCH = 44
    ANDROID_MIN = 48

    def test_interactive_heights(self):
        for name in ("H_TOUCH", "H_INPUT", "H_BUTTON", "H_BUTTON_SM", "H_NAV"):
            with self.subTest(token=name):
                self.assertGreaterEqual(getattr(mobile_theme, name),
                                        self.ANDROID_MIN,
                                        f"{name} Android 48dp tabaninin altinda")

    def test_pill_height_meets_common_minimum(self):
        # Pill'ler 8dp araliklarla dizilir; 40dp + aralik dokunulabilir kalir.
        self.assertGreaterEqual(mobile_theme.H_PILL, 40)
        self.assertGreaterEqual(mobile_theme.GAP_TOUCH, 8,
                                "bitisik dokunma hedefleri arasi bosluk 8dp'den az")

    def test_row_height_allows_two_lines_plus_touch(self):
        self.assertGreaterEqual(mobile_theme.H_ROW, self.MIN_TOUCH)


class TestNoDeadFletApis(unittest.TestCase):
    """Sessizce hiçbir şey yapmayan Flet API'leri kaynağa geri sızmamalı.

    Flet 0.86'da bunların hiçbiri hata vermez; yalnızca ölü nitelik yaratır ve
    özellik sessizce çalışmaz. Ancak kaynak düzeyinde yakalanabilirler.
    """

    def test_views_do_not_assign_page_snack_bar(self):
        for path in VIEW_FILES:
            with self.subTest(file=os.path.basename(path)):
                self.assertNotRegex(
                    read_source(path), r"page\.snack_bar\s*=",
                    "page.snack_bar atamasi Flet 0.86'da hicbir sey yapmaz; "
                    "widgets.snack() kullanin")

    def test_views_do_not_assign_page_dialog(self):
        for path in VIEW_FILES:
            with self.subTest(file=os.path.basename(path)):
                self.assertNotRegex(
                    read_source(path), r"page\.dialog\s*=",
                    "page.dialog atamasi Flet 0.86'da hicbir sey yapmaz; "
                    "widgets.show() kullanin")

    def test_views_do_not_assign_dropdown_on_change(self):
        """`Dropdown` seçim olayı `on_select`tir; `on_change` diye alan yoktur."""
        pattern = re.compile(r"^\s*(\w*(?:dd|dropdown|opt)\w*)\.on_change\s*=",
                             re.IGNORECASE | re.MULTILINE)
        for path in VIEW_FILES:
            with self.subTest(file=os.path.basename(path)):
                self.assertIsNone(
                    pattern.search(read_source(path)),
                    "Dropdown.on_change atamasi secimi asla islemez; "
                    "on_select kullanin")

    @unittest.skipUnless(HAS_FLET, "flet kurulu degil")
    def test_dropdown_really_has_no_on_change_field(self):
        """Yasağın gerekçesi: alanın gerçekten olmadığını doğrula."""
        import flet as ft
        self.assertFalse(hasattr(ft.Dropdown(options=[]), "on_change"))
        self.assertTrue(hasattr(ft.Dropdown(options=[]), "on_select"))


class TestNoEmojiAsIcons(unittest.TestCase):
    """Emoji ikon yerine kullanılmaz — ekran okuyucuda gürültü, platformda tutarsız."""

    # Piktografik bloklar: emoji, teknik semboller (⏱ ⏸ ⏳), geometrik sekiller
    # (▶ ⏹), dingbat'ler (✅ ⚡) ve varyasyon seciciler. Ok isaretleri (U+2190
    # blogu) bilerek disaridadir — dosya icindeki duz yazida `->` yerine `→`
    # kullanmak ikon degil, tipografidir.
    EMOJI = re.compile(
        "[\U0001F300-\U0001FAFF"
        "⌀-⏿"
        "■-◿"
        "☀-➿"
        "⬀-⯿"
        "️]")

    def test_view_sources_are_emoji_free(self):
        for path in VIEW_FILES:
            source = read_source(path)
            found = sorted(set(self.EMOJI.findall(source)))
            with self.subTest(file=os.path.basename(path)):
                self.assertEqual(
                    [], found,
                    f"emoji ikon olarak kullanilmis: {found} — ft.Icons kullanin")


@unittest.skipUnless(HAS_FLET, "flet kurulu degil; arayuz testleri atlaniyor")
class TestWidgetLibrary(unittest.TestCase):
    """Bileşen kitaplığı gerçek Flet API'siyle kurulabiliyor."""

    def setUp(self):
        import widgets
        self.W = widgets

    def test_every_component_constructs(self):
        import flet as ft
        W = self.W
        builders = {
            "card": lambda: W.card(W.label("x")),
            "tile": lambda: W.tile(W.label("x")),
            "divider": W.divider,
            "label": lambda: W.label("x", mono=True),
            "section_label": lambda: W.section_label("son indirilenler"),
            "page_title": lambda: W.page_title("Film", ft.Icons.MOVIE_ROUNDED),
            "link": lambda: W.link("Değiştir", lambda: None),
            "meta_chip": lambda: W.meta_chip("1080p"),
            "badge": lambda: W.badge("HAZIR"),
            "status_dot": W.status_dot,
            "stat_tile": lambda: W.stat_tile("Hız", "0 MB/s"),
            "step_hint": lambda: W.step_hint(["a", "b", "c"]),
            "primary_button": lambda: W.primary_button("Çözümle"),
            "success_button": lambda: W.success_button("İndir"),
            "ghost_button": lambda: W.ghost_button("Yapıştır"),
            "danger_button": lambda: W.danger_button("İptal"),
            "warning_button": lambda: W.warning_button("Duraklat"),
            "purple_button": lambda: W.purple_button("Dönüştür"),
            "icon_button": lambda: W.icon_button(ft.Icons.REFRESH_ROUNDED),
            "text_field": lambda: W.text_field("Link", "https://"),
            "dropdown": lambda: W.dropdown("Format", []),
            "progress_bar": lambda: W.progress_bar(0.5),
            "toggle": lambda: W.toggle(True),
            "PillGroup": lambda: W.PillGroup(["a", "b"]),
            "Collapsible": lambda: W.Collapsible("Gelişmiş"),
            "list_row": lambda: W.list_row("T", "meta"),
            "setting_row": lambda: W.setting_row("A", "b"),
            "empty_state": lambda: W.empty_state(ft.Icons.FOLDER_OFF_ROUNDED, "Boş"),
            "log_strip": lambda: W.log_strip(W.label("log")),
            "screen": lambda: W.screen([W.label("x")]),
        }
        for name, builder in builders.items():
            with self.subTest(component=name):
                self.assertIsNotNone(builder())

    def test_icon_buttons_hold_android_touch_size(self):
        import flet as ft
        button = self.W.icon_button(ft.Icons.REFRESH_ROUNDED)
        self.assertGreaterEqual(button.width, 48)
        self.assertGreaterEqual(button.height, 48)

    def test_upper_tr_handles_turkish_dotted_i(self):
        self.assertEqual("SON İNDİRİLENLER", self.W.upper_tr("son indirilenler"))
        self.assertEqual("IŞIK", self.W.upper_tr("ışık"))

    def test_elide_keeps_short_text_and_truncates_long(self):
        self.assertEqual("kısa", self.W.elide("kısa", 10))
        self.assertEqual(10, len(self.W.elide("a" * 40, 10)))

    def test_pill_group_selection_contract(self):
        chosen = []
        group = self.W.PillGroup(["1080p (1042 Parça)", "720p", "480p"],
                                 on_select=chosen.append)
        self.assertEqual("1080p (1042 Parça)", group.get())
        self.assertEqual(0, group.index)
        group._pick(2)
        self.assertEqual("480p", group.get())
        self.assertEqual(["480p"], chosen)

    def test_pill_group_set_accepts_unknown_value(self):
        group = self.W.PillGroup(["a", "b"])
        group.set("c")
        self.assertEqual("c", group.get())
        self.assertIn("c", group.values)

    def test_pill_group_splits_label_and_subtitle(self):
        # Bastaki emoji atilir, parantez icindeki kisim alt metne gecer.
        self.assertEqual(("1080p", "1042 Parça"),
                         self.W.PillGroup._split("🎬 1080p (1042 Parça)"))
        self.assertEqual(("Türkçe dublaj", ""),
                         self.W.PillGroup._split("Türkçe dublaj"))

    def test_collapsible_toggles_body_visibility(self):
        panel = self.W.Collapsible("Gelişmiş", body_controls=[self.W.label("x")])
        self.assertFalse(panel.expanded)
        self.assertFalse(panel.body.visible)
        panel.toggle()
        self.assertTrue(panel.expanded)
        self.assertTrue(panel.body.visible)

    def test_empty_pill_group_shows_placeholder_not_crash(self):
        group = self.W.PillGroup([], empty_text="Kalite bulunamadı")
        self.assertEqual("", group.get())
        self.assertEqual(-1, group.index)

    def test_custom_controls_do_not_shadow_flet_internals(self):
        """Kontrol alt sınıfları Flet'in iç depolama adlarını ezmemeli.

        Flet her kontrol örneğinde `_values`, `_c`, `_i`, `_dirty` ve
        `_internals` adlarını kendisi kullanır. Bir alt sınıf bunlardan birine
        yazarsa hata kurulum anında değil, sayfa çizilirken Flet'in içinde
        alakasız görünen bir `AttributeError` olarak patlar — `PillGroup`
        `_values` adını aldığında tam olarak bu oldu ve mock tabanlı testler
        bunu göremedi.
        """
        import flet as ft

        reserved = {name for name in vars(ft.Column()) if name.startswith("_")}
        reserved |= {name for name in vars(ft.Container()) if name.startswith("_")}
        self.assertIn("_values", reserved, "Flet ic depolama adlari degismis")

        instances = {
            "PillGroup": self.W.PillGroup(["a", "b"]),
            "Collapsible": self.W.Collapsible("Gelişmiş",
                                              body_controls=[self.W.label("x")]),
        }
        for name, instance in instances.items():
            base_type = type(instance).__mro__[1]
            expected = {n for n in vars(base_type()) if n.startswith("_")}
            for attribute in expected:
                with self.subTest(control=name, attribute=attribute):
                    self.assertIsInstance(
                        getattr(instance, attribute), type(getattr(base_type(),
                                                                  attribute)),
                        f"{name}.{attribute} Flet'in ic depolamasini eziyor")


@unittest.skipUnless(HAS_FLET, "flet kurulu degil; arayuz testleri atlaniyor")
class TestViewContracts(unittest.TestCase):
    """Ekranlar kurulur ve kabuğun beklediği yöntemleri sunar."""

    def setUp(self):
        from mobile_engine import MobileDownloadController
        self.controller = MobileDownloadController()
        self.page = MagicMock()
        self.page.get_clipboard = MagicMock(return_value="https://example.test")
        self.page.services = []
        self.page.run_task = MagicMock()

    def test_all_views_build(self):
        from views.film_view import build_film_view
        from views.social_view import build_social_view
        from views.queue_view import build_queue_view
        from views.converter_view import build_converter_view
        from views.downloads_view import build_downloads_view
        from views.settings_view import build_settings_view

        for name, builder in (
            ("film", build_film_view), ("social", build_social_view),
            ("queue", build_queue_view), ("converter", build_converter_view),
            ("downloads", build_downloads_view), ("settings", build_settings_view),
        ):
            with self.subTest(view=name):
                self.assertIsNotNone(builder(self.page, self.controller))

    def test_router_keyword_matches_view_signature(self):
        """`switch_to_tab` `auto_resolve=` gönderir; görünümler onu kabul etmeli.

        Anahtar sözcük adı `auto_res` iken her Akıllı Yönlendirici devri
        `TypeError` ile düşüyordu ve bu, görünümü yalnızca kuran bir testte
        görünmüyordu.
        """
        from views.film_view import build_film_view
        from views.social_view import build_social_view

        for name, builder in (("film", build_film_view),
                              ("social", build_social_view)):
            with self.subTest(view=name):
                view = builder(self.page, self.controller)
                self.assertTrue(hasattr(view, "set_url"))
                view.set_url("https://example.test/media", auto_resolve=False)

    def test_downloads_and_converter_expose_refresh_hooks(self):
        from views.downloads_view import build_downloads_view
        from views.converter_view import build_converter_view

        downloads = build_downloads_view(self.page, self.controller)
        self.assertTrue(callable(downloads.refresh_downloads))
        converter = build_converter_view(self.page, self.controller)
        self.assertTrue(callable(converter.refresh_files))

    def test_controller_ui_hooks_default_to_none(self):
        """`nav_handler` bağlanmadan `switch_tab` çağrılırsa çökmemeli."""
        self.assertIsNone(self.controller.nav_handler)
        self.assertIsNone(self.controller.status_handler)
        self.controller.switch_tab(2)  # AttributeError vermemeli

    def test_status_handler_receives_state_transitions(self):
        seen = []
        self.controller.status_handler = seen.append
        self.controller.start_download_session("test")
        self.controller.pause_download()
        self.controller.resume_download()
        self.controller.cancel_current_download(cleanup=False)
        self.assertEqual(["DOWNLOADING", "PAUSED", "DOWNLOADING", "CANCELLED"], seen)

    def test_status_handler_error_does_not_break_download(self):
        def explode(_state):
            raise RuntimeError("cizim hatasi")

        self.controller.status_handler = explode
        self.controller.start_download_session("test")  # yutulmali
        self.assertTrue(self.controller.is_downloading)


@unittest.skipUnless(HAS_FLET, "flet kurulu degil; arayuz testleri atlaniyor")
class TestShell(unittest.TestCase):
    """Uygulama kabuğu (app bar, gezinme çubuğu, ayarlar) kurulur."""

    def test_main_builds_shell(self):
        shell = load_mobile_shell()

        page = MagicMock()
        page.get_clipboard = MagicMock(return_value="https://example.test")
        page.services = []
        page.run_task = MagicMock()

        shell.main(page)

        self.assertIsNotNone(page.appbar)
        self.assertEqual(len(shell.NAV_PAGES), len(page.navigation_bar.destinations))
        self.assertEqual(
            [text for text, _, _ in shell.NAV_PAGES],
            [d.label for d in page.navigation_bar.destinations])

    def test_every_controller_state_has_a_status_label(self):
        shell = load_mobile_shell()
        for state in ("IDLE", "DOWNLOADING", "PAUSED", "COMPLETED",
                      "CANCELLED", "ERROR"):
            with self.subTest(state=state):
                self.assertIn(state, shell.STATUS_LABELS)


if __name__ == "__main__":
    unittest.main()
