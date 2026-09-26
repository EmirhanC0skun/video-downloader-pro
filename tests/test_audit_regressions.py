# -*- coding: utf-8 -*-
"""
Kod denetiminde bulunan hatalar için regresyon testleri.

Her test, denetim raporundaki bulgu kimliğine (A1…F5) göre adlandırılmıştır ve
düzeltme geri alınırsa kırılır. Tamamı çevrimdışıdır; ağ erişimi yoktur.
"""

import ast
import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine
import extractor
import sniffer
import history


class TestRemainingAuditFindings(unittest.TestCase):

    def test_downloader_star_import_exports_only_real_symbols(self):
        namespace = {}
        exec("from engine_core.downloader import *", namespace)
        self.assertIn("SegmentDownloaderMixin", namespace)

    def test_importing_utils_does_not_patch_urllib3_process_globally(self):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script = (
            "import sys; "
            f"sys.path.insert(0, {project_root!r}); "
            "import urllib3.util.connection as connection; "
            "original = connection.create_connection; "
            "import engine_core.utils; "
            "raise SystemExit(0 if connection.create_connection is original else 1)"
        )
        result = subprocess.run([sys.executable, "-c", script], timeout=15)
        self.assertEqual(result.returncode, 0)

    def test_resolver_never_updates_tk_from_worker_fallback(self):
        from ui.controllers.resolve import ResolveControllerMixin

        source = inspect.getsource(ResolveControllerMixin._resolve_film_threaded)
        self.assertNotIn("except Exception:\n                    apply_ui()", source)

    def test_segment_validator_rejects_json_and_xml_error_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, payload in (
                ("error-json.tmp", b'{"error":"Access denied"}'),
                ("error-xml.tmp", b'<?xml version="1.0"?><Error>Denied</Error>'),
            ):
                path = os.path.join(temp_dir, name)
                with open(path, "wb") as handle:
                    handle.write(payload)
                self.assertFalse(engine.is_valid_segment_file(path), name)


# =============================================================================
# A. Çalışma anında patlayan kod
# =============================================================================
class TestRuntimeCrashes(unittest.TestCase):

    def test_A1_detect_segment_range_unpacked_with_correct_arity(self):
        """detect_segment_range 2'li demet döndürür; hiçbir çağrı yeri 3'e açmamalı."""
        returns = [
            n for n in ast.walk(ast.parse(inspect.getsource(engine.detect_segment_range)))
            if isinstance(n, ast.Return)
        ]
        self.assertTrue(returns, "detect_segment_range hiç return içermiyor")
        for r in returns:
            self.assertIsInstance(r.value, ast.Tuple)
            self.assertEqual(len(r.value.elts), 2,
                             "detect_segment_range 2 elemanlı demet döndürmeli")

        src = ast.parse(open(engine.__file__, encoding="utf-8-sig").read())
        bad = []
        for node in ast.walk(src):
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "detect_segment_range"):
                continue
            target = node.targets[0]
            if isinstance(target, ast.Tuple) and len(target.elts) != 2:
                bad.append((node.lineno, len(target.elts)))
        self.assertEqual(bad, [], f"detect_segment_range yanlış arity ile açılıyor: {bad}")

    def test_A2_no_undefined_session_name_in_engine(self):
        """run_dual/run_multi içinde çıplak `session.get(...)` kalmamalı."""
        for fn in (engine.VideoDownloadEngine.run_dual_stream_download,
                   engine.VideoDownloadEngine.run_multi_audio_download):
            tree = ast.parse(inspect.getsource(fn).lstrip())
            assigned = {n.id for n in ast.walk(tree)
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            args = {a.arg for a in tree.body[0].args.args}
            used_bare_session = any(
                isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == "session"
                for n in ast.walk(tree)
            )
            if used_bare_session:
                self.assertTrue("session" in assigned or "session" in args,
                                f"{fn.__name__}: tanımsız `session` kullanılıyor")

    def test_A3_A5_gui_method_references_resolve(self):
        """gui.py içindeki tüm self.<metot>() çağrıları tanımlı olmalı."""
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui.py")
        tree = ast.parse(open(gui_path, encoding="utf-8-sig").read())
        cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == "VideoDownloaderGUI")
        defined = {n.name for n in cls.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        inherited = {
            "after", "after_cancel", "after_idle", "clipboard_append", "clipboard_clear",
            "clipboard_get", "configure", "geometry", "grid_columnconfigure",
            "grid_rowconfigure", "minsize", "title", "update_idletasks", "winfo_height",
            "winfo_width", "winfo_x", "winfo_y", "withdraw", "destroy", "mainloop",
            "update", "bind", "protocol", "deiconify", "lift", "state",
        }
        missing = sorted({
            n.func.attr for n in ast.walk(cls)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
            and n.func.attr not in defined and n.func.attr not in inherited
        })
        self.assertEqual(missing, [], f"gui.py tanımsız metot çağırıyor: {missing}")

    def test_A4_context_menu_uses_bound_tkinter_alias(self):
        """Sağ tık menüsü `tkinter.Menu` değil, import edilen `tk` diğer adını kullanmalı."""
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui.py")
        src = open(gui_path, encoding="utf-8-sig").read()
        self.assertNotIn("tkinter.Menu(", src,
                         "gui.py `tkinter` adını bağlamıyor; `tk.Menu` kullanılmalı")
        self.assertIn("tk.Menu(", src)

    def test_A6_dual_stream_resets_cancel_flag(self):
        """
        run_dual_stream_download önceki iptal bayrağını temizlemeli.

        Ağa çıkmadan doğrulanır: devredilen metot taklit edilir, yalnızca
        `cancel_event`in çağrı başında temizlenip temizlenmediğine bakılır.
        Gerçek uçtan uca doğrulama: test_engine.py::test_15
        """
        src = inspect.getsource(engine.VideoDownloadEngine.run_dual_stream_download)
        self.assertIn("self.reset_cancel()", src)

        eng = engine.VideoDownloadEngine()
        eng.cancel(cleanup=False)                    # önceki öğe iptal edilmiş gibi
        self.assertTrue(eng.cancel_event.is_set())

        seen = {}

        def fake_multi(*a, **kw):
            seen["cancel_set"] = eng.cancel_event.is_set()
            return True, "ok"

        with patch.object(engine.VideoDownloadEngine, "run_multi_audio_download",
                          side_effect=fake_multi):
            ok, msg = eng.run_dual_stream_download(
                video_url="https://cdn.example.com/v/seg_001.ts",
                audio_url="https://cdn.example.com/a/seg_001.ts",
                output_filepath=os.path.join(tempfile.gettempdir(), "vdp_a6.mp4"),
                video_segments=["https://cdn.example.com/v/seg_001.ts"],
                audio_segments=["https://cdn.example.com/a/seg_001.ts"],
            )

        self.assertTrue(ok)
        self.assertFalse(seen.get("cancel_set", True),
                         "İptal bayrağı çağrı başında temizlenmedi (A6)")

    def test_A7_no_hardcoded_developer_paths(self):
        """Kaynak kodda geliştirici makinesine ait sabit yol kalmamalı."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", ".agents", "__pycache__", "build", "dist", "docs")]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    text = open(fp, encoding="utf-8-sig").read()
                except Exception:
                    continue
                if "C:" + chr(92) + "Users" + chr(92) + "Emirhan" in text:
                    offenders.append(os.path.relpath(fp, root))
        self.assertEqual(offenders, [], f"Sabit geliştirici yolu içeren dosyalar: {offenders}")


# =============================================================================
# B. Mantık ve doğruluk
# =============================================================================
MASTER_ASCENDING = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
mid.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
high.m3u8
"""

MASTER_DESCENDING = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
high.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
mid.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
"""

BASE = "https://cdn.example.com/hls/master.m3u8"
BEST = "https://cdn.example.com/hls/high.m3u8"


class TestStreamSelection(unittest.TestCase):

    def test_B1_extractor_picks_highest_bandwidth_regardless_of_order(self):
        self.assertEqual(extractor.select_best_variant_url(BASE, MASTER_ASCENDING), BEST)
        self.assertEqual(extractor.select_best_variant_url(BASE, MASTER_DESCENDING), BEST)

    def test_B1_sniffer_picks_highest_bandwidth_regardless_of_order(self):
        self.assertEqual(sniffer.pick_highest_bandwidth_variant(BASE, MASTER_ASCENDING), BEST)
        self.assertEqual(sniffer.pick_highest_bandwidth_variant(BASE, MASTER_DESCENDING), BEST)

    def test_B1_falls_back_to_plain_playlist_line(self):
        plain = "#EXTM3U\n#EXT-X-TARGETDURATION:6\nchunk.m3u8\n"
        self.assertEqual(extractor.select_best_variant_url(BASE, plain),
                         "https://cdn.example.com/hls/chunk.m3u8")


class TestAesDecryption(unittest.TestCase):

    def setUp(self):
        try:
            from Crypto.Cipher import AES  # noqa: F401
        except ImportError:
            self.skipTest("pycryptodome kurulu değil")

    def test_B2_pkcs7_padding_is_stripped(self):
        from Crypto.Cipher import AES
        key = bytes(range(16))
        iv = bytes(16)
        plain = b"MPEG-TS payload"                      # 15 bayt
        pad = 16 - (len(plain) % 16)
        padded = plain + bytes([pad]) * pad
        ct = AES.new(key, AES.MODE_CBC, iv).encrypt(padded)

        out = engine.decrypt_hls_segment(ct, key, iv)
        self.assertEqual(out, plain, "PKCS#7 dolgusu kaldırılmadı (B2)")

    def test_B2_iv_derived_from_media_sequence(self):
        self.assertEqual(engine.derive_hls_iv(0), bytes(16))
        self.assertEqual(engine.derive_hls_iv(1), bytes(15) + b"\x01")
        self.assertEqual(engine.derive_hls_iv(258), bytes(14) + b"\x01\x02")

    def test_B2_failure_returns_none_instead_of_ciphertext(self):
        """Çözme başarısız olursa şifreli veri asla geri dönmemeli."""
        self.assertIsNone(engine.decrypt_hls_segment(b"kisa", bytes(16), bytes(16)))
        self.assertIsNone(engine.decrypt_hls_segment(b"", bytes(16), bytes(16)))
        self.assertIsNone(engine.decrypt_hls_segment(bytes(32), None, bytes(16)))

    def test_B2_encrypted_segment_is_not_written_on_failure(self):
        """download_segment_file, çözülemeyen segmenti diske yazmamalı."""
        import tempfile
        eng = engine.VideoDownloadEngine()
        target = os.path.join(tempfile.mkdtemp(prefix="vdp_b2_"), "seg.tmp")

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"A" * 33          # 16'nın katı değil -> çözme başarısız
        resp.headers = {"Content-Type": "video/mp2t"}

        fake_session = MagicMock()
        fake_session.get.return_value = resp
        with patch.object(eng, "_get_session", return_value=fake_session):
            ok, written = eng.download_segment_file(
                "https://cdn.example.com/s.ts",
                {"aes_key": bytes(16), "aes_iv": bytes(16)},
                target,
                max_retries=1,
            )
        self.assertFalse(ok)
        self.assertEqual(written, 0)
        self.assertFalse(os.path.exists(target), "Şifreli veri diske yazıldı (B2)")


class TestProbeAndParams(unittest.TestCase):

    def test_B8_probe_url_does_not_download_body(self):
        """HEAD başarısızsa Range: bytes=0-0 ile akış modunda yoklanmalı."""
        session = MagicMock()
        session.head.side_effect = Exception("HEAD desteklenmiyor")
        resp = MagicMock()
        resp.status_code = 206
        session.get.return_value = resp

        ok, status, hint = engine.probe_url("https://cdn.example.com/s.ts", {}, session=session)

        self.assertTrue(ok)
        kwargs = session.get.call_args.kwargs
        self.assertTrue(kwargs.get("stream"), "probe_url stream=True kullanmıyor (B8)")
        self.assertEqual(kwargs["headers"].get("Range"), "bytes=0-0")
        resp.close.assert_called_once()

    def test_B10_merge_mode_is_actually_used(self):
        """CLI'daki --merge seçeneği run_download gövdesinde okunmalı."""
        src = inspect.getsource(engine.VideoDownloadEngine.run_download)
        self.assertIn("merge_mode", src.split("\n", 1)[1],
                      "merge_mode yalnızca imzada var, gövdede kullanılmıyor (B10)")

    def test_B10_fallback_host_is_passed_to_segment_downloader(self):
        src = inspect.getsource(engine.VideoDownloadEngine.download_stream_segments)
        self.assertIn("fallback_host=fallback_host", src)

    def test_B10_detect_segment_range_uses_supplied_session(self):
        src = inspect.getsource(engine.detect_segment_range)
        self.assertIn("owns_session", src,
                      "detect_segment_range verilen session'ı yok sayıyor (B10)")

    def test_B9_run_download_remux_hides_console_window(self):
        src = inspect.getsource(engine.VideoDownloadEngine.run_download)
        self.assertIn("CREATE_NO_WINDOW", src)

    def test_B7_magic_routers_have_recursion_guard(self):
        """Sekmeler birbirinden bağımsız çalışmalı; metot imzaları geriye dönük uyumlu olmalı."""
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui.py")
        src = open(gui_path, encoding="utf-8-sig").read()
        self.assertIn("def _resolve_film_threaded(self, _from_router=False)", src)
        self.assertIn("def _resolve_youtube_url_threaded(self, _from_router=False)", src)
        # Sosyal medya sekmesinden film sekmesine zorla yönlendirme olmamalı
        yt_chunk = src.split("def _resolve_youtube_url_threaded")[1].split("cookie_choice")[0]
        self.assertNotIn('self._show_page("film")', yt_chunk)

    def test_B11_adaptive_concurrency_for_cloudflare_workers(self):
        """Cloudflare Worker (.workers.dev) CDN'lerinde bot korumasını aşmak için adaptif worker ve fail-fast timeout olmalı."""
        src_stream = inspect.getsource(engine.VideoDownloadEngine.download_stream_segments)
        self.assertIn("workers.dev", src_stream)
        self.assertIn("eff_workers = min(thread_count, 10)", src_stream)

        src_seg = inspect.getsource(engine.VideoDownloadEngine.download_segment_file)
        self.assertIn("workers.dev", src_seg)
        self.assertIn("t_read = 6.0 if \"workers.dev\" in current_url.lower() else 10.0", src_seg)


# =============================================================================
# C. Mimari
# =============================================================================
class TestArchitecture(unittest.TestCase):

    def test_C3_result_contract_keys_always_present(self):
        """normalize_extraction_result her zaman tam anahtar kümesini döndürmeli."""
        out = extractor.normalize_extraction_result(
            {"success": True, "title": "X", "video_url": "https://e.test/v.m3u8"},
            source_url="https://e.test/film",
        )
        for key in extractor.RESULT_DEFAULTS:
            self.assertIn(key, out, f"'{key}' anahtarı eksik (C3)")
        self.assertTrue(out["qualities"], "qualities boş türetildi (C3)")
        self.assertTrue(out["audio_tracks"], "audio_tracks boş türetildi (C3)")
        self.assertEqual(out["raw_url"], "https://e.test/film")

    def test_C3_total_segments_derived_from_segment_list(self):
        out = extractor.normalize_extraction_result({
            "success": True, "title": "X", "video_url": "u",
            "video_segments": ["a", "b", "c"],
        })
        self.assertEqual(out["total_segments"], 3)

    def test_C3_direct_file_gets_no_synthetic_audio_track(self):
        out = extractor.normalize_extraction_result({
            "success": True, "title": "X", "video_url": "https://e.test/v.mp4",
            "direct_file": True,
        })
        self.assertEqual(out["audio_tracks"], [])

    def test_C2_registry_is_reachable_from_production_path(self):
        """extractors/ paketi artık ölü kod olmamalı."""
        src = open(extractor.__file__, encoding="utf-8-sig").read()
        self.assertIn("from extractors.registry import default_registry", src,
                      "Modüler registry üretim yolundan çağrılmıyor (C2)")

    def test_C2_series_film_extractor_does_not_recurse(self):
        """SeriesFilmExtractor monolite geri dönmemeli (sonsuz özyineleme)."""
        from extractors.series_film import SeriesFilmExtractor
        tree = ast.parse(inspect.getsource(SeriesFilmExtractor.extract).lstrip())
        calls = [
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ] + [
            n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        self.assertNotIn("resolve_film_page", calls,
                         "SeriesFilmExtractor resolve_film_page'i geri çağırıyor (C2)")

    def test_C5_download_ui_prep_is_single_method(self):
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui.py")
        src = open(gui_path, encoding="utf-8-sig").read()
        self.assertIn("def _begin_download_ui(", src)
        self.assertGreaterEqual(src.count("self._begin_download_ui("), 4,
                                "Dört indirme başlatıcı da ortak metodu kullanmalı (C5)")

    def test_C7_unpack_js_defined_once(self):
        src = ast.parse(open(extractor.__file__, encoding="utf-8-sig").read())
        names = [n.name for n in src.body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(names.count("unpack_js"), 1,
                         "unpack_js birden fazla kez tanımlı (C7)")

    def test_C1_mobile_core_is_in_sync_with_desktop(self):
        """android_app/core üretilmiş bir kopyadır; kökten ayrışmamalı."""
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import sync_mobile_core
        ok, problems = sync_mobile_core.check()
        self.assertTrue(ok, "Mobil çekirdek ayrışmış (C1): " + "; ".join(problems)
                            + "\nDüzeltmek için: python tools/sync_mobile_core.py")

    def test_C1_no_duplicate_flat_copies_inside_android_app(self):
        """android_app/ altındaki düz kopyalar kaldırılmış olmalı."""
        app_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "android_app")
        for name in ("engine.py", "extractor.py", "sniffer.py", "history.py",
                     "logger.py", "exceptions.py"):
            self.assertFalse(os.path.exists(os.path.join(app_dir, name)),
                             f"android_app/{name} üçüncü bir kopya olarak geri gelmiş (C1)")


# =============================================================================
# D / F. Bağımlılıklar ve hijyen
# =============================================================================
class TestDependenciesAndHygiene(unittest.TestCase):

    def setUp(self):
        self.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _req(self, name):
        return open(os.path.join(self.root, name), encoding="utf-8").read().lower()

    def test_D1_requirements_lists_every_runtime_dependency(self):
        req = self._req("requirements.txt")
        for pkg in ("curl-cffi", "pycryptodome", "certifi", "requests", "yt-dlp"):
            self.assertIn(pkg, req, f"requirements.txt '{pkg}' paketini listelemiyor (D1)")

    def test_D2_lockfile_covers_requirements(self):
        lock = self._req("requirements.lock")
        for pkg in ("curl-cffi", "pycryptodome", "certifi", "tqdm"):
            self.assertIn(pkg, lock, f"requirements.lock '{pkg}' paketini listelemiyor (D2)")

    def test_D5_upx_disabled_in_spec(self):
        spec = open(os.path.join(self.root, "VideoDownloaderPro.spec"), encoding="utf-8").read()
        self.assertIn("_UPX = False", spec, "UPX hâlâ açık (D5)")

    def test_D6_importing_history_does_not_open_database(self):
        """`import history` yan etki üretmemeli; veritabanı ilk kullanımda açılmalı."""
        src = open(history.__file__, encoding="utf-8-sig").read()
        self.assertNotIn("\n_default_manager = SQLiteHistoryManager()", src,
                         "history.py import anında veritabanı açıyor (D6)")
        self.assertTrue(hasattr(history, "get_manager"))

    def test_D6_legacy_timestamp_never_collapses_to_epoch_zero(self):
        self.assertGreater(history._legacy_created_at({"id": 1}), 1_600_000_000)
        self.assertGreater(history._legacy_created_at({"id": 3}), 1_600_000_000)
        self.assertEqual(history._legacy_created_at({"id": 1700000000000}), 1700000000.0)
        self.assertEqual(history._legacy_created_at({"id": 1700000000}), 1700000000)

    def test_F2_dev_artifacts_not_in_repo_root(self):
        for stray in ("script_0.js", "script_1.js", "fastplay.html",
                      "goodbyedpi_1000_site_raporu.txt", "fast_test_suite.py",
                      "run_full_live_test_suite.py"):
            self.assertFalse(os.path.exists(os.path.join(self.root, stray)),
                             f"Geliştirme artefaktı kök dizine geri gelmiş: {stray} (F2)")

    def test_F3_no_os_system_calls(self):
        gui_src = open(os.path.join(self.root, "gui.py"), encoding="utf-8-sig").read()
        self.assertNotIn("os.system(", gui_src, "gui.py hâlâ os.system kullanıyor (F3)")

    def test_F4_ssl_warnings_not_globally_disabled(self):
        tree = ast.parse(open(extractor.__file__, encoding="utf-8-sig").read())
        calls = [
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        self.assertNotIn("disable_warnings", calls,
                         "SSL uyarıları hâlâ global olarak susturuluyor (F4)")


# =============================================================================
# C4. Sessiz istisnalar
# =============================================================================
class TestSilentExceptions(unittest.TestCase):

    @staticmethod
    def _bare_pass_handlers(path):
        tree = ast.parse(open(path, encoding="utf-8-sig").read())
        return [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.ExceptHandler) and len(n.body) == 1
                and isinstance(n.body[0], ast.Pass)]

    def test_C4_engine_and_ui_have_no_silent_exception_handlers(self):
        """
        engine / gui / sniffer / history içinde sessizce yutulan istisna kalmamalı.

        Bu dört modülde `logger` her zaman mevcut olduğu için istisnasız sıfır
        beklenir. `extractor.py` ve `logger.py` ayrı ele alınır (aşağıya bakınız).
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for rel in ("engine.py", "gui.py", "sniffer.py", "history.py"):
            for line in self._bare_pass_handlers(os.path.join(root, rel)):
                offenders.append(f"{rel}:{line}")
        self.assertEqual(offenders, [],
                         f"Sessizce yutulan istisnalar kaldı (C4): {offenders}")

    def test_C4_remaining_silent_handlers_are_deliberate(self):
        """
        Kalan birkaç `except: pass` bilinçlidir ve sayısı sabit tutulmalıdır:

        * `certifi` / stdout yapılandırma korumaları — logger henüz kurulmamıştır,
        * log geri-çağırma korumaları — log hatasını loglamak özyineleme üretir,
        * `UICallbackHandler.emit` — log işleyicisinin içi,
        * registry `except ExtractorError: pass` — kasıtlı akış kontrolü.

        Sayı artarsa bu test, yeni bir sessiz yutmanın sızdığını bildirir.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected = {
            "extractor.py": 0,
            "logger.py": 1,
            "downloader.py": 1,
            "main.py": 1,
            os.path.join("extractors", "series_film.py"): 0,
            os.path.join("extractors", "universal.py"): 0,
        }
        actual = {rel: len(self._bare_pass_handlers(os.path.join(root, rel)))
                  for rel in expected}
        self.assertEqual(actual, expected,
                         "Sessiz istisna sayısı değişti (C4). Yeni bir yutma eklendiyse "
                         "logger.debug(..., exc_info=True) kullanın.")



class TestSegmentValidationAndRecovery(unittest.TestCase):
    """
    376 baytlık geçerli MPEG-TS paketlerinin eksik sayılmamasını (YabancıDizi / SezonlukDizi)
    ve is_valid_segment_file fonksiyonunun HTML/0-bayt hatalarını ayırt ettiğini doğrular.
    """

    def test_C5_valid_mpeg_ts_segment_under_512_bytes_is_valid(self):
        from engine import is_valid_segment_file
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            # 1. 376 baytlık geçerli MPEG-TS süreksizlik paketi
            ts_p = os.path.join(td, "valid_discontinuity.ts")
            with open(ts_p, "wb") as f:
                f.write(b"G@\x00\x16" + b"\xff" * 372)
            self.assertTrue(is_valid_segment_file(ts_p), "376 baytlık geçerli MPEG-TS segmenti geçerli sayılmalı")

            # 2. 0 baytlık boş dosya
            zero_p = os.path.join(td, "empty.tmp")
            with open(zero_p, "wb") as f:
                pass
            self.assertFalse(is_valid_segment_file(zero_p), "0 baytlık dosya geçersiz sayılmalı")

            # 3. HTML hata sayfası
            html_p = os.path.join(td, "error.html")
            with open(html_p, "wb") as f:
                f.write(b"<!DOCTYPE html><html><body>Error 404</body></html>")
            self.assertFalse(is_valid_segment_file(html_p), "HTML hata sayfası geçersiz sayılmalı")

            # 4. M3U8 çalma listesi
            m3u8_p = os.path.join(td, "list.m3u8")
            with open(m3u8_p, "wb") as f:
                f.write(b"#EXTM3U\n#EXT-X-VERSION:3\n")
            self.assertFalse(is_valid_segment_file(m3u8_p), "M3U8 dosyası segment olarak geçersiz sayılmalı")

    def test_C6_mailru_embed_and_ad_keywords_filter(self):
        from extractor import resolve_mailru_embed, normalize_extraction_result
        from unittest.mock import MagicMock

        # 1. normalize_extraction_result tekil akışta varsayılan olarak "und" vermeli
        raw_res = {"video_url": "https://example.com/stream.m3u8"}
        normalized = normalize_extraction_result(raw_res)
        self.assertEqual(normalized["audio_tracks"][0]["lang"], "und",
                         "Tekil varsayılan ses kanalı sahte 'tur' değil 'und' olmalıdır")

        # 2. resolve_mailru_embed mock doğrulaması
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "meta": {"title": "Test Movie"},
            "videos": [{"key": "1080p", "url": "//cdn.example.com/movie.mp4"}]
        }
        mock_session.get.return_value = mock_resp

        res = resolve_mailru_embed("https://my.mail.ru/video/embed/12345", session=mock_session)
        self.assertIsNotNone(res)
        self.assertEqual(res["video_url"], "https://cdn.example.com/movie.mp4")
        self.assertEqual(res["title"], "Test Movie")

    def test_C7_diziyou_dual_language_and_resumable_direct_engine(self):
        import hashlib, tempfile, re
        from extractor import resolve_film_page
        from unittest.mock import patch, MagicMock

        # 1. Deterministik direct file temp klasörü testi
        url = "https://cdn.example.com/video1080p.mp4?token=abc123xyz"
        out_p = os.path.join(tempfile.gettempdir(), "Melissa_P.mp4")
        base_temp = os.path.join(tempfile.gettempdir(), ".vdp_temp")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        safe_stem = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(out_p))[0])[:25]
        expected_dir = os.path.join(base_temp, f".temp_direct_{safe_stem}_{url_hash}")
        
        # Yeniden denendiğinde klasörün zaman damgasından bağımsız sabit kaldığını doğrula
        url_hash_2 = hashlib.md5(url.encode()).hexdigest()[:10]
        safe_stem_2 = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(out_p))[0])[:25]
        dir_2 = os.path.join(base_temp, f".temp_direct_{safe_stem_2}_{url_hash_2}")
        self.assertEqual(expected_dir, dir_2, "Deterministik temp klasörü her duraklat/başlat işleminde birebir aynı kalmalıdır")

        import engine
        self.assertTrue(hasattr(engine, "hashlib"), "engine modülü hashlib importuna sahip olmalıdır")

        # 2. Diziyou çift dil tespiti (Mocking HTML responses)
        mock_page_html = """
        <html>
        <head><title>Test Dizi 1. Sezon 1. Bölüm</title></head>
        <body>
        <div id="diziyouSelect">
            <span id="turkceDublaj">Türkçe Dublaj</span>
            <span id="turkceAltyazili">Türkçe Altyazılı</span>
        </div>
        <iframe src="/player/10555.html"></iframe>
        <!-- Padding comment to exceed the 500-byte length threshold of extractor.py -->
        <!-- """ + ("x" * 600) + """ -->
        </body>
        </html>
        """
        mock_session = MagicMock()
        mock_resp_page = MagicMock(status_code=200, text=mock_page_html)
        mock_resp_tr = MagicMock(status_code=200, text='<source src="https://storage.diziyou.one/episodes/10555_tr/play.m3u8">')
        mock_resp_orig = MagicMock(status_code=200, text='<source src="https://storage.diziyou.one/episodes/10555/play.m3u8">')
        mock_resp_m3u8_tr = MagicMock(status_code=200, text='#EXTM3U\nseg_tr_0.ts\nseg_tr_1.ts\n')
        mock_resp_m3u8_orig = MagicMock(status_code=200, text='#EXTM3U\nseg_en_0.ts\nseg_en_1.ts\n')

        def mock_get(u, **kwargs):
            if "10555_tr.html" in u:
                return mock_resp_tr
            elif "10555.html" in u:
                return mock_resp_orig
            elif "10555_tr/play.m3u8" in u:
                return mock_resp_m3u8_tr
            elif "10555/play.m3u8" in u:
                return mock_resp_m3u8_orig
            return mock_resp_page

        mock_session.get.side_effect = mock_get

        with patch("extractor.requests.Session", return_value=mock_session):
            res = resolve_film_page("https://www.diziyou.one/test-dizi-1-sezon-1-bolum/")
            self.assertTrue(res.get("success"))
            tracks = res.get("audio_tracks", [])
            self.assertEqual(len(tracks), 2, "Diziyou çift dil tespitinde hem dublaj hem altyazı akışı sunulmalıdır")
            self.assertEqual(tracks[0]["lang"], "tur")
            self.assertEqual(tracks[1]["lang"], "eng")

    def test_C8_closeload_pichive_and_copyright_regressions(self):
        from extractor import decrypt_closeload_python, resolve_film_page
        from unittest.mock import MagicMock, patch

        # 1. CloseLoad Saf Python Yorumlayıcı Testi
        mock_func = """function dc_test(value_parts) {
            let value = value_parts.join('');
            let result = value;
            result = result.split('').reverse().join('');
            result = atob(result);
            var acc = 10;
            let unmix = '';
            for (let i = 0; i < result.length; i++) {
                var b = result.charCodeAt(i);
                acc = (acc + 5) % 256;
                var plain = b ^ acc;
                acc = (acc + b) % 256;
                unmix += String.fromCharCode(plain);
            }
            return unmix;
        }"""
        # Test input generation matching mock_func logic
        # expected target: "https://stream.test/master.txt"
        target_str = "https://stream.test/master.txt"
        # encrypt target_str:
        acc = 10
        enc_bytes = []
        for c in target_str:
            b = ord(c)
            acc = (acc + 5) % 256
            cipher_byte = b ^ acc
            acc = (acc + cipher_byte) % 256
            enc_bytes.append(chr(cipher_byte))
        enc_s = "".join(enc_bytes)
        import base64
        b64 = base64.b64encode(enc_s.encode('latin1')).decode('latin1')
        rev = b64[::-1]
        mock_call = f'dc_test(["{rev[:10]}", "{rev[10:]}"])'

        decrypted = decrypt_closeload_python(mock_func, mock_call)
        self.assertEqual(decrypted, target_str, "CloseLoad dinamik yorumlayıcısı hedef URL'yi eksiksiz çözmelidir")

        # 2. Telif Hakkı Uyarısı Testi
        mock_session = MagicMock()
        mock_copyright_resp = MagicMock(status_code=200, text="<html><body><div class='alert'>Telif nedeniyle bu içerik kaldırılmıştır.</div><!-- " + ("x" * 600) + " --></body></html>")
        mock_session.get.return_value = mock_copyright_resp
        with patch("extractor.requests.Session", return_value=mock_session):
            with self.assertRaises(RuntimeError) as ctx:
                resolve_film_page("https://filmmodu.live/izle/spider-man-brand-new-day")
            self.assertIn("telif hakkı nedeniyle", str(ctx.exception).lower())

    def test_C9_default_videos_download_dir_and_auto_recovery(self):
        from gui import get_default_download_directory, set_custom_download_directory, load_user_config
        import tempfile

        # 1. Varsayılan İndirme Klasörü Doğrulaması (Videos/VideoDownloaderPro)
        def_dir = get_default_download_directory()
        self.assertTrue(os.path.isabs(def_dir), "Varsayılan dizin mutlak bir dosya yolu olmalıdır")
        self.assertTrue("VideoDownloaderPro" in def_dir, "Varsayılan dizin 'VideoDownloaderPro' alt klasörünü içermelidir")
        self.assertTrue(os.path.exists(def_dir), "Varsayılan dizin otomatik olarak oluşturulmuş olmalıdır")

        # 2. Özel İndirme Klasörü Değiştirme ve Kalıcılık Doğrulaması
        with tempfile.TemporaryDirectory() as td:
            custom_target = os.path.join(td, "CustomDownloads")
            os.makedirs(custom_target, exist_ok=True)
            saved = set_custom_download_directory(custom_target)
            self.assertTrue(saved, "Özel klasör kaydedilebilmelidir")
            resolved_dir = get_default_download_directory()
            self.assertEqual(resolved_dir, custom_target, "Özel klasör öncelikli olarak döndürülmelidir")

            # Temizleme: Tekrar boşalt
            cfg = load_user_config()
            cfg.pop("download_dir", None)
            from gui import save_user_config
            save_user_config(cfg)

    def test_C10_dizitime_resolution(self):
        """DiziTime (dizitime.news) sayfalarının API uç noktası ve embed çözümlemesi doğrulanmalı."""
        from extractor import resolve_dizitime_page, resolve_film_page
        from unittest.mock import MagicMock, patch

        mock_html = """
        <html>
        <head><title>Dalliance 1.Sezon 5.Bölüm izle - Dizitime</title></head>
        <body>
        <select class="selectpicker show-tick vidsources">
            <option value="644414" data-name="DTime">Kaynak 1</option>
            <option value="644415" data-name="Moly">Kaynak 2</option>
        </select>
        </body></html>
        """

        with patch("extractor.c_requests") as mock_c:
            mock_sess = MagicMock()
            mock_c.Session.return_value = mock_sess

            # Page request
            resp_page = MagicMock()
            resp_page.text = mock_html
            resp_page.status_code = 200

            # Vid request 644415 -> 302 to Vidmoly
            resp_gv = MagicMock()
            resp_gv.status_code = 302
            resp_gv.headers = {"Location": "https://vidmoly.biz/embed-test1234.html"}

            mock_sess.get.side_effect = [resp_page, resp_gv]

            with patch("extractor.resolve_film_page") as mock_resolve:
                mock_resolve.return_value = {
                    "success": True,
                    "title": "Vidmoly Video",
                    "video_url": "https://fake-cdn.com/stream.m3u8",
                    "video_segments": ["https://fake-cdn.com/seg1.ts"],
                    "audio_tracks": [],
                    "total_segments": 1
                }

                res = resolve_dizitime_page("https://dizitime.news/dalliance/1-sezon-5-bolum-izle")
                self.assertIsNotNone(res)
                self.assertTrue(res.get("success"))
                self.assertEqual(res.get("title"), "Dalliance 1.Sezon 5.Bölüm izle")
                self.assertEqual(len(res.get("video_segments", [])), 1)

    def test_C11_unsupported_platforms_removal(self):
        """Kalitesiz ve atıl platformların (filmonline, filmmakinesi, hdflimizle) kaldırıldığı ve reddedildiği doğrulanmalı."""
        from extractor import resolve_film_page, ExtractorError

        for bad_url in [
            "https://filmonline.net/watch/movie/ct0ixV76B4Xd07FN",
            "https://filmmakinesi.to/film/son-gun-dogumu-2026/",
            "https://www.hdflimizle.net/melissa-p-izle/",
        ]:
            with self.assertRaises(ExtractorError) as ctx:
                resolve_film_page(bad_url)
            self.assertIn("desteklenmemektedir", str(ctx.exception).lower())

    def test_seven20p_extractor_success(self):
        """720pizle platformunun başarıyla çözümlendiği doğrulanmalı (mock test)."""
        from extractors.platforms.seven20p import Seven20pExtractor
        from unittest.mock import MagicMock, patch

        mock_html = '''
        <html>
        <head><title>The Banker izle - filmin bilgileri, konusu - 720pizle</title></head>
        <body>
        <div id="cstk">
            <iframe src="//four.pichive.online/iframe.php?v=fe2c4f67cbe115ab63f8ff8741febfc3"></iframe>
        </div>
        </body>
        </html>
        '''
        mock_pichive = {
            "video_url": "https://four.pichive.online/m.php?v=dummy_token",
            "base_host": "https://four.pichive.online",
            "subtitles": [{"url": "https://cdn.example.com/tr.vtt", "label": "Türkçe", "lang": "tur"}],
            "headers": {"User-Agent": "test", "Referer": "https://four.pichive.online/iframe.php?v=fe2c4f67cbe115ab63f8ff8741febfc3"}
        }

        mock_sess = MagicMock()
        mock_sess.get.return_value = MagicMock(status_code=200, text=mock_html)

        with patch("extractors.platforms.seven20p.resolve_pichive_embed", return_value=mock_pichive):
            ext = Seven20pExtractor()
            self.assertTrue(ext.can_handle("https://720pizle.my/izle/the-banker"))
            res = ext.extract("https://720pizle.my/izle/the-banker", session=mock_sess)
            self.assertIsNotNone(res)
            self.assertTrue(res.success)
            self.assertEqual(res.title, "The Banker")
            self.assertEqual(res.video_url, "https://four.pichive.online/m.php?v=dummy_token")
            self.assertEqual(len(res.subtitles), 1)

    def test_C12_subtitle_output_mode_config(self):
        """Altyazı çıktı modu ayarları ve yardımcı fonksiyonları doğru çalışmalı."""
        from gui import get_subtitle_output_mode, set_subtitle_output_mode, should_keep_external_srt
        from unittest.mock import patch

        fake_cfg = {}
        with patch("gui.load_user_config", side_effect=lambda: fake_cfg), \
             patch("gui.save_user_config", side_effect=lambda c: fake_cfg.update(c) or True):

            # Varsayılan mod
            self.assertEqual(get_subtitle_output_mode(), "embed_and_keep_srt")
            self.assertTrue(should_keep_external_srt())

            # Yalnızca gömme modu
            set_subtitle_output_mode("embed_only")
            self.assertEqual(get_subtitle_output_mode(), "embed_only")
            self.assertFalse(should_keep_external_srt())

            # Geri varsayılana alma
            set_subtitle_output_mode("embed_and_keep_srt")
            self.assertEqual(get_subtitle_output_mode(), "embed_and_keep_srt")
            self.assertTrue(should_keep_external_srt())

    def test_C13_engine_subtitle_cleanup_behavior(self):
        """keep_external_srt=False durumunda başarıyla muxlanan harici .srt silinmeli; True durumunda korunmalı."""
        import tempfile
        import shutil
        from unittest.mock import MagicMock, patch
        import engine

        tmp_dir = tempfile.mkdtemp()
        try:
            out_mp4 = os.path.join(tmp_dir, "test_movie.mp4")
            sub_srt = os.path.join(tmp_dir, "test_movie.srt")

            def fake_dl(tasks, headers, **kwargs):
                for t in tasks:
                    with open(t[2], "wb") as f:
                        f.write(b"tsdata")
                return len(tasks), len(tasks) * 6, set()

            def fake_mux(*args, **kwargs):
                out_p = kwargs.get("output_filepath") if "output_filepath" in kwargs else (args[2] if len(args) > 2 else out_mp4)
                with open(out_p, "wb") as f:
                    f.write(b"mp4dummy")
                return True

            # 1. keep_external_srt=False ve başarılı muxing -> .srt silinmeli
            with open(sub_srt, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:04,000\nTest\n")

            eng = engine.VideoDownloadEngine()
            with patch.object(eng, "download_stream_segments", side_effect=fake_dl), \
                 patch("engine.fetch_and_save_subtitle", return_value=sub_srt), \
                 patch.object(eng, "mux_multi_audio_and_video", side_effect=fake_mux):

                ok, msg = eng.run_multi_audio_download(
                    video_url="https://test.com/v.m3u8",
                    audio_tracks=[{
                        "name": "Ses",
                        "lang": "tur",
                        "url": "https://test.com/a.m3u8",
                        "segments": ["https://test.com/a1.ts"],
                    }],
                    output_filepath=out_mp4,
                    video_segments=["https://test.com/v1.ts"],
                    subtitles=[{"url": "https://test.com/sub.vtt", "name": "Türkçe"}],
                    keep_external_srt=False
                )
                self.assertTrue(ok, f"İndirme başarısız: {msg}")
                self.assertFalse(os.path.exists(sub_srt), "keep_external_srt=False iken .srt silinmeli")

            # 2. keep_external_srt=True ve başarılı muxing -> .srt korunmalı
            with open(sub_srt, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:04,000\nTest\n")

            with patch.object(eng, "download_stream_segments", side_effect=fake_dl), \
                 patch("engine.fetch_and_save_subtitle", return_value=sub_srt), \
                 patch.object(eng, "mux_multi_audio_and_video", side_effect=fake_mux):

                ok, msg = eng.run_multi_audio_download(
                    video_url="https://test.com/v.m3u8",
                    audio_tracks=[{
                        "name": "Ses",
                        "lang": "tur",
                        "url": "https://test.com/a.m3u8",
                        "segments": ["https://test.com/a1.ts"],
                    }],
                    output_filepath=out_mp4,
                    video_segments=["https://test.com/v1.ts"],
                    subtitles=[{"url": "https://test.com/sub.vtt", "name": "Türkçe"}],
                    keep_external_srt=True
                )
                self.assertTrue(ok, f"İndirme başarısız: {msg}")
                self.assertTrue(os.path.exists(sub_srt), "keep_external_srt=True iken .srt korunmalı")

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_C14_history_single_deletion_and_gui_binding(self):
        """Geçmiş kayıtlarının tekil olarak silinmesi ve GUI aksiyonları doğrulanmalı."""
        import tempfile
        import shutil
        from unittest.mock import MagicMock, patch
        from history import SQLiteHistoryManager, delete_history_entry

        tmp_dir = tempfile.mkdtemp()
        try:
            db_p = os.path.join(tmp_dir, "test_hist.db")
            mgr = SQLiteHistoryManager(db_p, legacy_json_path=None)

            e1 = mgr.add_entry("Film 1", "/path/1.mp4", 100 * 1024 * 1024)
            e2 = mgr.add_entry("Film 2", "/path/2.mp4", 200 * 1024 * 1024)
            self.assertEqual(mgr.count(), 2)

            with patch("history.get_manager", return_value=mgr):
                # e1 sil
                res = delete_history_entry(e1["id"])
                self.assertTrue(res)
                self.assertEqual(mgr.count(), 1)
                remaining = mgr.load_history()
                self.assertEqual(len(remaining), 1)
                self.assertEqual(remaining[0]["id"], e2["id"])

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_C15_notification_and_sound_config(self):
        """Masaüstü bildirimi ve ses ayarları getter/setter fonksiyonları doğru çalışmalı."""
        from gui import (
            get_notification_sound_enabled, set_notification_sound_enabled,
            get_desktop_notification_enabled, set_desktop_notification_enabled
        )
        from unittest.mock import patch

        fake_cfg = {}
        with patch("gui.load_user_config", side_effect=lambda: fake_cfg), \
             patch("gui.save_user_config", side_effect=lambda c: fake_cfg.update(c) or True):

            # Varsayılanlar True olmalı
            self.assertTrue(get_notification_sound_enabled())
            self.assertTrue(get_desktop_notification_enabled())

            # Ses kapatma / açma
            set_notification_sound_enabled(False)
            self.assertFalse(get_notification_sound_enabled())
            set_notification_sound_enabled(True)
            self.assertTrue(get_notification_sound_enabled())

            # Bildirim kapatma / açma
            set_desktop_notification_enabled(False)
            self.assertFalse(get_desktop_notification_enabled())
            set_desktop_notification_enabled(True)
            self.assertTrue(get_desktop_notification_enabled())


class TestFieldAuditFixes(unittest.TestCase):
    """
    Saha testi bulguları (Gruplar A-F) düzeltmelerini doğrulayan regresyon testleri:
    - Grup A & C: Altyazı önceliklendirmesi (Full diyalog > Zorunlu/Tabela/Forced)
    - Grup B: FFmpeg altyazı varsayılan disposition bayrağı (-disposition:s:0 default)
    - Grup D: Tolerans modu (<= 2 eksik segment için birleştirme toleransı)
    - Grup E & F: M3U8 altyazı ve çoklu ses kanalı çıkarma
    """

    def test_group_c_subtitle_priority_ranks_full_dialogue_above_forced(self):
        """Full Türkçe altyazının forced/tabela altyazısına göre öncelikli seçildiğini doğrular."""
        from engine import fetch_and_save_subtitle
        import tempfile
        from unittest.mock import patch, MagicMock

        subs = [
            {"name": "Türkçe (Forced / Tabela)", "lang": "tur", "forced": True, "url": "http://example.com/forced.vtt"},
            {"name": "Türkçe Tam Altyazı", "lang": "tur", "forced": False, "url": "http://example.com/full.vtt"},
            {"name": "English Subtitle", "lang": "eng", "forced": False, "url": "http://example.com/en.vtt"},
        ]

        called_urls = []

        def fake_get(url, **kwargs):
            called_urls.append(url)
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.content = b"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nMerhaba Dunya\n"
            return mock_res

        with tempfile.TemporaryDirectory() as td:
            out_file = os.path.join(td, "test_movie.mp4")
            with patch("requests.Session.get", side_effect=fake_get):
                res = fetch_and_save_subtitle(subs, out_file)
                self.assertIsNotNone(res)
                # İlk indirilen ve seçilen url tam altyazı olmalı
                self.assertEqual(called_urls[0], "http://example.com/full.vtt")

    def test_group_b_ffmpeg_subtitle_disposition_present(self):
        """Mux komutlarında -disposition:s:0 default parametresinin yer aldığını doğrular."""
        import inspect
        import engine

        mux_single_src = inspect.getsource(engine.VideoDownloadEngine.mux_video_and_audio)
        self.assertIn('"-disposition:s:0", "default"', mux_single_src)

        mux_multi_src = inspect.getsource(engine.VideoDownloadEngine.mux_multi_audio_and_video)
        self.assertIn('"-disposition:s:0", "default"', mux_multi_src)

    def test_group_d_incomplete_streams_are_never_muxed(self):
        """Tek bir eksik video veya ses segmenti bile mux aşamasına geçmemeli."""
        import inspect
        import engine

        single_src = inspect.getsource(engine.VideoDownloadEngine.run_download)
        self.assertNotIn("_is_tolerable_single", single_src)
        self.assertNotIn("Tolerans Modu", single_src)
        self.assertIn("if v_missing:", single_src)

        multi_src = inspect.getsource(engine.VideoDownloadEngine.run_multi_audio_download)
        self.assertNotIn("def _is_tolerable", multi_src)
        self.assertNotIn("Tolerans Modu", multi_src)
        self.assertIn("if v_missing:", multi_src)
        self.assertIn("if a_missing:", multi_src)

    def test_group_a_m3u8_and_track_subtitle_helpers(self):
        """_extract_subtitles_from_m3u8 ve _extract_subtitles_from_tracks fonksiyonlarının doğruluğu."""
        from extractor import _extract_subtitles_from_m3u8, _extract_subtitles_from_tracks

        sample_m3u8 = """#EXTM3U
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Türkçe",DEFAULT=YES,AUTOSELECT=YES,FORCED=NO,LANGUAGE="tur",URI="sub_tr.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Türkçe (Forced)",DEFAULT=NO,AUTOSELECT=NO,FORCED=YES,LANGUAGE="tur",URI="sub_tr_forced.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=2000000,SUBTITLES="subs"
720p.m3u8
"""
        subs = _extract_subtitles_from_m3u8(sample_m3u8, base_url="https://stream.example.com/live/master.m3u8")
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0]["name"], "Türkçe")
        self.assertFalse(subs[0]["forced"])
        self.assertEqual(subs[0]["url"], "https://stream.example.com/live/sub_tr.m3u8")
        self.assertTrue(subs[1]["forced"])

        sample_html = """
        <script>
        var player = jwplayer("player").setup({
            tracks: [{"file": "/subtitles/tr.vtt", "label": "Türkçe", "kind": "subtitles", "default": true}]
        });
        </script>
        """
        tr_subs = _extract_subtitles_from_tracks(sample_html, base_url="https://film.example.com/watch")
        self.assertEqual(len(tr_subs), 1)
        self.assertEqual(tr_subs[0]["label"], "Türkçe")
        self.assertEqual(tr_subs[0]["url"], "https://film.example.com/subtitles/tr.vtt")


# =============================================================================
# G. 2. Tur Kıdemli Denetim (Senior Audit) Regresyon Testleri
# =============================================================================
class TestSeniorAuditPhase2Regressions(unittest.TestCase):

    def test_G1_total_segments_none_raises_download_error_safely(self):
        """total_segments None iken TypeError: unsupported operand type yerine DownloadError veya temiz hata döner."""
        eng = engine.VideoDownloadEngine()
        with patch.object(eng, '_session') as mock_sess, \
             patch('engine.parse_segment_url', return_value=('https://example.com/seg_', 1, 3, '.ts', '')):
            with patch('engine.detect_segment_range', return_value=(0, None)):
                success, msg = eng.run_download('https://example.com/seg_001.ts', 'test.mp4')
                self.assertFalse(success)
                self.assertIn("Segment aralığı tespit edilemedi", msg)

    def test_G2_dead_doh_and_gui_functions_removed(self):
        """Atıl fonksiyonlar engine ve gui modüllerinden tamamen temizlenmiş olmalıdır."""
        import gui
        self.assertFalse(hasattr(engine, 'resolve_domain_doh'), "engine.resolve_domain_doh silinmeli")
        self.assertFalse(hasattr(gui.VideoDownloaderGUI, '_open_file_folder'), "gui._open_file_folder silinmeli")

    def test_G3_no_unused_imports_in_registry_and_extractors(self):
        """extractors/registry.py ve generic_hls.py içinde atıl import kalmamalıdır."""
        import extractors.registry as reg
        import extractors.generic_hls as ghls
        import extractors.series_film as sfilm
        
        reg_src = open(reg.__file__, encoding="utf-8").read()
        self.assertNotIn("from extractors.base import BaseExtractor, ExtractorResult", reg_src)
        self.assertNotIn("from typing import List, Optional, Dict, Any", reg_src)

        ghls_src = open(ghls.__file__, encoding="utf-8").read()
        self.assertNotIn("import json", ghls_src)
        self.assertNotIn("from typing import Optional", ghls_src)
        self.assertNotIn("from urllib.parse import urljoin", ghls_src)

        sfilm_src = open(sfilm.__file__, encoding="utf-8").read()
        self.assertNotIn("from extractors.generic_hls import decrypt_cryptojs_aes, unpack_js", sfilm_src)

    def test_G4_probe_timeout_is_safe_30s(self):
        """FFmpeg tekil dosya metadata sorgusu 600s yerine güvenli 30s timeout ile çalışmalıdır."""
        engine_src = open(engine.__file__, encoding="utf-8").read()
        self.assertIn("probe_proc.communicate(timeout=30)", engine_src)
        self.assertNotIn("probe_proc.communicate(timeout=600)", engine_src)

    def test_G5_remux_timeout_is_300s(self):
        """4K büyük filmlerde remux zaman aşımı 120s yerine en az 300s olarak yapılandırılmalıdır."""
        engine_src = open(engine.__file__, encoding="utf-8").read()
        self.assertIn("timeout=300", engine_src)


if __name__ == "__main__":
    unittest.main()

