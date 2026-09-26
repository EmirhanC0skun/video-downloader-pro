"""`ui/` sunum katmanı testleri.

Paket bilinçli olarak motordan ve iş mantığından ayrıdır, bu yüzden doğrudan
test edilebilir. `theme` ve `icons` saf veridir ve ekran gerektirmez; bu
testler ekransız ortamda da çalışır. Widget testleri Tk kökü ister ve kök
kurulamıyorsa atlanır.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import icons, theme

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

HAS_DISPLAY = True
try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.withdraw()
    _probe.update()
    _probe.destroy()
    import customtkinter as ctk

    from ui import fonts, widgets
except Exception:
    HAS_DISPLAY = False


class TestThemeTokens(unittest.TestCase):
    """Belirteçlerin biçim ve tutarlılık denetimi."""

    def test_every_color_token_is_valid_hex(self):
        colors = theme.all_colors()
        self.assertGreater(len(colors), 25, "belirtec tablosu beklenenden kucuk")
        for name, value in colors.items():
            self.assertRegex(value, HEX, f"{name} gecerli bir hex renk degil: {value}")

    def test_over_flattens_alpha_against_base(self):
        """Tkinter alfa bilmez; katmanlar zemine göre düzleştirilir."""
        # alpha=0 zemini, alpha=1 katmani verir.
        self.assertEqual(theme.over("#FFFFFF", "#11151F", 0.0), "#11151f")
        self.assertEqual(theme.over("#FFFFFF", "#11151F", 1.0), "#ffffff")
        # Tasarimdaki rgba(255,255,255,.06) kart kenarligi.
        self.assertEqual(theme.over("#FFFFFF", "#11151F", 0.06), theme.BORDER)

    def test_over_rejects_alpha_outside_range(self):
        with self.assertRaises(ValueError):
            theme.over("#FFFFFF", "#000000", 1.5)

    def test_over_rejects_malformed_color(self):
        with self.assertRaises(ValueError):
            theme.over("#FFF", "#000000", 0.5)

    def test_derived_borders_are_lighter_than_their_base(self):
        """Kenarlık zemininden ayırt edilebilir olmalı, yoksa kart sınırı kaybolur."""
        for border, base in ((theme.BORDER, theme.BG_CARD),
                             (theme.BORDER_STRONG, theme.BG_APP),
                             (theme.BORDER_SIDEBAR, theme.BG_SIDEBAR)):
            self.assertGreater(sum(theme._rgb(border)), sum(theme._rgb(base)))

    def test_font_families_cover_design_weights(self):
        self.assertEqual(sorted(theme.FONT_UI), [500, 600, 700, 800])
        self.assertEqual(sorted(theme.FONT_MONO), [500, 600])


class TestIconMapping(unittest.TestCase):
    def test_every_glyph_is_a_single_character(self):
        self.assertGreater(len(icons.GLYPHS), 40)
        for name, value in icons.GLYPHS.items():
            self.assertEqual(len(value), 1, f"{name} tek glyph olmali: {value!r}")

    def test_glyphs_live_in_the_private_use_area(self):
        """Material Symbols glyph'leri PUA aralığındadır (U+E000–U+F8FF)."""
        for name, value in icons.GLYPHS.items():
            self.assertTrue(0xE000 <= ord(value) <= 0xF8FF,
                            f"{name} PUA disinda: U+{ord(value):04X}")

    def test_unknown_icon_name_raises(self):
        """Yazım hatası sessizce boş glyph'e düşmemeli."""
        with self.assertRaises(KeyError):
            icons.glyph("boyle_bir_ikon_yok")

    def test_fallback_text_used_when_icon_font_missing(self):
        self.assertEqual(icons.text("download", has_icon_font=False), "v")
        self.assertEqual(icons.text("download", has_icon_font=True),
                         icons.GLYPHS["download"])

    def test_fallback_keys_are_all_real_icons(self):
        for name in icons.FALLBACK:
            self.assertIn(name, icons.GLYPHS, f"{name} icin glyph yok")

    def test_navigation_icons_exist(self):
        """Sidebar'ın altı sayfası da bir glyph bulabilmeli."""
        for name in ("film", "social", "queue", "library", "convert", "settings"):
            self.assertEqual(len(icons.glyph(name)), 1)


@unittest.skipUnless(HAS_DISPLAY, "Tk display yok; widget testleri atlaniyor")
class TestWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fonts.load()
        ctk.set_appearance_mode("Dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()
        fonts.detect_families()
        cls.host = ctk.CTkFrame(cls.root)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_upper_tr_uses_turkish_dotted_capital(self):
        """`str.upper()` 'i' harfini 'I' yapar; Türkçe'de doğrusu 'İ'."""
        self.assertEqual(widgets.upper_tr("son indirilenler"), "SON İNDİRİLENLER")
        self.assertEqual(widgets.upper_tr("çıktı biçimi"), "ÇIKTI BİÇİMİ")
        self.assertEqual(widgets.upper_tr("hız"), "HIZ")

    def test_elide_shortens_only_when_needed(self):
        self.assertEqual(widgets.elide("kısa", 10), "kısa")
        self.assertTrue(widgets.elide("çok uzun bir başlık", 8).endswith("…"))
        self.assertLessEqual(len(widgets.elide("çok uzun bir başlık", 8)), 8)

    def test_pill_group_selects_one_at_a_time(self):
        picked = []
        group = widgets.PillGroup(self.host, ["1080p", "720p", "480p"],
                                  command=lambda i, t: picked.append(t))
        self.root.update()
        self.assertEqual(group.value(), "1080p")
        group.select(2)
        self.assertEqual(group.value(), "480p")
        self.assertEqual(picked, ["480p"])
        selected = [p for p in group._pills if p.selected]
        self.assertEqual(len(selected), 1)

    def test_segmented_control_reports_selection(self):
        seen = []
        seg = widgets.Segmented(self.host, ["Dengeli", "Otomatik", "Turbo"],
                                command=lambda i, t: seen.append(t), selected=1)
        self.root.update()
        self.assertEqual(seg.value(), "Otomatik")
        seg.select(2)
        self.assertEqual(seg.value(), "Turbo")
        self.assertEqual(seen, ["Turbo"])

    def test_toggle_round_trips_its_value(self):
        toggle = widgets.Toggle(self.host, value=True)
        self.root.update()
        self.assertTrue(toggle.value())
        toggle.set_value(False)
        self.assertFalse(toggle.value())

    def test_collapsible_hides_body_when_closed(self):
        panel = widgets.Collapsible(self.host, "Gelişmiş")
        self.root.update()
        self.assertFalse(panel.expanded)
        self.assertFalse(panel.body.grid_info(), "kapali panel yer kaplamamali")
        panel.toggle()
        self.root.update()
        self.assertTrue(panel.expanded)
        self.assertTrue(panel.body.grid_info())

    def test_collapsible_body_widgets_survive_collapse(self):
        """Kapalı panel gövdeyi yok etmez; arka plan güncellemeleri hedefini bulur."""
        panel = widgets.Collapsible(self.host, "Günlük", expanded=True)
        child = widgets.label(panel.body, "satır")
        child.grid(row=0, column=0)
        panel.set_expanded(False)
        self.root.update()
        child.configure(text="yeni satır")
        self.assertEqual(child.cget("text"), "yeni satır")

    def test_sidebar_item_badge_hides_on_zero(self):
        item = widgets.SidebarItem(self.host, "queue", "Kuyruk")
        item.grid()
        self.root.update()
        self.assertFalse(item._badge.grid_info())
        item.set_badge(3)
        self.root.update()
        self.assertTrue(item._badge.grid_info())
        self.assertEqual(item._badge.cget("text"), "3")
        item.set_badge(0)
        self.root.update()
        self.assertFalse(item._badge.grid_info())

    def test_status_card_reflects_download_state(self):
        card = widgets.StatusCard(self.host)
        self.root.update()
        card.set_status("İndiriliyor · %46", "24.6 MB/s", theme.PRIMARY)
        self.assertIn("İndiriliyor", card._title.cget("text"))
        self.assertEqual(card._dot.cget("fg_color"), theme.PRIMARY)

    def test_stat_tile_updates_value_only(self):
        tile = widgets.StatTile(self.host, "hız", "0.00 MB/s")
        self.root.update()
        tile.set_value("24.6 MB/s")
        self.assertEqual(tile._value.cget("text"), "24.6 MB/s")
        self.assertEqual(tile._caption.cget("text"), "HIZ")

    # -- OptionPills: CTkOptionMenu sozlesmesi ----------------------------
    def test_option_pills_get_set_and_configure(self):
        pills = widgets.OptionPills(self.host, values=["A (1 GB)", "B (2 GB)"])
        self.root.update()
        self.assertEqual(pills.get(), "A (1 GB)")
        pills.set("B (2 GB)")
        self.assertEqual(pills.get(), "B (2 GB)")
        self.assertEqual(pills.cget("values"), ["A (1 GB)", "B (2 GB)"])

    def test_option_pills_preserve_full_value_while_shortening_label(self):
        """Motor tam dizeyi bekler; kısaltma yalnızca görünürde olmalı."""
        full = "🎬 1080p Full HD (1042 Parça)"
        pills = widgets.OptionPills(self.host, values=[full])
        self.root.update()
        self.assertEqual(pills.get(), full)
        self.assertEqual(widgets.OptionPills._split(full),
                         ("1080p Full HD", "1042 Parça"))

    def test_option_pills_configure_resets_selection(self):
        pills = widgets.OptionPills(self.host, values=["A", "B"])
        pills.set("B")
        pills.configure(values=["X", "Y", "Z"])
        self.root.update()
        self.assertEqual(pills.get(), "X")
        self.assertEqual(len(pills.cget("values")), 3)

    def test_option_pills_accepts_unknown_value_like_a_menu(self):
        """`set()` listede olmayan değeri ekler — CTkOptionMenu de böyle davranır."""
        pills = widgets.OptionPills(self.host, values=["A"])
        pills.set("Beklenmeyen")
        self.root.update()
        self.assertEqual(pills.get(), "Beklenmeyen")
        self.assertIn("Beklenmeyen", pills.cget("values"))


@unittest.skipUnless(HAS_DISPLAY, "Tk display yok")
class TestFontFallback(unittest.TestCase):
    """Gömülü fontlar olmasa da arayüz kurulabilmeli."""

    def test_ui_font_rejects_unknown_weight(self):
        with self.assertRaises(ValueError):
            fonts.ui(13, weight=123)

    def test_mono_font_rejects_unknown_weight(self):
        with self.assertRaises(ValueError):
            fonts.mono(13, weight=800)

    def test_assets_dir_points_at_bundled_fonts(self):
        self.assertTrue(fonts.assets_dir().endswith(os.path.join("assets", "fonts")))

    def test_load_is_idempotent(self):
        first = fonts.load()
        second = fonts.load()
        self.assertEqual(first["loaded"], second["loaded"])


if __name__ == "__main__":
    unittest.main()
