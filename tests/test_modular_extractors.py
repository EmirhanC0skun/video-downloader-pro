# -*- coding: utf-8 -*-
"""
Modular Extractor Architecture & Registry Unit Tests (100% Offline / Zero Network).
"""

import unittest
import os
import sys
import requests
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extractors.base import BaseExtractor, ExtractorResult
from extractors.registry import ExtractorRegistry
from extractors.direct import DirectMediaExtractor
from extractors.dailymotion import DailymotionExtractor
from extractors.series_film import SeriesFilmExtractor
from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js
from extractors.universal import UniversalYtDlpExtractor
from extractors.platforms.diziyou import DiziyouExtractor
from exceptions import ExtractorError, ISPBlockError
import extractor as extractor_facade


class DummyTestExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "Dummy Test Extractor"

    def can_handle(self, url: str) -> bool:
        return "dummy-test-video.com" in url

    def extract(self, url: str, session=None, log_callback=None) -> ExtractorResult:
        return ExtractorResult(
            success=True,
            title="Dummy Video Title",
            video_url="https://stream.dummy.com/video.m3u8",
            total_segments=10,
            direct_file=False
        )


class TestModularExtractors(unittest.TestCase):

    def test_facade_forwards_caller_session_to_registry(self):
        caller_session = object()
        registry_result = {
            "success": True,
            "title": "Android native transport",
            "video_url": "https://cdn.invalid/video.mp4",
            "direct_file": True,
            "total_segments": 1,
        }

        with patch.object(
            extractor_facade.default_registry,
            "resolve",
            return_value=registry_result,
        ) as resolver:
            result = extractor_facade.resolve_film_page(
                "https://example.invalid/watch",
                session=caller_session,
            )

        self.assertTrue(result["success"])
        resolver.assert_called_once_with(
            "https://example.invalid/watch",
            session=caller_session,
            log_callback=None,
        )

    def test_registry_reports_domain_failure_without_leaking_signed_query(self):
        class FailingExtractor(BaseExtractor):
            @property
            def name(self) -> str:
                return "Android Probe"

            def can_handle(self, url: str) -> bool:
                return "example.invalid" in url

            def extract(self, url: str, session=None, log_callback=None):
                raise ExtractorError("mobile dependency unavailable")

        registry = ExtractorRegistry()
        registry._extractors = [FailingExtractor()]
        session = MagicMock()
        session.get.return_value.status_code = 404

        with self.assertLogs("video_downloader.extractors.registry", level="INFO") as captured:
            with self.assertRaises(ExtractorError):
                registry.resolve(
                    "https://example.invalid/watch?token=secret-token",
                    session=session,
                )

        output = "\n".join(captured.output)
        self.assertIn("Android Probe", output)
        self.assertIn("example.invalid", output)
        self.assertIn("ExtractorError", output)
        self.assertIn("mobile dependency unavailable", output)
        self.assertNotIn("secret-token", output)

    def test_diziyou_uses_real_1080_playlist_when_master_aliases_every_variant_to_720(self):
        page_url = "https://www.diziyou.one/show-1-sezon-1-bolum/"
        player_url = "https://www.diziyou.one/player/42.html"
        master_orig = "https://storage.diziyou.one/episodes/42/play.m3u8"
        master_tr = "https://storage.diziyou.one/episodes/42_tr/play.m3u8"
        master_text = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1600000,RESOLUTION=1280x720
720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3600000,RESOLUTION=1920x1080
720p.m3u8
"""
        media_text = "#EXTM3U\n#EXTINF:4.0,\n1080p_000.ts\n#EXT-X-ENDLIST\n"

        def response(text, url, status=200):
            item = MagicMock()
            item.status_code = status
            item.text = text
            item.url = url
            return item

        responses = {
            page_url: response(
                '<title>Show izle</title><span id="turkceDublaj">Dublaj</span>'
                f'<iframe src="{player_url}"></iframe>',
                page_url,
            ),
            player_url: response(f'<source src="{master_orig}">', player_url),
            player_url.replace(".html", "_tr.html"): response(
                f'<source src="{master_tr}">', player_url.replace(".html", "_tr.html")
            ),
            master_orig: response(master_text, master_orig),
            master_tr: response(master_text, master_tr),
            "https://storage.diziyou.one/episodes/42/1080p.m3u8": response(
                media_text, "https://storage.diziyou.one/episodes/42/1080p.m3u8"
            ),
            "https://storage.diziyou.one/episodes/42_tr/1080p.m3u8": response(
                media_text, "https://storage.diziyou.one/episodes/42_tr/1080p.m3u8"
            ),
        }
        session = MagicMock()
        session.get.side_effect = lambda url, **_kwargs: responses.get(
            url, response("", url, status=404)
        )

        result = DiziyouExtractor().extract(page_url, session=session)

        self.assertIsNotNone(result)
        self.assertIn("/1080p_000.ts", result.video_segments[0])
        self.assertTrue(all("/1080p_000.ts" in track["segments"][0] for track in result.audio_tracks))
        self.assertEqual(result.qualities[0]["resolution"], "1920x1080")

    def test_direct_extractor_matching_and_extract(self):
        """DirectMediaExtractor accurately identifies and extracts mp4, mkv, and m3u8 URLs."""
        ext = DirectMediaExtractor()
        self.assertTrue(ext.can_handle("https://example.com/video.mp4"))
        self.assertTrue(ext.can_handle("https://example.com/movie.mkv?token=123"))
        self.assertTrue(ext.can_handle("https://example.com/master.m3u8"))
        self.assertFalse(ext.can_handle("https://diziyou.co/watch/123"))

        # Test direct file extraction
        res_mp4 = ext.extract("https://example.com/video.mp4")
        self.assertTrue(res_mp4.success)
        self.assertTrue(res_mp4.direct_file)
        self.assertEqual(res_mp4.title, "video.mp4")

        # Test direct m3u8 extraction with mocked session
        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '#EXT-X-MEDIA:TYPE=AUDIO,NAME="Turkce",URI="audio_tr.m3u8"\n#EXTINF:10.0,\nseg1.ts'
        mock_sess.get.return_value = mock_resp

        res_m3u8 = ext.extract("https://example.com/stream/master.m3u8", session=mock_sess)
        self.assertTrue(res_m3u8.success)
        self.assertEqual(len(res_m3u8.audio_tracks), 1)

    def test_dailymotion_extractor_matching_and_extract(self):
        """DailymotionExtractor identifies full and short Dailymotion URLs and queries metadata."""
        ext = DailymotionExtractor()
        self.assertTrue(ext.can_handle("https://www.dailymotion.com/video/x8abcdef"))
        self.assertTrue(ext.can_handle("https://dai.ly/x8abcdef"))
        self.assertFalse(ext.can_handle("https://youtube.com/watch?v=123"))

        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Dailymotion Test Video",
            "qualities": {"auto": [{"url": "https://dm.example.com/master.m3u8"}]}
        }
        mock_sess.get.return_value = mock_resp

        res = ext.extract("https://www.dailymotion.com/video/x8abcdef", session=mock_sess)
        self.assertIsNotNone(res)
        self.assertTrue(res.success)
        self.assertEqual(res.title, "Dailymotion Test Video")

    def test_series_film_extractor_matching_and_extract(self):
        """SeriesFilmExtractor identifies Turkish sites and extracts m3u8 playlists."""
        ext = SeriesFilmExtractor()
        self.assertTrue(ext.can_handle("https://diziyou.co/stranger-things-1-sezon-1-bolum/"))
        self.assertTrue(ext.can_handle("https://hdfilmcehennemi.life/film/oppenheimer/"))
        self.assertTrue(ext.can_handle("https://dizibox.tv/breaking-bad-1-sezon-1-bolum/"))
        self.assertFalse(ext.can_handle("https://youtube.com/watch?v=123"))

        # Test extraction
        mock_sess = MagicMock()
        mock_page_resp = MagicMock()
        mock_page_resp.status_code = 200
        mock_page_resp.text = '<html><head><title>Breaking Bad 1. Sezon 1. Bölüm</title></head><body><source src="https://cdn.example.com/master.m3u8"></body></html>'
        
        mock_m3u8_resp = MagicMock()
        mock_m3u8_resp.status_code = 200
        mock_m3u8_resp.text = '#EXT-X-MEDIA:TYPE=AUDIO,NAME="Turkce Dublaj",URI="tr.m3u8"'

        mock_sess.get.side_effect = [mock_page_resp, mock_m3u8_resp]

        res = ext.extract("https://diziyou.co/stranger-things-1-sezon-1-bolum/", session=mock_sess)
        self.assertIsNotNone(res)
        self.assertTrue(res.success)
        self.assertIn("Breaking Bad", res.title)
        self.assertEqual(len(res.audio_tracks), 1)

    def test_series_film_extractor_isp_block(self):
        """SeriesFilmExtractor detects ISP censorship pages and raises ISPBlockError."""
        ext = SeriesFilmExtractor()
        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>5651 Sayılı Kanun Uyarınca erisime_engellenmis dir. Mahkeme Karari</body></html>"
        mock_sess.get.return_value = mock_resp

        with self.assertRaises(ISPBlockError):
            ext.extract("https://diziyou.co/blocked-movie/", session=mock_sess)

    def test_series_film_extractor_unfetched_playlist(self):
        """When playlist fetch fails, total_segments safely defaults to 0 without crashing."""
        ext = SeriesFilmExtractor()
        mock_sess = MagicMock()
        mock_page_resp = MagicMock()
        mock_page_resp.status_code = 200
        mock_page_resp.text = '<html><head><title>Test Film</title></head><body><source src="https://cdn.example.com/master.m3u8"></body></html>'
        
        mock_sess.get.side_effect = [mock_page_resp, requests.RequestException("404 Not Found")]

        res = ext.extract("https://diziyou.co/test-film/", session=mock_sess)
        self.assertIsNotNone(res)
        self.assertTrue(res.success)
        self.assertEqual(res.total_segments, 0)

    def test_registry_enforces_ssl_on_custom_sessions(self):
        """Registry enforces session.verify=True on caller-supplied sessions by default."""
        registry = ExtractorRegistry()
        custom_session = MagicMock()
        custom_session.verify = False  # Caller tries to pass unverified session

        dummy_ext = DummyTestExtractor()
        registry.register(dummy_ext)

        registry.resolve("https://dummy-test-video.com/watch/123", session=custom_session, allow_insecure_ssl=False)
        self.assertTrue(custom_session.verify)

        # When explicitly allowed
        registry.resolve("https://dummy-test-video.com/watch/123", session=custom_session, allow_insecure_ssl=True)
        self.assertFalse(custom_session.verify)

    def test_custom_extractor_registration_and_dispatch(self):
        """Custom extractors can be dynamically registered and dispatched without modifying core code."""
        registry = ExtractorRegistry()
        dummy_ext = DummyTestExtractor()
        registry.register(dummy_ext)

        result_dict = registry.resolve("https://dummy-test-video.com/watch/999")
        self.assertTrue(result_dict["success"])
        self.assertEqual(result_dict["title"], "Dummy Video Title")
        self.assertEqual(result_dict["video_url"], "https://stream.dummy.com/video.m3u8")

    def test_all_modular_extractors_can_handle(self):
        """Verify each modular extractor matches its designated domain and rejects unrelated ones."""
        from extractors.embeds.vidmoly import VidmolyExtractor
        from extractors.embeds.voe import VoeExtractor
        from extractors.embeds.streamwish import StreamwishExtractor
        from extractors.embeds.sibnet import SibnetExtractor
        from extractors.embeds.closeload import CloseloadExtractor
        from extractors.embeds.dplayer import DPlayerExtractor
        from extractors.embeds.mailru import MailruExtractor
        from extractors.embeds.players import PichiveExtractor, VideoparkExtractor, BiplayerExtractor, CanlitvnewsExtractor
        from extractors.platforms.dizipal import DizipalExtractor
        from extractors.platforms.dizitime import DizitimeExtractor
        from extractors.platforms.filmmodu import FilmmoduExtractor
        from extractors.platforms.dizilla import DizillaExtractor
        from extractors.platforms.jetfilmizle import JetfilmizleExtractor
        from extractors.platforms.sezonlukdizi import SezonlukdiziExtractor
        from extractors.platforms.yabancidizi import YabancidiziExtractor
        from extractors.platforms.hdfilmcehennemi import HDFilmcehennemiExtractor
        from extractors.platforms.diziyou import DiziyouExtractor
        from extractors.platforms.dizibox import DiziboxExtractor
        from extractors.platforms.anime import AnimeExtractor
        from extractors.generic import GenericMediaExtractor

        match_cases = [
            (VidmolyExtractor(), "https://vidmoly.to/embed-xyz123.html", "https://unrelated.com/"),
            (VoeExtractor(), "https://voe.sx/e/xyz123", "https://unrelated.com/"),
            (StreamwishExtractor(), "https://streamwish.to/e/sw123", "https://unrelated.com/"),
            (SibnetExtractor(), "https://video.sibnet.ru/shell.php?videoid=123", "https://unrelated.com/"),
            (CloseloadExtractor(), "https://closeload.com/embed/cl123", "https://unrelated.com/"),
            (DPlayerExtractor(), "https://dplayer77.site/v/dp123", "https://unrelated.com/"),
            (MailruExtractor(), "https://my.mail.ru/video/embed/123", "https://unrelated.com/"),
            (PichiveExtractor(), "https://pichive.com/e/pi123", "https://unrelated.com/"),
            (VideoparkExtractor(), "https://videopark.net/v/123", "https://unrelated.com/"),
            (BiplayerExtractor(), "https://bicaps.live/biplayer/vid/123", "https://unrelated.com/"),
            (CanlitvnewsExtractor(), "https://canlitv.news/stream/123", "https://unrelated.com/"),
            (DizipalExtractor(), "https://dizipal999.com/dizi/test", "https://unrelated.com/"),
            (DizitimeExtractor(), "https://dizitime.org/dizi/test-1-sezon-1-bolum", "https://unrelated.com/"),
            (FilmmoduExtractor(), "https://filmmodu.cx/film/test", "https://unrelated.com/"),
            (DizillaExtractor(), "https://dizilla.club/dizi/test", "https://unrelated.com/"),
            (JetfilmizleExtractor(), "https://jetfilmizle.cx/film/test", "https://unrelated.com/"),
            (SezonlukdiziExtractor(), "https://sezonlukdizi.net/dizi/test", "https://unrelated.com/"),
            (YabancidiziExtractor(), "https://yabancidizi.news/dizi/test", "https://unrelated.com/"),
            (HDFilmcehennemiExtractor(), "https://hdfilmcehennemi.life/film/test", "https://unrelated.com/"),
            (DiziyouExtractor(), "https://diziyou.co/dizi/test", "https://unrelated.com/"),
            (DiziboxExtractor(), "https://dizibox.tv/dizi/test", "https://unrelated.com/"),
            (AnimeExtractor(), "https://turkanime.co/anime/test", "https://unrelated.com/"),
            (GenericMediaExtractor(), "https://example.com/video.mp4", "https://example.com/page.html"),
        ]

        for ext, valid_url, invalid_url in match_cases:
            with self.subTest(extractor=ext.name):
                self.assertTrue(ext.can_handle(valid_url), f"{ext.name} should handle {valid_url}")
                self.assertFalse(ext.can_handle(invalid_url), f"{ext.name} should NOT handle {invalid_url}")

    def test_hdfilmcehennemi_referer_and_hls_resolution(self):
        """HDFilmcehennemi embeds correctly bind player URL to referer and origin headers."""
        from extractors.platforms.hdfilmcehennemi import HDFilmcehennemiExtractor
        ext = HDFilmcehennemiExtractor()

        main_html = '<html><head><title>Oppenheimer izle</title></head><body><iframe src="https://www.hdfilmcehennemi.nl/embed/oppenheimer"></iframe></body></html>'
        embed_html = '''<html><head><track kind="subtitles" label="Türkçe" src="/sub_tr.vtt"></head>
        <body><script>var s_test = "https://cdn.example.com/master.m3u8";</script>
        <iframe src="https://vidmoly.to/embed-test.html"></iframe></body></html>'''

        mock_sess = MagicMock()
        resp_main = MagicMock(status_code=200, text=main_html)
        resp_emb = MagicMock(status_code=200, text=embed_html)
        mock_sess.get.side_effect = [resp_main, resp_emb]

        with patch("extractors.platforms.hdfilmcehennemi.decode_rapidrame_script", return_value="https://cdn.example.com/stream.m3u8"), \
             patch("extractors.platforms.hdfilmcehennemi.extract_master_quality_variants", return_value=[{"url": "https://cdn.example.com/720p.m3u8"}]):
            
            resp_m3u8 = MagicMock(status_code=200, text="#EXTM3U\n#EXTINF:6.0,\nseg1.ts\nseg2.ts")
            resp_sub = MagicMock(status_code=200, text="#EXTM3U\n#EXTINF:6.0,\nseg1.ts\nseg2.ts")
            mock_sess.get.side_effect = [resp_main, resp_emb, resp_m3u8, resp_sub]

            res = ext.extract("https://hdfilmcehennemi.nl/oppenheimer-izle/", session=mock_sess)
            self.assertIsNotNone(res)
            self.assertTrue(res.success)
            self.assertEqual(res.video_headers["Referer"], "https://www.hdfilmcehennemi.nl/embed/oppenheimer")
            self.assertEqual(res.video_headers["Origin"], "https://www.hdfilmcehennemi.nl")
            self.assertEqual(res.total_segments, 2)
            self.assertFalse(res.direct_file)

    def test_hdfilmcehennemi_rejects_dead_hls_manifest_instead_of_false_success(self):
        """A decoded HLS URL is not a usable result when its manifest is gone."""
        from extractors.platforms.hdfilmcehennemi import HDFilmcehennemiExtractor

        page_url = "https://hdfilmcehennemi.nl/dead-film/"
        embed_url = "https://hdfilmcehennemi.mobi/video/embed/dead/"
        dead_manifest = "https://hls8.playmix.uno/hls/dead/master.txt"
        main_html = f'<html><title>Dead Film izle</title><iframe src="{embed_url}"></iframe></html>'
        embed_html = "<html><title>Dead player</title></html>"

        def response(text, status_code=200):
            item = MagicMock()
            item.status_code = status_code
            item.text = text
            item.__bool__.return_value = True
            return item

        def get(url, **_kwargs):
            if url == page_url:
                return response(main_html)
            if url == dead_manifest:
                return response("Not Found", status_code=404)
            if "/video/embed/dead/" in url:
                return response(embed_html)
            return response("Not Found", status_code=404)

        session = MagicMock()
        session.get.side_effect = get

        with patch(
            "extractors.platforms.hdfilmcehennemi.decode_rapidrame_script",
            return_value=dead_manifest,
        ):
            result = HDFilmcehennemiExtractor().extract(page_url, session=session)

        self.assertIsNone(result)

    def test_hdfilmcehennemi_tries_ajax_player_when_initial_embed_is_dead(self):
        """A dead default player must not hide a working AJAX mirror."""
        from extractors.platforms.hdfilmcehennemi import HDFilmcehennemiExtractor

        page_url = "https://www.hdfilmcehennemi.nl/example-film/"
        dead_embed = "https://hdfilmcehennemi.mobi/video/embed/dead/"
        ajax_url = "https://www.hdfilmcehennemi.nl/video/225110/"
        live_embed = "https://www.hdfilmcehennemi.nl/rplayer/live/"
        dead_manifest = "https://dead.example/master.m3u8"
        decoded_live_manifest = "https://s230.rapidrame.com/movie/master.m3u8?token=x&srv=s427"
        live_manifest = "https://s427.rapidrame.com/movie/master.m3u8?token=x&srv=s427"
        media_playlist = "https://s427.rapidrame.com/movie/1080/index.m3u8"
        main_html = (
            '<html><title>Example Film izle</title>'
            f'<iframe src="{dead_embed}"></iframe>'
            '<button data-video="155163">Close</button>'
            '<button data-video="225110">Rapidrame</button></html>'
        )
        ajax_html = f'<iframe class="rapidrame" data-src="{live_embed}"></iframe>'
        master_text = (
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\n"
            "1080/index.m3u8\n"
        )
        media_text = "#EXTM3U\n#EXTINF:6.0,\nseg-1.ts\n#EXT-X-ENDLIST\n"

        def response(text, status_code=200, json_data=None):
            item = MagicMock()
            item.status_code = status_code
            item.text = text
            item.__bool__.return_value = True
            if json_data is not None:
                item.json.return_value = json_data
            return item

        def get(url, **_kwargs):
            if url == page_url:
                return response(main_html)
            if url == ajax_url:
                return response('', json_data={"success": True, "data": {"html": ajax_html}})
            if url == dead_embed or "/video/embed/dead/" in url:
                return response("<html>dead</html>")
            if url == live_embed:
                return response("<html>live packed player</html>")
            if url == dead_manifest:
                return response("Not Found", status_code=404)
            if url == decoded_live_manifest:
                return response("Unavailable", status_code=503)
            if url == live_manifest:
                return response(master_text)
            if url == media_playlist:
                return response(media_text)
            return response("Not Found", status_code=404)

        session = MagicMock()
        session.get.side_effect = get

        def decode(html):
            return decoded_live_manifest if "live packed player" in html else dead_manifest

        with patch(
            "extractors.platforms.hdfilmcehennemi.decode_rapidrame_script",
            side_effect=decode,
        ):
            result = HDFilmcehennemiExtractor().extract(page_url, session=session)

        self.assertIsNotNone(result)
        self.assertEqual(result.video_url, media_playlist)
        self.assertEqual(result.video_segments, ["https://s427.rapidrame.com/movie/1080/seg-1.ts"])
        self.assertTrue(any(call.args[0] == ajax_url for call in session.get.call_args_list))
        requested_urls = [call.args[0] for call in session.get.call_args_list]
        self.assertIn(live_embed, requested_urls)
        self.assertNotIn(dead_embed, requested_urls)

    def test_decode_rapidrame_script_supports_dean_edwards_packed_source_variable(self):
        """The current Rapidrame player stores the HLS URL in a packed variable."""
        from extractors.platforms.hdfilmcehennemi import decode_rapidrame_script

        packed = r'''eval(function(p,a,c,k,e,d){e=function(c){return c.toString(36)};
        if(!''.replace(/^/,String)){while(c--){d[c.toString(a)]=k[c]||c.toString(a)}
        k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1}
        while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}
        return p}('0 1="2";',3,3,
        'var|streamVar|https://cdn.example.com/master.m3u8'.split('|'),0,{}))'''
        html = f"<script>{packed}</script><script>var configs={{sources:[{{file:streamVar}}]}};</script>"

        self.assertEqual(
            decode_rapidrame_script(html),
            "https://cdn.example.com/master.m3u8",
        )

    def test_dizibox_migrates_legacy_domain_and_resolves_spidy_hls(self):
        """Legacy Dizibox links follow the current domain and current iframe host."""
        from extractors.platforms.dizibox import DiziboxExtractor

        legacy_url = "https://www.dizibox.live/show-1-sezon-1-bolum-hd-izle/"
        current_url = "https://www.dizibox.lol/show-1-sezon-1-bolum/"
        embed_url = "https://spidypro.com/embed/example"
        master_url = "https://cdn.example/master.m3u8"
        media_url = "https://cdn.example/1080/index.m3u8"
        page_html = f'<html><title>Show izle</title><iframe src="{embed_url}"></iframe></html>'
        embed_html = f'<script>const player={{file:"{master_url}"}};</script>'
        master_text = (
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\n"
            "1080/index.m3u8\n"
        )
        media_text = "#EXTM3U\n#EXTINF:6.0,\nseg-1.ts\n#EXT-X-ENDLIST\n"

        def response(text, status_code=200):
            item = MagicMock()
            item.status_code = status_code
            item.text = text
            item.url = current_url
            return item

        def get(url, **_kwargs):
            responses = {
                legacy_url: response("blocked", status_code=403),
                current_url: response(page_html),
                embed_url: response(embed_html),
                master_url: response(master_text),
                media_url: response(media_text),
            }
            return responses.get(url, response("Not Found", status_code=404))

        session = MagicMock()
        session.get.side_effect = get
        with patch("extractors.platforms.dizibox.c_requests", None), patch(
            "extractors.platforms.dizibox._fetch_dizibox_browser_page",
            return_value=None,
        ):
            result = DiziboxExtractor().extract(legacy_url, session=session)

        self.assertIsNotNone(result)
        self.assertEqual(result.video_url, media_url)
        self.assertEqual(result.video_segments, ["https://cdn.example/1080/seg-1.ts"])
        self.assertTrue(any(call.args[0] == current_url for call in session.get.call_args_list))

    def test_dizibox_uses_browser_page_after_cloudflare_403(self):
        """Managed Cloudflare pages are read through the existing Chrome fallback."""
        from extractors.platforms.dizibox import DiziboxExtractor

        page_url = "https://www.dizibox.live/show-1-sezon-1-bolum-hd-izle/"
        embed_url = "https://dbx.molystream.org/embed/example"
        master_url = "https://dbx.molystream.org/embed/sheila/example"
        media_url = "https://dbx.molystream.org/embed/example/q/1"
        page_html = f'<html><title>Show izle</title><iframe src="{embed_url}"></iframe></html>'
        encrypted_html = '<script>CryptoJS.AES.decrypt("cipher", "key")</script>'
        decrypted_html = f'<script>player.setup({{file:"{master_url}"}})</script>'
        master_text = (
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\n"
            f"{media_url}\n"
        )
        media_text = "#EXTM3U\n#EXTINF:2.0,\nhttps://cdn.example/sheila_000.png\n"

        def response(text, status_code=200):
            item = MagicMock()
            item.status_code = status_code
            item.text = text
            item.url = page_url
            return item

        def get(url, **_kwargs):
            responses = {
                page_url: response("blocked", status_code=403),
                embed_url: response(encrypted_html),
                master_url: response(master_text),
                media_url: response(media_text),
            }
            return responses.get(url, response("Not Found", status_code=404))

        session = MagicMock()
        session.get.side_effect = get
        with patch("extractors.platforms.dizibox.c_requests", None), patch(
            "extractors.platforms.dizibox._fetch_dizibox_browser_page",
            return_value=page_html,
        ) as browser_fetch, patch(
            "extractors.platforms.dizibox.decrypt_cryptojs_aes",
            return_value=decrypted_html,
        ):
            result = DiziboxExtractor().extract(page_url, session=session)

        self.assertIsNotNone(result)
        self.assertEqual(result.video_segments, ["https://cdn.example/sheila_000.png"])
        browser_fetch.assert_called_once_with(page_url)

    def test_dizipal_multi_tab_and_clean_dublaj_altyazi(self):
        """Dizipal cleanly separates Dublaj and Altyazılı streams with distinct metadata."""
        from extractors.platforms.dizipal import resolve_dizipal_page

        mock_html = '''
        <html><head><title>Game of Thrones 5x6 izle - Dizipal</title></head><body>
        <div data-rm-k='{"salt":"aabbcc","iv":"112233","ciphertext":"dummy1"}'></div>
        <div data-rm-k='{"salt":"ddeeff","iv":"445566","ciphertext":"dummy2"}'></div>
        </body></html>
        '''

        mock_dp1 = {
            "streams": [{"title": "Türkçe Dublaj", "url": "https://cdn.example.com/dublaj.m3u8"}],
            "subtitles": []
        }
        mock_dp2 = {
            "streams": [{"title": "Orijinal", "url": "https://cdn.example.com/orijinal.m3u8"}],
            "subtitles": [{"url": "https://cdn.example.com/sub.vtt", "label": "Türkçe Altyazı", "lang": "tur"}]
        }

        mock_sess = MagicMock()
        mock_sess.get.return_value = MagicMock(status_code=200, text=mock_html)

        with patch("extractors.platforms.dizipal.AES") as mock_aes, \
             patch("extractors.platforms.dizipal.resolve_dplayer_embed", side_effect=[mock_dp1, mock_dp2]), \
             patch("extractors.platforms.dizipal.c_requests") as mock_creq:
            
            mock_cipher = MagicMock()
            mock_cipher.decrypt.side_effect = [b"/embed/tab1\x05\x05\x05\x05\x05", b"/embed/tab2\x05\x05\x05\x05\x05"]
            mock_aes.new.return_value = mock_cipher

            r_m = MagicMock(status_code=200, text="#EXTM3U\n#EXTINF:6.0,\nseg1.ts")
            mock_creq.get.return_value = r_m

            res = resolve_dizipal_page("https://dizipal1579.com/bolum/got-5x6", session=mock_sess)
            self.assertIsNotNone(res)
            self.assertTrue(res["success"])
            self.assertEqual(len(res["audio_tracks"]), 2)
            self.assertEqual(res["audio_tracks"][0]["name"], "🎬 🇹🇷 Türkçe Dublaj")
            self.assertEqual(res["audio_tracks"][0]["lang"], "tur")
            self.assertEqual(res["audio_tracks"][1]["name"], "🎬 🇬🇧 Orijinal / Türkçe Altyazılı")
            self.assertEqual(res["audio_tracks"][1]["lang"], "eng")
            self.assertEqual(len(res["subtitles"]), 1)
            self.assertEqual(res["subtitles"][0]["lang"], "tur")


if __name__ == "__main__":
    unittest.main()
