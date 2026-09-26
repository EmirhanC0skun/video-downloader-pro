import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Headless / CI ortam tespiti.
#
# NOT: Burada bilerek bir Tk kökü OLUŞTURULUP YOK EDİLMEZ. Önceki sürüm bir
# yoklama kökü açıp `destroy()` ediyor, ardından setUpClass ikinci bir kök
# kuruyordu. Windows'ta bir Tcl yorumlayıcısı sonlandırıldıktan sonra aynı süreçte
# yenisini kurmak kırılgandır ve rastgele şu hatayı üretir:
#     couldn't read file "...tcl8.6/init.tcl": No error
# Yalnızca import edilebilirlik kontrol edilir; asıl kök tek sefer setUpClass'ta
# oluşturulur ve başarısız olursa hata değil ATLAMA üretilir.
HAS_DISPLAY = True
try:
    import tkinter  # noqa: F401
    import customtkinter as ctk
    from gui import VideoDownloaderGUI
except Exception:
    HAS_DISPLAY = False


@unittest.skipUnless(HAS_DISPLAY, "GUI display or customtkinter not available; skipping GUI tests")
class TestGUIUserExperience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_DISPLAY:
            raise unittest.SkipTest("No GUI display available")
        cls.patcher_info = patch("tkinter.messagebox.showinfo")
        cls.patcher_warn = patch("tkinter.messagebox.showwarning")
        cls.patcher_err = patch("tkinter.messagebox.showerror")
        cls.patcher_ask = patch("tkinter.messagebox.askyesno", return_value=True)
        cls.mock_info = cls.patcher_info.start()
        cls.mock_warn = cls.patcher_warn.start()
        cls.mock_err = cls.patcher_err.start()
        cls.mock_ask = cls.patcher_ask.start()

        import customtkinter as ctk
        from gui import VideoDownloaderGUI

        cls.ctk = ctk
        try:
            cls.app = VideoDownloaderGUI()
            cls.app.withdraw()
            cls.app.update()
        except Exception as exc:
            # Görüntü sunucusu / Tcl kullanılamıyorsa hata değil atlama üret.
            for name in ("patcher_info", "patcher_warn", "patcher_err", "patcher_ask"):
                if hasattr(cls, name):
                    getattr(cls, name).stop()
            raise unittest.SkipTest(f"Tk penceresi oluşturulamadı: {exc}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'patcher_info'):
            cls.patcher_info.stop()
            cls.patcher_warn.stop()
            cls.patcher_err.stop()
            cls.patcher_ask.stop()
        if hasattr(cls, 'app'):
            try:
                cls.app.destroy()
            except Exception:
                pass

    def test_01_initial_window_and_theme_setup(self):
        """User Experience: Window title, dark theme, sidebar navigation."""
        self.assertIn("Video Downloader Pro", self.app.title())
        self.assertEqual(self.ctk.get_appearance_mode(), "Dark")
        # Sekmeli duzenin yerini sol menu yonlendiricisi aldi.
        self.assertEqual(len(self.app.nav), 6)
        self.assertEqual(set(self.app.pages),
                         {"film", "social", "queue", "library", "converter", "settings"})
        self.assertEqual(self.app.current_page, "film")
        # Ust cubuk rozetinin yerini sidebar'daki canli durum karti aldi.
        self.assertEqual(self.app.status_card._title.cget("text"), "Hazır")
        self.assertIsNotNone(self.app.status_card)

    def test_02_film_tab_empty_url_validation(self):
        """UX Flow: User clicks 'Çözümle' with empty URL -> Friendly warning."""
        self.app.entry_film_page.delete(0, "end")
        self.app._resolve_film_threaded()
        self.app.update()
        self.mock_warn.assert_called()

    def test_03_film_tab_paste_and_clear_buttons(self):
        """UX Flow: Paste and clear text in Film tab."""
        self.app.entry_film_page.delete(0, "end")
        self.app.entry_film_page.insert(0, "https://testsite.com/watch/123")
        self.assertEqual(self.app.entry_film_page.get(), "https://testsite.com/watch/123")
        self.app.entry_film_page.delete(0, "end")
        self.assertEqual(self.app.entry_film_page.get(), "")

    def test_04_film_tab_cancel_resets_ui_to_zero(self):
        """UX Flow: Cancel resets progress bar, labels, and restores start button."""
        self.app.is_downloading = True
        self.app.progress_bar.set(0.65)
        self.app.lbl_progress_text.configure(text="65%")
        
        self.app._cancel_download()
        self.app.update()
        
        self.assertFalse(self.app.is_downloading)
        self.assertEqual(self.app.progress_bar.get(), 0.0)
        self.assertEqual(self.app.lbl_progress_text.cget("text"), "0%")
        self.assertEqual(self.app.btn_cancel.cget("state"), "disabled")
        self.assertEqual(self.app.btn_start.cget("state"), "normal")

    def test_05_film_tab_pause_preserves_ui_progress(self):
        """UX Flow: Pause preserves progress bar ratio and toggles button to 'Devam Et'."""
        self.app.is_downloading = True
        self.app.is_paused = False
        self.app.progress_bar.set(0.42)
        
        self.app._toggle_pause_download()
        self.app.update()
        
        self.assertTrue(self.app.is_paused)
        self.assertEqual(self.app.progress_bar.get(), 0.42)
        self.assertIn("Devam Et", self.app.btn_pause.cget("text"))
        
        self.app.is_downloading = False
        self.app.is_paused = False

    def test_06_queue_tab_add_remove_clear(self):
        """UX Flow: Adding items to queue, updating badge, and clearing queue."""
        self.app.entry_queue_url.delete(0, "end")
        self.app.entry_queue_url.insert(0, "https://testsite.com/video1")
        self.app._add_to_queue()
        self.app.update()
        
        self.assertEqual(len(self.app.download_queue), 1)
        self.assertEqual(self.app.download_queue[0]["url"], "https://testsite.com/video1")
        
        self.app._clear_queue()
        self.app.update()
        self.assertEqual(len(self.app.download_queue), 0)

    def test_07_youtube_tab_format_options(self):
        """UX Flow: YouTube tab quality and format dropdown."""
        self.app.opt_yt_format.set("🎬 1080p Full HD")
        self.assertEqual(self.app.opt_yt_format.get(), "🎬 1080p Full HD")
        self.app.opt_yt_format.set("🎵 Sadece Ses (MP3 320k)")
        self.assertEqual(self.app.opt_yt_format.get(), "🎵 Sadece Ses (MP3 320k)")

    def test_08_history_tab_refresh_and_clear(self):
        """UX Flow: History tab loads, refreshes, and clears records."""
        self.app._refresh_history_ui()
        self.app.update()
        self.app._clear_history_ui()
        self.app.update()

    def test_09_converter_tab_format_selection(self):
        """UX Flow: Media converter format options (MP3, AAC, WAV, FLAC, M4A)."""
        self.app.opt_conv_fmt.set("MP3 (320kbps)")
        self.assertEqual(self.app.opt_conv_fmt.get(), "MP3 (320kbps)")
        self.app.opt_conv_fmt.set("AAC (256kbps)")
        self.assertEqual(self.app.opt_conv_fmt.get(), "AAC (256kbps)")

    def test_10_film_tab_curl_auto_detection_and_parsing(self):
        """UX Flow: User pastes a raw cURL command into Film tab -> auto-detected and parsed."""
        raw_curl = "curl 'https://site.com/stream/index.m3u8' -H 'Referer: https://site.com/' -H 'User-Agent: Mozilla/5.0'"
        self.app.entry_film_page.delete(0, "end")
        self.app.entry_film_page.insert(0, raw_curl)
        self.app._resolve_film_threaded()
        self.app.update()
        
        self.assertEqual(self.app.entry_film_page.get(), "https://site.com/stream/index.m3u8")
        self.assertIn("Referer", self.app.custom_headers)

    def test_11_film_tab_multi_audio_dropdown_selection(self):
        """UX Flow: Selecting between Dual-Audio, Turkish, and English tracks."""
        tracks = ["🇹🇷 Dublaj (850 Parça)", "🇬🇧 Altyazılı (850 Parça)", "🌟 Çift Sesli (Dublaj + İngilizce) [Tek MP4]"]
        self.app.opt_audio_track.configure(values=tracks)
        self.app.opt_audio_track.set(tracks[2])
        self.assertEqual(self.app.opt_audio_track.get(), "🌟 Çift Sesli (Dublaj + İngilizce) [Tek MP4]")

    def test_12_series_scanner_season_and_episode_generation(self):
        """UX Flow: Scanner generates sequential episode URLs from season inputs."""
        self.app.entry_queue_url.delete(0, "end")
        self.app.entry_queue_url.insert(0, "https://dizisite.com/dizi/breaking-bad-1-sezon-1-bolum")
        self.app.entry_start_ep.delete(0, "end")
        self.app.entry_start_ep.insert(0, "1")
        self.app.entry_end_ep.delete(0, "end")
        self.app.entry_end_ep.insert(0, "3")
        
        self.app._add_range_to_queue()
        self.app.update()
        self.assertEqual(len(self.app.download_queue), 3)
        self.app._clear_queue()

    def test_13_youtube_tab_browser_cookie_selection(self):
        """UX Flow: Browser cookie selection (Chrome, Brave, Edge, Firefox)."""
        self.app.opt_yt_cookies.set("🌐 Chrome Oturumu")
        self.assertEqual(self.app.opt_yt_cookies.get(), "🌐 Chrome Oturumu")
        self.app.opt_yt_cookies.set("🌐 Brave Oturumu")
        self.assertEqual(self.app.opt_yt_cookies.get(), "🌐 Brave Oturumu")

    def test_14_media_converter_format_and_bitrate_selection(self):
        """UX Flow: Media converter format options (MP3 320k, MP3 192k, WAV)."""
        self.app.opt_conv_fmt.set("MP3 (320 kbps Yüksek)")
        self.assertEqual(self.app.opt_conv_fmt.get(), "MP3 (320 kbps Yüksek)")
        self.app.opt_conv_fmt.set("WAV (Kayıpsız)")
        self.assertEqual(self.app.opt_conv_fmt.get(), "WAV (Kayıpsız)")

    def test_15_pause_and_resume_ui_button_transition(self):
        """UX Flow: Start -> Pause (Disabled start, Enabled Devam Et) -> Devam Et (Enabled pause, Disabled start)."""
        self.app.is_downloading = True
        self.app.is_paused = False
        self.app.progress_bar.set(0.50)
        
        # 1. Duraklat
        self.app._toggle_pause_download()
        self.app.update()
        self.assertTrue(self.app.is_paused)
        self.assertIn("Devam Et", self.app.btn_pause.cget("text"))
        self.assertEqual(self.app.btn_cancel.cget("state"), "normal")
        
        # 2. _reset_ui tetiklendiğinde (thread bittiğinde) duraklatılmış durumun bozulmadığını doğrula
        self.app._reset_ui(False, "İndirme duraklatıldı.")
        self.app.update()
        self.assertTrue(self.app.is_paused)
        self.assertIn("Devam Et", self.app.btn_pause.cget("text"))
        
        # 3. İptal Et
        self.app._cancel_download()
        self.app.update()
        self.assertFalse(self.app.is_paused)
        self.assertFalse(self.app.is_downloading)
        self.assertEqual(self.app.progress_bar.get(), 0.0)
        self.assertEqual(self.app.btn_start.cget("state"), "normal")

    def test_16_rapid_button_spam_resilience(self):
        """UX Resilience: User clicks Start, Pause, and Cancel buttons 20 times rapidly."""
        for _ in range(20):
            self.app.is_downloading = True
            self.app.is_paused = False
            self.app._toggle_pause_download()
            self.app._toggle_pause_download()
            self.app._cancel_download()
            self.app.update()
        
        self.assertFalse(self.app.is_downloading)
        self.assertEqual(self.app.progress_bar.get(), 0.0)

    # =====================================================================
    # YENİ ARAYÜZ: YÖNLENDİRİCİ VE DURUM MAKİNESİ
    # =====================================================================
    def test_17_sidebar_router_switches_pages(self):
        """UX Flow: Sidebar navigation shows one page and marks it active."""
        for key in ("social", "queue", "library", "converter", "settings", "film"):
            self.app._show_page(key)
            self.app.update()
            self.assertEqual(self.app.current_page, key)
            # Pencere test sirasinda withdraw() edildigi icin winfo_ismapped()
            # her zaman 0 doner; gorunurluk grid yoneticisinden okunur.
            self.assertTrue(self.app.pages[key].grid_info())
            for other in self.app.pages:
                if other != key:
                    self.assertFalse(self.app.pages[other].grid_info(),
                                     f"{other} sayfasi {key} secilikken gorunur kaldi")

    def test_18_sidebar_router_updates_header(self):
        """UX Flow: Header title and subtitle follow the selected page."""
        self.app._show_page("converter")
        self.app.update()
        self.assertEqual(self.app.lbl_page_title.cget("text"), "Dönüştürücü")
        self.assertEqual(self.app.lbl_page_sub.cget("text"), "Videodan ses çıkar")

    def test_19_film_state_machine_shows_one_state(self):
        """UX Flow: Film page exposes exactly one of idle/resolved/downloading."""
        for state in ("bos", "cozumlendi", "indiriliyor", "bos"):
            self.app._show_page("film")
            self.app._set_film_state(state)
            self.app.update()
            self.assertEqual(self.app._film_state, state)
            visible = [name for name, frame in self.app.film_states.items()
                       if frame.grid_info()]
            self.assertEqual(visible, [state])

    def test_20_download_start_switches_to_downloading_state(self):
        """UX Flow: Starting a download moves the film page to its progress view."""
        self.app._show_page("film")
        self.app._set_film_state("cozumlendi")
        self.app._begin_download_ui("İndiriliyor", keep_progress=False)
        self.app.update()
        self.assertEqual(self.app._film_state, "indiriliyor")
        self.assertEqual(self.app.btn_cancel.cget("state"), "normal")
        self.app._cancel_download()
        self.app.update()

    def test_21_cancel_returns_to_resolved_state(self):
        """UX Flow: After cancelling, the resolved card comes back."""
        self.app._show_page("film")
        self.app.resolved_film_data = {"title": "Test", "total_segments": 10}
        self.app._set_film_state("indiriliyor")
        self.app.is_downloading = True
        self.app.is_paused = False
        self.app._reset_ui(False, "iptal edildi")
        self.app.update()
        self.assertEqual(self.app._film_state, "cozumlendi")

    def test_22_option_pills_keep_option_menu_contract(self):
        """UX Contract: Quality/audio pills answer get/set/configure like a menu."""
        self.app.opt_quality.configure(values=["🎬 1080p (1.9 GB)", "📺 720p (1.1 GB)"])
        self.assertEqual(self.app.opt_quality.get(), "🎬 1080p (1.9 GB)")
        self.app.opt_quality.set("📺 720p (1.1 GB)")
        self.assertEqual(self.app.opt_quality.get(), "📺 720p (1.1 GB)")
        self.assertEqual(len(self.app.opt_quality.cget("values")), 2)

    def test_23_queue_badge_tracks_pending_items(self):
        """UX Flow: Sidebar queue badge reflects pending downloads."""
        self.app.download_queue = []
        self.app._refresh_queue_ui()
        self.app.update()
        self.assertFalse(self.app.nav["queue"]._badge.grid_info(),
                         "kuyruk bosken rozet gorunur kalmamali")
        self.app.download_queue = [
            {"id": 1, "title": "A", "url": "https://a", "status": "Sırada", "type": "film"},
            {"id": 2, "title": "B", "url": "https://b", "status": "Sırada", "type": "film"},
        ]
        self.app._refresh_queue_ui()
        self.app.update()
        self.assertTrue(self.app.nav["queue"]._badge.grid_info())
        self.assertEqual(self.app.nav["queue"]._badge.cget("text"), "2")
        self.app.download_queue = []
        self.app._refresh_queue_ui()

    def test_24_shutdown_cancels_pending_tk_callbacks(self):
        """Window teardown must not leave Tcl commands queued after destroy."""
        self.app.after(60_000, lambda: None)
        self.app.destroy()
        self.assertTrue(self.app._destroying)


if __name__ == "__main__":
    unittest.main()
