import os
import time
import shutil
import threading
import unittest
from unittest.mock import patch
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from engine import (
    parse_segment_url,
    build_segment_url,
    detect_segment_range,
    parse_curl_command,
    get_ffmpeg_path,
    VideoDownloadEngine
)


class MockSegmentHandler(BaseHTTPRequestHandler):
    SEGMENT_COUNT = 15
    REQUIRED_REFERER = "https://mocksite.com/"

    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self._handle_request(is_head=True)

    def do_GET(self):
        self._handle_request(is_head=False)

    def _handle_request(self, is_head=False):
        parsed = urlparse(self.path)
        path = parsed.path

        referer = self.headers.get("Referer", "")
        if self.REQUIRED_REFERER not in referer and "mocksite" not in referer:
            self.send_response(403)
            self.end_headers()
            return

        if "/video/seg_" in path or "/audio/seg_" in path:
            filename = os.path.basename(path)
            try:
                seg_num_str = filename.replace("seg_", "").replace(".jpg", "").replace(".png", "")
                seg_num = int(seg_num_str)

                if 0 <= seg_num <= self.SEGMENT_COUNT:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    content = f"MOCK_DATA_{seg_num:05d}".encode("utf-8") * 64
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    if not is_head:
                        self.wfile.write(content)
                    return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return

        self.send_response(404)
        self.end_headers()


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HTTPServer.allow_reuse_address = True
        cls.server = HTTPServer(("127.0.0.1", 0), MockSegmentHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}/video/seg_"
        cls.audio_url = f"http://127.0.0.1:{cls.port}/audio/seg_"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_scratch")
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_parse_segment_url(self):
        prefix, pad, ext, query, sample_idx = parse_segment_url("https://cdn.example.com/hls/seg_025.jpg")
        self.assertEqual(prefix, "https://cdn.example.com/hls/seg_")
        self.assertEqual(pad, 3)
        self.assertEqual(ext, ".jpg")
        self.assertEqual(query, "")
        self.assertEqual(sample_idx, 25)

        prefix2, pad2, ext2, query2, sample_idx2 = parse_segment_url("https://cdn.example.com/v/chunk-001.ts?token=xyz123&exp=999")
        self.assertEqual(prefix2, "https://cdn.example.com/v/chunk-")
        self.assertEqual(pad2, 3)
        self.assertEqual(ext2, ".ts")
        self.assertEqual(query2, "?token=xyz123&exp=999")
        self.assertEqual(sample_idx2, 1)

    def test_02_parse_cmd_curl(self):
        cmd_str = (
            'curl --url ^"https://s6.maymun.shop/cdn/down/Movie/video/seg_013.jpg^" ^\n'
            '  -H ^"Referer: https://setplay.shop/^" ^\n'
            '  -H ^"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)^" ^\n'
            '  --cookie ^"session_id=abcdef123^"'
        )
        url, headers = parse_curl_command(cmd_str)
        self.assertEqual(url, "https://s6.maymun.shop/cdn/down/Movie/video/seg_013.jpg")
        self.assertEqual(headers.get("Referer"), "https://setplay.shop/")
        self.assertEqual(headers.get("Cookie"), "session_id=abcdef123")

    def test_03_detect_segment_range(self):
        headers = {"Referer": "https://mocksite.com/"}
        start_idx, total_segs = detect_segment_range(
            prefix=self.base_url,
            padding=3,
            ext=".jpg",
            query_fragment="",
            headers=headers,
            sample_index=1
        )
        self.assertEqual(start_idx, 0)
        self.assertEqual(total_segs, MockSegmentHandler.SEGMENT_COUNT)

    def test_04_download_and_binary_merge(self):
        output_file = os.path.join(self.test_dir, "test_complete_video.mp4")
        sample_url = f"{self.base_url}001.jpg"

        engine = VideoDownloadEngine()
        success, result = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file,
            referer="https://mocksite.com/",
            thread_count=4
        )

        self.assertTrue(success, f"İndirme başarısız oldu: {result}")
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(os.path.getsize(output_file), 1000)

    def test_06_cancel_with_cleanup_deletes_temp_dir(self):
        """Cancel with cleanup=True removes temporary files."""
        engine = VideoDownloadEngine()
        dummy_temp = os.path.join(self.test_dir, ".temp_test_cancel_cleanup")
        os.makedirs(dummy_temp, exist_ok=True)
        dummy_file = os.path.join(dummy_temp, "seg_001.tmp")
        with open(dummy_file, "wb") as f:
            f.write(b"data")

        engine.active_temp_dir = dummy_temp
        engine.cancel(cleanup=True)
        self.assertTrue(engine.cancel_event.is_set())
        self.assertFalse(os.path.exists(dummy_temp))

    def test_07_pause_preserves_temp_dir(self):
        """Pause sets cancel_event without deleting temporary files."""
        engine = VideoDownloadEngine()
        dummy_temp = os.path.join(self.test_dir, ".temp_test_pause")
        os.makedirs(dummy_temp, exist_ok=True)
        dummy_file = os.path.join(dummy_temp, "seg_001.tmp")
        with open(dummy_file, "wb") as f:
            f.write(b"data")

        engine.active_temp_dir = dummy_temp
        engine.pause()
        self.assertTrue(engine.cancel_event.is_set())
        self.assertFalse(engine.cleanup_on_cancel)
        self.assertTrue(os.path.exists(dummy_temp))
        self.assertTrue(os.path.exists(dummy_file))

    def test_08_real_pause_and_resume_download(self):
        """Gerçek Pause -> Temp Koruması -> Resume -> %100 Başarı ve İntakt Çıktı Entegrasyon Testi."""
        output_file = os.path.join(self.test_dir, "test_paused_resumed_video.mp4")
        sample_url = f"{self.base_url}001.jpg"
        engine = VideoDownloadEngine()

        pause_triggered = threading.Event()

        def on_progress(completed, total, bytes_down, speed):
            # 2 segment indirildikten sonra duraklat
            if completed >= 2 and not pause_triggered.is_set():
                pause_triggered.set()
                engine.pause()

        # 1. Adım: İndirmeyi başlat ve duraklat
        success_p1, msg_p1 = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file,
            referer="https://mocksite.com/",
            thread_count=2,
            progress_callback=on_progress
        )

        self.assertFalse(success_p1, "Duraklatılan ilk adım False dönmelidir.")
        self.assertTrue(engine.cancel_event.is_set())
        self.assertFalse(engine.cleanup_on_cancel)

        # Temp dizininin ve inen parçaların korunduğunu doğrula
        temp_dir = engine.active_temp_dir
        self.assertTrue(os.path.exists(temp_dir), "Duraklatma sonrasında temp klasörü korunmalıdır.")
        downloaded_segs = [f for f in os.listdir(temp_dir) if f.endswith(".tmp") and os.path.getsize(os.path.join(temp_dir, f)) > 0]
        self.assertGreaterEqual(len(downloaded_segs), 1, "En az 1 segment indirilmiş olarak korunmalıdır.")

        # 2. Adım: Devam Et (Resume) - Kaldığı yerden devam etmeli
        success_p2, msg_p2 = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file,
            referer="https://mocksite.com/",
            thread_count=4
        )

        self.assertTrue(success_p2, f"Devam ettirilen indirme başarılı olmalıdır: {msg_p2}")
        self.assertTrue(os.path.exists(output_file), "Final çıktı dosyası oluşturulmuş olmalıdır.")
        self.assertGreater(os.path.getsize(output_file), 1000, "Final dosya boyutu geçerli olmalıdır.")
        self.assertFalse(os.path.exists(temp_dir), "İndirme bitince temp klasörü temizlenmelidir.")

    def test_09_cancel_then_new_download_lifecycle(self):
        """Cancel -> Temp Temizliği -> Yeni İndirme (reset_cancel) Yaşam Döngüsü Testi."""
        output_file_a = os.path.join(self.test_dir, "test_video_cancelled.mp4")
        output_file_b = os.path.join(self.test_dir, "test_video_new.mp4")
        sample_url = f"{self.base_url}001.jpg"
        engine = VideoDownloadEngine()

        cancel_triggered = threading.Event()

        def on_progress(completed, total, bytes_down, speed):
            if completed >= 1 and not cancel_triggered.is_set():
                cancel_triggered.set()
                engine.cancel(cleanup=True)

        # 1. İndirme: İptal et
        success_a, msg_a = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file_a,
            referer="https://mocksite.com/",
            thread_count=2,
            progress_callback=on_progress
        )

        self.assertFalse(success_a)
        temp_dir_a = engine.active_temp_dir
        if temp_dir_a:
            self.assertFalse(os.path.exists(temp_dir_a), "İptal edilen indirme temp klasörünü temizlemelidir.")

        # 2. İndirme: Aynı motor üzerinde yeni görev başlat (otomatik reset_cancel testi)
        success_b, msg_b = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file_b,
            referer="https://mocksite.com/",
            thread_count=4
        )

        self.assertTrue(success_b, f"Yeni indirme otomatik reset ile başarılı olmalıdır: {msg_b}")
        self.assertTrue(os.path.exists(output_file_b))

    def test_10_cleanup_filesystem_path_robustness(self):
        """Salt-okunur dosyalar ve iç içe klasörlerde temizleme direnci testi."""
        from engine import cleanup_filesystem_path
        import stat

        test_cleanup_dir = os.path.join(self.test_dir, "test_readonly_cleanup_dir")
        os.makedirs(test_cleanup_dir, exist_ok=True)
        nested_file = os.path.join(test_cleanup_dir, "readonly_file.tmp")
        with open(nested_file, "w") as f:
            f.write("readonly content")

        # Dosyayı salt-okunur (read-only) yap
        os.chmod(nested_file, stat.S_IREAD)

        # Temizleyici çağır
        res = cleanup_filesystem_path(test_cleanup_dir)
        self.assertTrue(res)
        self.assertFalse(os.path.exists(test_cleanup_dir))

    @patch("engine.VideoDownloadEngine.mux_multi_audio_and_video")
    def test_11_multi_audio_real_loopback_download_and_resume(self, mock_mux):
        """Çoklu Ses (Multi-Audio) İndirme: Duraklatma, Parça Koruma ve Eksiksiz Devam Etme Testi."""
        mock_mux.return_value = True
        output_file = os.path.join(self.test_dir, "test_multiaudio_lifecycle.mp4")
        sample_v = f"{self.base_url}001.jpg"
        audio_tracks = [
            {"name": "Turkish", "lang": "tr", "sample_segment_url": f"{self.audio_url}001.jpg", "count": 6, "headers": {"Referer": "https://mocksite.com/"}},
            {"name": "English", "lang": "en", "sample_segment_url": f"{self.audio_url}001.jpg", "count": 6, "headers": {"Referer": "https://mocksite.com/"}}
        ]
        engine = VideoDownloadEngine()
        pause_triggered = threading.Event()

        def on_progress(completed, total, bytes_down, speed):
            if completed >= 2 and not pause_triggered.is_set():
                pause_triggered.set()
                engine.pause()

        # 1. Adım: Başlat ve Duraklat
        success_1, msg_1 = engine.run_multi_audio_download(
            video_url=sample_v,
            audio_tracks=audio_tracks,
            output_filepath=output_file,
            video_headers={"Referer": "https://mocksite.com/"},
            total_segments=6,
            thread_count=4,
            progress_callback=on_progress
        )

        self.assertFalse(success_1, "Duraklatılan çoklu ses ilk adım False dönmelidir.")
        temp_dir = engine.active_temp_dir
        self.assertTrue(os.path.exists(temp_dir), "Temp klasörü duraklatma sonrasında korunmalıdır.")

        # Diskte hem video hem de ses parçalarının silinmeden korunduğunu doğrula
        preserved_files = os.listdir(temp_dir)
        v_segs = [f for f in preserved_files if f.startswith("v_seg_")]
        a_segs = [f for f in preserved_files if f.startswith("a0_seg_") or f.startswith("a1_seg_")]
        self.assertGreaterEqual(len(v_segs) + len(a_segs), 1, "İndirilen parçalar duraklatma sonrasında korunmuş olmalıdır.")

        # 2. Adım: Devam Et (Resume)
        success_2, msg_2 = engine.run_multi_audio_download(
            video_url=sample_v,
            audio_tracks=audio_tracks,
            output_filepath=output_file,
            video_headers={"Referer": "https://mocksite.com/"},
            total_segments=6,
            thread_count=4
        )

        self.assertTrue(success_2, f"Çoklu ses devam ettirildiğinde başarılı olmalıdır: {msg_2}")
        mock_mux.assert_called()

    def test_12_corrupted_partial_segment_cache_handling(self):
        """Bozuk / 512 bayttan küçük önbellek parçalarının tespit edilip yeniden indirilmesi testi."""
        import re
        output_file = os.path.join(self.test_dir, "test_corrupt_cache.mp4")
        sample_url = f"{self.base_url}001.jpg"
        engine = VideoDownloadEngine()

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(output_file))[0])
        temp_dir = os.path.join(os.path.dirname(output_file), f".temp_{safe_name}")
        os.makedirs(temp_dir, exist_ok=True)

        # 10 baytlık bozuk/yarım kalmış bir geçici dosya simüle et
        corrupted_seg = os.path.join(temp_dir, "seg_0000001.tmp")
        with open(corrupted_seg, "wb") as f:
            f.write(b"CORRUPT123")

        self.assertLess(os.path.getsize(corrupted_seg), 512)

        # İndirmeyi çalıştır -> Bozuk parçayı algılayıp yeniden indirmeli
        success, msg = engine.run_download(
            sample_url=sample_url,
            output_filepath=output_file,
            referer="https://mocksite.com/",
            thread_count=4
        )

        self.assertTrue(success, f"Bozuk segment başarıyla telafi edilip tamamlanmalıdır: {msg}")
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(os.path.getsize(output_file), 1000)

    def test_14_dual_stream_end_to_end_with_separate_audio(self):
        """C6: run_dual_stream_download -> run_multi_audio_download devri gerçekten çalışmalı."""
        from unittest.mock import patch as _patch
        output_file = os.path.join(self.test_dir, "test_dual_e2e.mp4")
        eng = VideoDownloadEngine()

        v_segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 6)]
        a_segs = [f"{self.audio_url}{i:03d}.jpg" for i in range(1, 6)]
        hdrs = {"Referer": "https://mocksite.com/"}

        def fake_mux(video_concat_path, audio_concat_path, output_filepath, **kw):
            with open(output_filepath, "wb") as out:
                for src in (video_concat_path, audio_concat_path):
                    if os.path.exists(src):
                        with open(src, "rb") as f:
                            out.write(f.read())
            return True

        with _patch.object(VideoDownloadEngine, "mux_video_and_audio", side_effect=fake_mux) as m:
            ok, res = eng.run_dual_stream_download(
                video_url=v_segs[0],
                audio_url=a_segs[0],
                output_filepath=output_file,
                video_headers=hdrs,
                audio_headers=hdrs,
                video_segments=v_segs,
                audio_segments=a_segs,
                thread_count=4,
            )

        self.assertTrue(ok, f"Çift akış indirmesi başarısız: {res}")
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(os.path.getsize(output_file), 0)
        # Tek ses kanalinda sade muxer kullanilmali (cok kanalli olan degil)
        m.assert_called_once()

    def test_15_dual_stream_recovers_after_previous_cancellation(self):
        """A6: iptal edilmiş bir indirmeden sonra çift akış anında iptal dönmemeli."""
        from unittest.mock import patch as _patch
        output_file = os.path.join(self.test_dir, "test_dual_after_cancel.mp4")
        eng = VideoDownloadEngine()

        v_segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 4)]
        a_segs = [f"{self.audio_url}{i:03d}.jpg" for i in range(1, 4)]
        hdrs = {"Referer": "https://mocksite.com/"}

        # Onceki kuyruk ogesi iptal edilmis gibi davran
        eng.cancel(cleanup=False)
        self.assertTrue(eng.cancel_event.is_set())

        def fake_mux(video_concat_path, audio_concat_path, output_filepath, **kw):
            with open(output_filepath, "wb") as out:
                out.write(b"OK")
            return True

        with _patch.object(VideoDownloadEngine, "mux_video_and_audio", side_effect=fake_mux):
            ok, res = eng.run_dual_stream_download(
                video_url=v_segs[0], audio_url=a_segs[0],
                output_filepath=output_file,
                video_headers=hdrs, audio_headers=hdrs,
                video_segments=v_segs, audio_segments=a_segs,
                thread_count=2,
            )

        self.assertTrue(ok, f"İptal bayrağı temizlenmemiş (A6): {res}")
        self.assertNotIn("iptal", str(res).lower())

    def test_16_dual_stream_without_audio_falls_back_to_single_stream(self):
        """C6: ses kaynağı yoksa tekil akış indiricisine yönlendirilmeli."""
        output_file = os.path.join(self.test_dir, "test_dual_no_audio.mp4")
        eng = VideoDownloadEngine()
        v_segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 5)]

        ok, res = eng.run_dual_stream_download(
            video_url=v_segs[0], audio_url=None,
            output_filepath=output_file,
            video_headers={"Referer": "https://mocksite.com/"},
            video_segments=v_segs,
            thread_count=2,
        )

        self.assertTrue(ok, f"Sessiz akış tekil indiriciye düşmeli: {res}")
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(os.path.getsize(output_file), 0)

    def test_17_merge_mode_binary_skips_ffmpeg_remux(self):
        """B10: --merge binary seçeneği FFmpeg remux'ı gerçekten atlamalı."""
        from unittest.mock import patch as _patch
        output_file = os.path.join(self.test_dir, "test_merge_binary.mp4")
        eng = VideoDownloadEngine()
        segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 5)]

        with _patch("engine.subprocess.run") as mock_run:
            ok, res = eng.run_download(
                sample_url=segs[0],
                output_filepath=output_file,
                referer="https://mocksite.com/",
                segment_urls=segs,
                thread_count=2,
                merge_mode="binary",
            )

        self.assertTrue(ok, f"binary birleştirme başarısız: {res}")
        self.assertFalse(mock_run.called, "merge_mode='binary' iken FFmpeg çağrılmamalı (B10)")
        self.assertTrue(os.path.exists(output_file))


    def test_13_rapid_pause_resume_spam_concurrency(self):
        """Eşzamanlı hızlı duraklat/başlat spam sinyallerine karşı motor kararlılığı testi."""
        engine = VideoDownloadEngine()
        for _ in range(50):
            engine.pause()
            self.assertTrue(engine.cancel_event.is_set())
            self.assertFalse(engine.cleanup_on_cancel)
            engine.reset_cancel()
            self.assertFalse(engine.cancel_event.is_set())
            self.assertTrue(engine.cleanup_on_cancel)

    def test_16_multi_audio_concurrent_stream_execution(self):
        """4.A & 4.B: run_multi_audio_download video ve ses akışlarını eşzamanlı (paralel) çalıştırmalı."""
        from unittest.mock import patch as _patch
        import time

        output_file = os.path.join(self.test_dir, "test_concurrent_streams.mp4")
        eng = VideoDownloadEngine()

        call_intervals = []
        lock = threading.Lock()
        orig_dl = eng.download_stream_segments

        def instrumented_dl(tasks, headers, thread_count, progress_callback=None, log_callback=None):
            t_start = time.time()
            time.sleep(0.06)  # Simulate network latency to measure concurrency overlap
            res = orig_dl(tasks, headers, thread_count, progress_callback, log_callback)
            t_end = time.time()
            with lock:
                call_intervals.append((t_start, t_end))
            return res

        v_segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 4)]
        a_segs = [f"{self.audio_url}{i:03d}.jpg" for i in range(1, 4)]
        hdrs = {"Referer": "https://mocksite.com/"}

        def fake_mux(*args, **kwargs):
            return True

        with _patch.object(eng, "download_stream_segments", side_effect=instrumented_dl), \
             _patch.object(eng, "mux_multi_audio_and_video", side_effect=fake_mux):
            ok, msg = eng.run_multi_audio_download(
                video_url=v_segs[0],
                audio_tracks=[{"name": "Ses 1", "lang": "tur", "segments": a_segs, "headers": hdrs}],
                output_filepath=output_file,
                video_segments=v_segs,
                video_headers=hdrs,
                thread_count=4
            )

        self.assertTrue(ok, f"İndirme başarılı olmalı: {msg}")
        self.assertGreaterEqual(len(call_intervals), 2, "En az iki akış indirilmiş olmalı.")

        # Zaman aralıklarının çakıştığını (eşzamanlı çalıştığını) doğrula
        s1, e1 = call_intervals[0]
        s2, e2 = call_intervals[1]
        overlap = max(s1, s2) < min(e1, e2)
        self.assertTrue(overlap, f"Video ve ses akışları sıralı değil, paralel çalışmalıdır. Aralık 1: {s1}-{e1}, Aralık 2: {s2}-{e2}")

    def test_18_dynamic_worker_handoff_turbo_boost(self):
        """Video tamamlandığında kalan ses akışına dinamik worker devri ve Turbo Boost etkinleştirilmeli."""
        from unittest.mock import patch as _patch
        import time

        output_file = os.path.join(self.test_dir, "test_turbo_boost.mp4")
        eng = VideoDownloadEngine()

        self.assertFalse(eng.is_turbo_boosted(), "Başlangıçta Turbo Boost kapalı olmalıdır.")

        turbo_seen = []
        orig_dl = eng.download_stream_segments

        def instrumented_dl(tasks, headers, thread_count, progress_callback=None, log_callback=None):
            # İlk akış (video) çok hızlı bitsin, ikinci akış (ses) biraz daha uzun sürsün
            is_audio = any("audio" in t[1] for t in tasks)
            if is_audio:
                # Video bittikten sonra turbo boost durumunu gözlemlemek için bekle
                for _ in range(10):
                    if eng.is_turbo_boosted():
                        turbo_seen.append(True)
                        break
                    time.sleep(0.03)
            else:
                # Video akışı anında bitsin
                time.sleep(0.01)
            return orig_dl(tasks, headers, thread_count, progress_callback, log_callback)

        v_segs = [f"{self.base_url}{i:03d}.jpg" for i in range(1, 3)]
        a_segs = [f"{self.audio_url}{i:03d}.jpg" for i in range(1, 3)]
        hdrs = {"Referer": "https://mocksite.com/"}

        with _patch.object(eng, "download_stream_segments", side_effect=instrumented_dl), \
             _patch.object(eng, "mux_multi_audio_and_video", return_value=True):
            ok, msg = eng.run_multi_audio_download(
                video_url=v_segs[0],
                audio_tracks=[{"name": "Ses 1", "lang": "tur", "segments": a_segs, "headers": hdrs}],
                output_filepath=output_file,
                video_segments=v_segs,
                video_headers=hdrs,
                thread_count=16
            )

        self.assertTrue(ok, f"İndirme başarılı olmalı: {msg}")
        self.assertTrue(len(turbo_seen) > 0, "Video bittiğinde ses akışı sırasında Turbo Boost tetiklenmeliydi.")

        # reset_cancel sonrası Turbo Boost sıfırlanmalı
        eng.reset_cancel()
        self.assertFalse(eng.is_turbo_boosted(), "reset_cancel çağrısı Turbo Boost bayrağını sıfırlamalıdır.")


if __name__ == "__main__":
    unittest.main()


