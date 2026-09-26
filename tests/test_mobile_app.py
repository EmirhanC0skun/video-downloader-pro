import os
import sys
import unittest
import base64
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'android_app'))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
EXTENSION_SRC = os.path.join(APP_DIR, 'extensions', 'vdpro_android_bridge', 'src')
if EXTENSION_SRC not in sys.path:
    sys.path.insert(0, EXTENSION_SRC)

# E4: flet istege bagli bir bagimliliktir (yalnizca Android arayuzu icin).
# Kurulu degilse arayuz testleri ATLANMALI, hata vermemeli.
try:
    import flet  # noqa: F401
    HAS_FLET = True
except Exception:
    HAS_FLET = False

import mobile_engine
from vdpro_android_bridge import AndroidMediaService
from mobile_engine import (
    MobileDownloadController,
    translate_user_friendly_error,
    get_default_mobile_download_dir
)

class TestAndroidMobileApp(unittest.TestCase):
    def setUp(self):
        self.controller = MobileDownloadController()

    def test_01_controller_initialization(self):
        self.assertIsNotNone(self.controller.engine)
        self.assertTrue(len(self.controller.download_dir) > 0)
        self.assertEqual(self.controller.state, 'IDLE')
        self.assertFalse(self.controller.is_downloading)
        self.assertFalse(self.controller.is_paused)
        self.assertEqual(self.controller.speed_threads, 4)
        self.assertEqual(len(self.controller.queue_items), 0)

    def test_02_error_translation_scenarios(self):
        err_403 = 'HTTP Error 403: Forbidden server access'
        t_403 = translate_user_friendly_error(err_403)
        self.assertIn('Sunucu erişim koruması (403)', t_403)

        err_to = 'HTTPSConnectionPool: Connection timed out'
        t_to = translate_user_friendly_error(err_to)
        self.assertIn('bağlanılamadı veya zaman aşımına uğradı', t_to)

        err_seg = 'Geçersiz segment verisi tespit edildi'
        t_seg = translate_user_friendly_error(err_seg)
        self.assertIn('Akış parçaları tespit edilemedi', t_seg)

        err_perm = 'Permission denied: WinError 5'
        t_perm = translate_user_friendly_error(err_perm)
        self.assertIn('Dosya yazma izni', t_perm)

        err_gen = 'Bilinmeyen özel hata'
        self.assertEqual(translate_user_friendly_error(err_gen), 'Bilinmeyen özel hata')

    def test_03_tab_switching_and_nav_handler(self):
        called_args = []
        def mock_nav(idx, url=None, auto_resolve=False):
            called_args.append((idx, url, auto_resolve))

        self.controller.nav_handler = mock_nav
        self.controller.switch_tab(1, url='https://youtube.com/watch?v=123', auto_resolve=True)

        self.assertEqual(len(called_args), 1)
        self.assertEqual(called_args[0], (1, 'https://youtube.com/watch?v=123', True))
        self.assertEqual(self.controller.active_tab_index, 1)

    def test_04_download_lifecycle_state_machine(self):
        self.controller.start_download_session('Test Medya')
        self.assertTrue(self.controller.is_downloading)
        self.assertFalse(self.controller.is_paused)
        self.assertEqual(self.controller.state, 'DOWNLOADING')

        res_p = self.controller.pause_download()
        self.assertTrue(res_p)
        self.assertTrue(self.controller.is_paused)
        self.assertEqual(self.controller.state, 'PAUSED')

        res_r = self.controller.resume_download()
        self.assertTrue(res_r)
        self.assertFalse(self.controller.is_paused)
        self.assertEqual(self.controller.state, 'DOWNLOADING')

        self.controller.cancel_current_download(cleanup=False)
        self.assertFalse(self.controller.is_downloading)
        self.assertEqual(self.controller.state, 'CANCELLED')

    def test_05_queue_item_management(self):
        it1 = self.controller.add_queue_item('Bölüm 1', 'https://dizipal.mom/b1')
        _ = self.controller.add_queue_item('Bölüm 2', 'https://dizipal.mom/b2')

        self.assertEqual(len(self.controller.queue_items), 2)
        self.assertEqual(self.controller.queue_items[0]['title'], 'Bölüm 1')

        self.controller.remove_queue_item(it1['id'])
        self.assertEqual(len(self.controller.queue_items), 1)
        self.assertEqual(self.controller.queue_items[0]['title'], 'Bölüm 2')

        self.controller.clear_queue()
        self.assertEqual(len(self.controller.queue_items), 0)

    def test_06_series_episode_scanner(self):
        base_url = 'https://dizibox.tv/dizi-adi-1-sezon-1-bolum-izle/'
        eps = self.controller.scan_series_episodes(base_url, start_ep=1, end_ep=5)

        self.assertEqual(len(eps), 5)
        self.assertEqual(eps[0]['title'], 'Bölüm 1')
        self.assertIn('1-bolum', eps[0]['url'])
        self.assertEqual(eps[4]['title'], 'Bölüm 5')
        self.assertIn('5-bolum', eps[4]['url'])

    def test_resolver_exception_is_logged_without_signed_query(self):
        ui_messages = []
        source_url = 'https://example.invalid/watch?token=secret-token'

        with patch.object(
            mobile_engine,
            'resolve_film_page',
            side_effect=RuntimeError('android resolver boom'),
        ):
            with self.assertLogs(mobile_engine.logger.name, level='WARNING') as captured:
                result = self.controller.resolve_media_url(
                    source_url,
                    log_cb=ui_messages.append,
                )

        self.assertIsNone(result)
        self.assertIn('android resolver boom', ui_messages[-1])
        log_output = '\n'.join(captured.output)
        self.assertIn('example.invalid', log_output)
        self.assertIn('android resolver boom', log_output)
        self.assertNotIn('secret-token', log_output)

    def test_native_http_session_translates_requests_contract(self):
        captured = []

        def requester(payload):
            captured.append(payload)
            return {
                'status': 200,
                'url': 'https://example.invalid/final',
                'headers': {
                    'content-type': ['text/plain; charset=utf-8'],
                    'set-cookie': ['sid=abc; Path=/'],
                },
                'body_base64': base64.b64encode(b'android-native-body').decode('ascii'),
            }

        session = mobile_engine.AndroidNativeSession(requester)
        response = session.post(
            'https://example.invalid/start',
            headers={'Referer': 'https://origin.invalid/'},
            data={'language': 'tr', 'episode': '3'},
            timeout=(5, 17),
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.url, 'https://example.invalid/final')
        self.assertEqual(response.text, 'android-native-body')
        self.assertEqual(list(response.iter_content(7)), [b'android', b'-native', b'-body'])
        self.assertEqual(captured[0]['method'], 'POST')
        self.assertEqual(captured[0]['timeout_seconds'], 17)
        self.assertFalse(captured[0]['follow_redirects'])
        self.assertEqual(captured[0]['body'], 'language=tr&episode=3')
        self.assertIn('sid', session.cookies)

    def test_native_http_bridge_uses_request_timeout_instead_of_flet_default(self):
        service = AndroidMediaService()
        service._invoke_method = AsyncMock(return_value={'status': 204})
        request = {'url': 'https://example.invalid/', 'timeout_seconds': 17}

        result = asyncio.run(service.http_request(request))

        self.assertEqual(result, {'status': 204})
        service._invoke_method.assert_awaited_once_with(
            'http_request',
            request,
            timeout=27,
        )

    def test_controller_routes_resolution_through_native_http_session(self):
        native_session = object()
        resolved = {'success': True, 'title': 'Native Android media'}

        with patch.object(
            mobile_engine,
            '_create_android_http_session',
            return_value=native_session,
            create=True,
        ):
            with patch.object(
                mobile_engine,
                'resolve_film_page',
                return_value=resolved,
            ) as resolver:
                result = self.controller.resolve_media_url('https://example.invalid/watch')

        self.assertEqual(result, resolved)
        resolver.assert_called_once_with(
            'https://example.invalid/watch',
            log_callback=None,
            session=native_session,
        )

    @unittest.skipUnless(HAS_FLET, "flet kurulu degil; Android arayuz testleri atlaniyor")
    def test_07_all_views_import_and_render_structure(self):
        from views.film_view import build_film_view
        from views.social_view import build_social_view
        from views.queue_view import build_queue_view
        from views.converter_view import build_converter_view
        from views.downloads_view import build_downloads_view
        from views.settings_view import build_settings_view

        mock_page = MagicMock()
        mock_page.theme_mode = MagicMock()
        mock_page.get_clipboard = MagicMock(return_value='https://test.com')

        v_film = build_film_view(mock_page, self.controller)
        self.assertIsNotNone(v_film)

        v_social = build_social_view(mock_page, self.controller)
        self.assertIsNotNone(v_social)

        v_queue = build_queue_view(mock_page, self.controller)
        self.assertIsNotNone(v_queue)

        v_conv = build_converter_view(mock_page, self.controller)
        self.assertIsNotNone(v_conv)

        v_down = build_downloads_view(mock_page, self.controller)
        self.assertIsNotNone(v_down)

        v_set = build_settings_view(mock_page, self.controller)
        self.assertIsNotNone(v_set)

if __name__ == '__main__':
    unittest.main()
