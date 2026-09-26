# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Stream Orchestration, Master Playlist, and YouTube Engine.
"""

import os
import re
import sys
import time
import tempfile
import threading
import shutil
import subprocess
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from engine_core.crypto import derive_hls_iv, decrypt_hls_segment
from engine_core.utils import (
    cleanup_filesystem_path,
    is_valid_segment_file,
    format_human_duration,
    format_human_filesize,
    parse_segment_url,
    build_segment_url,
    probe_url,
    _close_owned,
)
from engine_core.ffmpeg import (
    get_ffmpeg_path,
    fetch_and_save_subtitle,
    write_concat_file,
    FFmpegMixin,
    _run_subprocess,
)
from engine_core.downloader import SegmentDownloaderMixin
from engine_core.recovery import write_recovery_state, update_recovery_progress

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

try:
    from exceptions import (
        VideoDownloaderError,
        DownloadError,
        FFmpegNotFoundError,
        CancelledError,
    )
except ImportError:
    try:
        from core.exceptions import (
            VideoDownloaderError,
            DownloadError,
            FFmpegNotFoundError,
            CancelledError,
        )
    except ImportError:
        class VideoDownloaderError(Exception): pass
        class DownloadError(VideoDownloaderError): pass
        class FFmpegNotFoundError(VideoDownloaderError): pass
        class CancelledError(VideoDownloaderError): pass

logger = get_logger("engine_core.pipeline")

_INTERNAL_STREAM_HEADER_KEYS = {"aes_key", "aes_iv", "aes_media_sequence"}


def _transport_headers(headers):
    """Return HTTP-safe headers without downloader-only HLS metadata."""
    return {
        key: value
        for key, value in dict(headers or {}).items()
        if str(key).lower() not in _INTERNAL_STREAM_HEADER_KEYS
    }


def _close_response(response):
    if response is not None and hasattr(response, "close"):
        try:
            response.close()
        except Exception:
            logger.debug("HLS response could not be closed", exc_info=True)


def _hls_timelines_aligned(video_durations, audio_durations, tolerance_seconds=1.0):
    """Return whether two HLS rendition timelines have materially equal length."""
    if not video_durations or not audio_durations:
        return True
    video_values = [float(value) for value in video_durations if value is not None]
    audio_values = [float(value) for value in audio_durations if value is not None]
    if not video_values or not audio_values:
        return True
    tolerance = float(tolerance_seconds)
    if abs(sum(video_values) - sum(audio_values)) <= tolerance:
        return True
    if len(video_values) != len(audio_values):
        return False

    # HLS paketleyicileri son ses segmentini video bitisinden daha uzun tutabilir.
    # FFmpeg `-shortest` bu yalnizca-son-segment kuyrugunu guvenle keser. Gercek
    # drift ise ara segment baslangiclarinin kademeli olarak ayrismasiyla gorulur.
    video_elapsed = 0.0
    audio_elapsed = 0.0
    for video_duration, audio_duration in zip(video_values[:-1], audio_values[:-1]):
        video_elapsed += video_duration
        audio_elapsed += audio_duration
        if abs(video_elapsed - audio_elapsed) > tolerance:
            return False
    return True


def _get_engine_symbol(name, default):
    """Dynamic lookup from engine facade so unittest.mock.patch('engine.X') is respected."""
    eng = sys.modules.get("engine")
    if eng and hasattr(eng, name):
        return getattr(eng, name)
    return default


def extract_m3u8_info(m3u8_url, custom_headers=None, max_depth=3, return_timeline=False):
    """
    M3U8 Manifest URL'sinden (Master veya Media Playlist) tüm segment URL'lerini
    ve fMP4 init segmentini ayrıştırır.
    İç içe (Master) playlist'lerde en yüksek çözünürlük/bant genişliğine sahip akışı seçer.
    Segment tokenlarının süresini kontrol eder (Fix 5).
    """
    if not m3u8_url or max_depth <= 0:
        return ([], []) if return_timeline else []

    domain_match = re.search(r'https?://[^/]+', m3u8_url)
    referer = domain_match.group(0) if domain_match else "https://google.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "*/*"
    }
    if custom_headers:
        headers.update(_transport_headers(custom_headers))

    text = None
    # 1. requests ile dene
    r = None
    try:
        r = requests.get(m3u8_url, headers=headers, timeout=10)
        if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXT-X" in r.text):
            text = r.text
    except Exception:
        logger.debug("[engine.py:277] extract_m3u8_info() sessiz istisna yutuldu", exc_info=True)
    finally:
        _close_response(r)

    # 2. curl_cffi ile dene (Cloudflare / WAF koruması varsa)
    if text is None and c_requests:
        r_c = None
        try:
            r_c = c_requests.get(m3u8_url, headers=headers, impersonate="chrome124", timeout=10)
            if r_c.status_code == 200 and ("#EXTM3U" in r_c.text or "#EXT-X" in r_c.text):
                text = r_c.text
        except Exception:
            logger.debug("[engine.py:286] extract_m3u8_info() sessiz istisna yutuldu", exc_info=True)
        finally:
            _close_response(r_c)

    if not text:
        return ([], []) if return_timeline else []

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Master Playlist Kontrolü (#EXT-X-STREAM-INF)
    has_variants = any(l.startswith("#EXT-X-STREAM-INF") for l in lines)
    if has_variants:
        variants = []
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                bw_m = re.search(r'BANDWIDTH=(\d+)', l)
                bw = int(bw_m.group(1)) if bw_m else 0
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if not next_line.startswith("#"):
                        v_url = urljoin(m3u8_url, next_line)
                        variants.append((bw, v_url))
        if variants:
            # En yüksek bant genişliği olan alt playlist'i seç
            variants.sort(key=lambda x: x[0], reverse=True)
            best_variant_url = variants[0][1]
            return extract_m3u8_info(
                best_variant_url,
                custom_headers=custom_headers,
                max_depth=max_depth - 1,
                return_timeline=return_timeline,
            )

    media_sequence = 0
    sequence_line = next((line for line in lines if line.startswith("#EXT-X-MEDIA-SEQUENCE:")), None)
    if sequence_line:
        try:
            media_sequence = int(sequence_line.partition(":")[2].strip())
        except ValueError:
            logger.warning("Invalid HLS media sequence ignored: %s", sequence_line)

    key_line = next((line for line in lines if line.startswith("#EXT-X-KEY:")), None)
    if key_line and isinstance(custom_headers, dict):
        method_match = re.search(r'METHOD=([^,\s]+)', key_line, re.IGNORECASE)
        method = method_match.group(1).upper() if method_match else ""
        if method == "NONE":
            for metadata_key in _INTERNAL_STREAM_HEADER_KEYS:
                custom_headers.pop(metadata_key, None)
        elif method == "AES-128":
            uri_match = re.search(r'URI=["\']([^"\']+)["\']', key_line, re.IGNORECASE)
            iv_match = re.search(r'IV=0x([0-9a-fA-F]+)', key_line, re.IGNORECASE)
            explicit_iv = None
            if iv_match:
                try:
                    explicit_iv = int(iv_match.group(1), 16).to_bytes(16, "big")
                except (OverflowError, ValueError):
                    logger.warning("Invalid AES-128 IV ignored in HLS playlist")

            aes_key = None
            if uri_match:
                key_url = urljoin(m3u8_url, uri_match.group(1))
                key_response = None
                try:
                    key_response = requests.get(key_url, headers=headers, timeout=10)
                    if key_response.status_code == 200 and len(key_response.content) == 16:
                        aes_key = bytes(key_response.content)
                except Exception:
                    logger.debug("AES-128 key request failed: %s", key_url, exc_info=True)
                finally:
                    _close_response(key_response)

                if aes_key is None and c_requests:
                    key_response = None
                    try:
                        key_response = c_requests.get(
                            key_url,
                            headers=headers,
                            impersonate="chrome124",
                            timeout=10,
                        )
                        if key_response.status_code == 200 and len(key_response.content) == 16:
                            aes_key = bytes(key_response.content)
                    except Exception:
                        logger.debug("AES-128 curl key request failed: %s", key_url, exc_info=True)
                    finally:
                        _close_response(key_response)

            if aes_key is not None:
                custom_headers["aes_key"] = aes_key
                custom_headers["aes_media_sequence"] = media_sequence
                if explicit_iv is None:
                    custom_headers.pop("aes_iv", None)
                else:
                    custom_headers["aes_iv"] = explicit_iv

    # Media Playlist Segmentleri (#EXTINF veya doğrudan .ts/.mp4 parçaları)
    segments = []
    durations = []
    # Init segment kontrolü (fMP4 / EXT-X-MAP)
    for l in lines:
        if l.startswith("#EXT-X-MAP:"):
            map_m = re.search(r'URI=["\']([^"\']+)["\']', l)
            if map_m:
                segments.append(urljoin(m3u8_url, map_m.group(1)))
                durations.append(None)

    pending_duration = None
    for l in lines:
        if l.startswith("#EXTINF:"):
            duration_text = l.partition(":")[2].partition(",")[0].strip()
            try:
                parsed_duration = float(duration_text)
                pending_duration = parsed_duration if parsed_duration > 0 else None
            except ValueError:
                logger.debug("Invalid EXTINF duration ignored: %r", duration_text)
                pending_duration = None
            continue
        if l.startswith("#"):
            continue
        seg_url = urljoin(m3u8_url, l)
        segments.append(seg_url)
        durations.append(pending_duration)
        pending_duration = None

    # Token süresi kontrolü (Fix 5)
    if segments:
        first_seg = segments[0]
        validto_m = re.search(r'validto=(\d+)', first_seg)
        if validto_m:
            try:
                valid_ts = int(validto_m.group(1))
                if valid_ts < time.time():
                    logger.warning(f"[M3U8] Segment token süresi dolmuş! (validto: {valid_ts} < now: {int(time.time())})")
            except Exception:
                logger.debug("[engine.py:336] extract_m3u8_info() sessiz istisna yutuldu", exc_info=True)

    if return_timeline:
        return segments, durations
    return segments




def detect_segment_range(prefix, padding, ext, query_fragment, headers, sample_index=1, cancel_event=None, log_callback=None, status_callback=None, session=None):
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                logger.debug("[engine.py:455] log() sessiz istisna yutuldu", exc_info=True)

    def set_status(msg):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                logger.debug("[engine.py:462] set_status() sessiz istisna yutuldu", exc_info=True)

    # Cagiran bir oturum verdiyse onu kullan; yoksa kisa omurlu yoklama oturumu ac.
    owns_session = session is None
    if owns_session:
        probe_session = requests.Session()
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=Retry(total=0))
        probe_session.mount('https://', adapter)
        probe_session.mount('http://', adapter)
    else:
        probe_session = session

    set_status("Segment Kontrol Ediliyor...")
    sample_url = build_segment_url(prefix, sample_index, padding, ext, query_fragment)
    is_ok, status, hint = probe_url(sample_url, headers, session=probe_session)
    if not is_ok:
        log(f"[!] UYARI: Örnek segment URL'sine erişilemedi ({hint})!")
        if status == 403:
            raise DownloadError(f"Sunucu erişimi engelledi ({hint}). Lütfen geçerli cURL / Cookie başlıklarını kullanın.")
        elif status not in (404, 503):
            raise DownloadError(f"Segment URL'sine erişilemedi ({hint}).")

    start_index = 1
    url_0 = build_segment_url(prefix, 0, padding, ext, query_fragment)
    ok_0, _, _ = probe_url(url_0, headers, session=probe_session)
    if ok_0:
        start_index = 0
        log("Segment başlangıç indeksi: 0 olarak doğrulandı.")
    else:
        log("Segment başlangıç indeksi: 1 olarak doğrulandı.")

    test_index = max(start_index, sample_index)
    step = 50
    last_valid_index = test_index

    log(f"Segment taraması başlatılıyor (adım: {step})...")

    while True:
        if cancel_event and cancel_event.is_set():
            log("Segment tespiti iptal edildi.")
            _close_owned(probe_session, owns_session)
            return start_index, 0

        set_status(f"Segment {test_index} Taranıyor...")
        test_url = build_segment_url(prefix, test_index, padding, ext, query_fragment)
        is_valid, _, _ = probe_url(test_url, headers, session=probe_session)
        if is_valid:
            log(f"  [+] Segment {test_index} bulundu.")
            last_valid_index = test_index
            test_index += step
            if step < 200:
                step = int(step * 1.5)
        else:
            log(f"  [!] Segment {test_index} bulunamadı, son sınır aranıyor...")
            break

    low = last_valid_index
    high = test_index
    total_segments = last_valid_index

    while low <= high:
        if cancel_event and cancel_event.is_set():
            log("Segment tespiti iptal edildi.")
            _close_owned(probe_session, owns_session)
            return start_index, 0

        mid = (low + high) // 2
        set_status(f"Segment {mid} Doğrulanıyor...")
        test_url = build_segment_url(prefix, mid, padding, ext, query_fragment)
        is_valid, _, _ = probe_url(test_url, headers, session=probe_session)

        if is_valid:
            total_segments = mid
            low = mid + 1
        else:
            high = mid - 1

    log(f"[[+]] Tespit tamamlandı: Segment aralığı [{start_index} - {total_segments}] (Toplam: {total_segments - start_index + 1} parça)")
    set_status(f"Toplam {total_segments - start_index + 1} Segment Bulundu")
    _close_owned(probe_session, owns_session)
    return start_index, total_segments





class VideoDownloadEngine(SegmentDownloaderMixin, FFmpegMixin):
    """
    Yüksek hızlı paralel HLS/Segment, Video+Ses Birleştirici, YouTube İndirici ve Ses Dönüştürücü Motoru.
    """

    def __init__(self):
        self.cancel_event = threading.Event()
        self.turbo_boost_event = threading.Event()
        self.turbo_extra_workers = 0
        self.is_running = False
        self.cleanup_on_cancel = True
        self.active_temp_dir = None
        self.shared_fallback_hosts = ()

        # Facade/test uyumluluğu için ana oturum korunur; segment worker'ları ise
        # birbirleriyle Session paylaşmaz ve aşağıdaki thread-local havuzu kullanır.
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=16,
            pool_maxsize=16,
            max_retries=Retry(total=0)
        )
        self._session.mount('https://', adapter)
        self._session.mount('http://', adapter)
        self._tls = threading.local()

    def enable_turbo_boost(self, extra_workers=0):
        """Video tamamlandığında veya boşa çıkan worker'lar olduğunda ses akışlarını hızlandırmak için Turbo Boost'u açar."""
        self.turbo_extra_workers = max(getattr(self, "turbo_extra_workers", 0), extra_workers)
        if hasattr(self, "turbo_boost_event"):
            self.turbo_boost_event.set()

    def disable_turbo_boost(self):
        """Turbo Boost bayrağını sıfırlar."""
        self.turbo_extra_workers = 0
        if hasattr(self, "turbo_boost_event"):
            self.turbo_boost_event.clear()

    def _get_session(self):
        """Return a worker-local keep-alive session and rotate stale connections."""
        if (
            hasattr(self, "_session")
            and hasattr(self._session, "get")
            and "Mock" in type(self._session.get).__name__
        ):
            return self._session

        if not hasattr(self._tls, "session"):
            session = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=16,
                pool_maxsize=16,
                pool_block=False,
                max_retries=Retry(total=0),
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._tls.session = session
        return self._tls.session

    def cancel(self, cleanup=True):
        """İndirme işlemini iptal eder. cleanup=True ise geçici dosyaları temizler."""
        self.cleanup_on_cancel = cleanup
        self.cancel_event.set()
        if cleanup and self.active_temp_dir:
            cleanup_filesystem_path(self.active_temp_dir)

    def pause(self):
        """İndirme işlemini duraklatır (geçici dosyaları korur)."""
        self.cancel(cleanup=False)

    def resume(self):
        """İndirmeyi devam ettirmek için iptal/duraklatma bayraklarını sıfırlar."""
        self.reset_cancel()

    def reset_cancel(self):
        self.cancel_event.clear()
        self.disable_turbo_boost()
        self.cleanup_on_cancel = True
        self.active_temp_dir = None
        self.shared_fallback_hosts = ()



    def run_dual_stream_download(self, video_url, audio_url, output_filepath,
                                 video_headers=None, audio_headers=None,
                                 total_segments=None, start_index=0,
                                 thread_count=16, progress_callback=None,
                                 log_callback=None, status_callback=None,
                                 video_segments=None, audio_segments=None,
                                 subtitles=None, subtitle_url=None, subtitle_headers=None,
                                 keep_external_srt=True, video_durations=None,
                                 audio_durations=None, recovery_url=None):
        """
        Video + tek ses kanalini indirip tek bir MP4 dosyasinda birlestirir.

        C6: Bu metot artik `run_multi_audio_download` uzerine ince bir adaptordur.
        Onceden iki metot ~250'ser satirla neredeyse ayni isi yapiyordu; segment
        gorevi kurma, onbellek tarama, EMA hiz hesabi ve birlestirme kodu iki yerde
        birden yasadigi icin A1/A2 gibi hatalar da iki kez tekrarlaniyordu.
        """
        self.reset_cancel()
        def log(msg):
            if log_callback:
                log_callback(msg)

        # Kardes metotlarla ayni yasam dongusu: onceki indirmeden kalan iptal
        # bayragi temizlenmezse bu cagri aninda "iptal edildi" ile doner (A6).
        self.reset_cancel()

        has_audio = bool(audio_segments) or bool(audio_url)
        if not has_audio:
            # Ses kanali yok: cift akis motoru yerine tekil akis indiricisi dogru yol.
            # Eskiden bos bir raw_audio.ts uretilip FFmpeg'e verilir, mux basarisiz
            # olur ve ikili yedek yol .mp4 adli bir MPEG-TS birakirdi.
            log("[i] Ayri ses akisi yok; tekil akis indiricisine yonlendiriliyor.")
            return self.run_download(
                sample_url=video_url,
                output_filepath=output_filepath,
                total_segments=total_segments,
                start_index=start_index,
                thread_count=thread_count,
                custom_headers=video_headers,
                progress_callback=(lambda c, t, b, s=0.0: progress_callback(c, t, b, s))
                if progress_callback else None,
                log_callback=log_callback,
                status_callback=status_callback,
                segment_urls=video_segments,
                subtitles=subtitles,
                subtitle_url=subtitle_url,
                subtitle_headers=subtitle_headers,
                keep_external_srt=keep_external_srt,
                recovery_url=recovery_url,
            )

        audio_track = {
            "name": "Ses",
            "lang": "tur",
            "segments": audio_segments,
            "durations": audio_durations,
            "sample_segment_url": audio_url,
            "url": audio_url,
            "headers": audio_headers or video_headers,
        }

        return self.run_multi_audio_download(
            video_url=video_url,
            audio_tracks=[audio_track],
            output_filepath=output_filepath,
            video_headers=video_headers,
            subtitle_url=subtitle_url,
            subtitle_headers=subtitle_headers,
            total_segments=total_segments,
            start_index=start_index,
            thread_count=thread_count,
            progress_callback=progress_callback,
            log_callback=log_callback,
            status_callback=status_callback,
            video_segments=video_segments,
            subtitles=subtitles,
            keep_external_srt=keep_external_srt,
            _from_dual_stream=True,
            video_durations=video_durations,
            recovery_url=recovery_url,
        )

    def run_multi_audio_download(self, video_url, audio_tracks, output_filepath,
                                 video_headers=None, subtitle_url=None, subtitle_headers=None,
                                 total_segments=None, start_index=0,
                                 thread_count=16, progress_callback=None,
                                 log_callback=None, status_callback=None,
                                 video_segments=None, subtitles=None,
                                 keep_external_srt=True, _from_dual_stream=False,
                                 video_durations=None, recovery_url=None):
        """
        Video + birden fazla ses kanalını (Türkçe Dublaj + Orijinal İngilizce) ve opsiyonel altyazıyı indirip
        FFmpeg ile çok kanallı (Multi-Audio) tek bir MP4 dosyasına birleştirir.
        """
        if video_headers is None:
            video_headers = {}

        def log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    logger.debug("run_multi_audio_download log callback failed", exc_info=True)

        def set_status(text):
            if status_callback:
                status_callback(text)

        self.reset_cancel()
        self.is_running = True

        try:
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(output_filepath))[0])
            base_temp = os.path.join(tempfile.gettempdir(), ".vdp_temp")
            temp_dir = os.path.join(base_temp, f".temp_{safe_name}")
            os.makedirs(temp_dir, exist_ok=True)
            self.active_temp_dir = temp_dir

            # Önceki indirmeden kalan birleştirme kalıntılarını temizle (segmentleri koru)
            for f_old in os.listdir(temp_dir):
                if f_old.startswith("raw_") or f_old.startswith("concat_"):
                    try:
                        os.remove(os.path.join(temp_dir, f_old))
                    except OSError:
                        logger.debug("[engine.py:1381] run_multi_audio_download() sessiz istisna yutuldu", exc_info=True)

            # Video görevleri
            video_tasks = []
            v_paths = []
            if video_segments:
                for idx, v_u in enumerate(video_segments):
                    v_p = os.path.join(temp_dir, f"v_seg_{idx:07d}.tmp")
                    video_tasks.append((idx, v_u, v_p))
                    v_paths.append(v_p)
                total_count = len(video_segments)
            else:
                v_prefix = None
                video_path = urlparse(video_url).path
                is_video_manifest = video_path.lower().endswith(".m3u8")
                should_probe_manifest = is_video_manifest or not os.path.splitext(video_path)[1]
                m3_segs = None
                if should_probe_manifest:
                    log("[i] Video akışı M3U8 manifesti olarak çözümleniyor...")
                    m3_segs, video_durations = extract_m3u8_info(
                        video_url,
                        video_headers,
                        return_timeline=True,
                    )

                if m3_segs:
                    video_segments = m3_segs
                    for idx, v_u in enumerate(video_segments):
                        v_p = os.path.join(temp_dir, f"v_seg_{idx:07d}.tmp")
                        video_tasks.append((idx, v_u, v_p))
                        v_paths.append(v_p)
                    total_count = len(video_segments)
                else:
                    try:
                        v_prefix, v_pad, v_ext, v_query, _ = parse_segment_url(video_url)
                    except ValueError:
                        v_prefix = None

                    if v_prefix is None:
                        raise ValueError(f"Geçersiz video akış URL'si: {video_url[:80]}")

                    if total_segments is None or total_segments <= 0:
                        try:
                            _, detected_end = _get_engine_symbol('detect_segment_range', detect_segment_range)(
                                v_prefix, v_pad, v_ext, v_query, video_headers,
                                sample_index=start_index, cancel_event=self.cancel_event,
                                log_callback=log, session=self._session
                            )
                            total_segments = detected_end if detected_end > 0 else start_index
                        except Exception as det_err:
                            log(f"[!] Segment araligi tespit edilemedi ({det_err}); tek segment varsayiliyor.")
                            logger.warning("detect_segment_range basarisiz", exc_info=True)
                            total_segments = start_index
                    total_count = total_segments - start_index + 1
                    for i in range(start_index, total_segments + 1):
                        v_u = build_segment_url(v_prefix, i, v_pad, v_ext, v_query)
                        v_p = os.path.join(temp_dir, f"v_seg_{i:07d}.tmp")
                        video_tasks.append((i, v_u, v_p))
                        v_paths.append(v_p)
            if video_durations is not None and len(video_durations) != len(video_tasks):
                logger.warning(
                    "Video timeline ignored because segment/duration counts differ: segments=%d durations=%d",
                    len(video_tasks),
                    len(video_durations),
                )
                video_durations = None
            # Korumalı Akıllı Tekilleştirme: Eğer tek bir ses kanalı verilmişse ve bu ses kanalı
            # video akışıyla birebir aynıysa (MPEG-TS tekil akış), 2 kez 300 MB indirmek yerine
            # doğrudan tekil akış olarak indirip işlemi tamamla!
            first_track = audio_tracks[0] if audio_tracks else {}
            # `video_segments` / `video_url` describe the picture stream paired
            # with this audio choice.  They do not mean the selected audio is
            # embedded in that stream.  Only the audio track's own transport
            # fields may be used to decide whether the muxed-stream fast path
            # is safe; otherwise selecting an external original-language track
            # silently falls back to the video's default (often dubbed) audio.
            first_track_segments = first_track.get("segments")
            first_track_url = (
                first_track.get("url")
                or first_track.get("sample_segment_url")
                or ""
            )
            first_track_is_video = bool(
                (first_track_segments and video_segments and first_track_segments == video_segments)
                or (first_track_url and first_track_url == video_url)
                or (first_track_segments and first_track_segments[0] == video_url)
            )

            if first_track_is_video:
                candidate_durations = first_track.get("video_durations") or first_track.get("durations")
                if candidate_durations and len(candidate_durations) == len(video_tasks):
                    video_durations = list(candidate_durations)

            if video_durations is None and video_segments:
                video_path = urlparse(video_url).path
                should_probe_video_timeline = (
                    ".m3u8" in video_url.lower()
                    or not os.path.splitext(video_path)[1]
                )
                if should_probe_video_timeline:
                    try:
                        timeline_segments, timeline_durations = extract_m3u8_info(
                            video_url,
                            video_headers,
                            return_timeline=True,
                        )
                        if len(timeline_segments) == len(video_tasks):
                            video_durations = timeline_durations
                    except Exception:
                        logger.debug("Video HLS timeline probe failed", exc_info=True)

            if len(audio_tracks) == 1 and first_track_is_video:
                log("[i] Akışın tekil video+ses akışı (Muxed MPEG-TS) olduğu doğrulandı. Çift indirme önlendi, tek akış hızlandırması uygulanıyor...")
                return self.run_download(
                    sample_url=first_track_url or video_url,
                    output_filepath=output_filepath,
                    thread_count=thread_count,
                    custom_headers=first_track.get("video_headers") or first_track.get("headers") or video_headers,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    segment_urls=first_track_segments or video_segments,
                    total_segments=len(video_segments),
                    subtitles=subtitles,
                    keep_external_srt=keep_external_srt,
                    recovery_url=recovery_url,
                )

            # Çift Dil Akıllı Muxed TS Optimizasyonu (Boyut Katlanmasını Önleme)
            is_track0_in_video = False
            track0_info = None
            if len(audio_tracks) > 1 and first_track_is_video:
                is_track0_in_video = True
                track0_info = (audio_tracks[0].get("name", "Türkçe Dublaj").split("(")[0].strip(), audio_tracks[0].get("lang", "tur"))
                log(f"[i] İlk ses kanalının ({track0_info[0]}) video akışına gömülü olduğu (Muxed MPEG-TS) tespit edildi. Çift indirme önlendi, sadece ek ses kanalı indirilecek.")

            tracks_to_download = audio_tracks[1:] if is_track0_in_video else audio_tracks
            log(f"Çoklu Ses İndirme: 1 Video + {len(tracks_to_download)} İndirilecek Ses kanalı ({total_count} parça)")

            # Ses kanalları görevleri
            audio_track_tasks = []
            for idx, a_track in enumerate(tracks_to_download):
                a_tasks = []
                a_paths = []
                a_headers = dict(a_track.get("headers") or video_headers or {})
                a_segs = a_track.get("segments")
                a_durations = a_track.get("durations")
                if a_durations is not None and (not a_segs or len(a_durations) != len(a_segs)):
                    logger.warning(
                        "Audio timeline ignored because segment/duration counts differ: track=%s segments=%d durations=%d",
                        a_track.get("name", idx + 1),
                        len(a_segs or []),
                        len(a_durations),
                    )
                    a_durations = None
                if a_segs:
                    for s_idx, a_u in enumerate(a_segs):
                        a_p = os.path.join(temp_dir, f"a{idx}_seg_{s_idx:07d}.tmp")
                        a_tasks.append((s_idx, a_u, a_p))
                        a_paths.append(a_p)
                else:
                    a_url = a_track.get("sample_segment_url", "") or a_track.get("url", "")
                    audio_path = urlparse(a_url).path
                    should_probe_audio_manifest = (
                        ".m3u8" in a_url.lower()
                        or not os.path.splitext(audio_path)[1]
                    )
                    if should_probe_audio_manifest:
                        try:
                            m3_aud, resolved_audio_durations = extract_m3u8_info(
                                a_url,
                                a_headers,
                                return_timeline=True,
                            )
                            if m3_aud:
                                a_durations = resolved_audio_durations
                                for s_idx, a_u in enumerate(m3_aud):
                                    a_p = os.path.join(temp_dir, f"a{idx}_seg_{s_idx:07d}.tmp")
                                    a_tasks.append((s_idx, a_u, a_p))
                                    a_paths.append(a_p)
                        except Exception:
                            logger.debug("[engine.py:1436] audio m3u8 resolve failed", exc_info=True)
                    if not a_tasks and a_url:
                        try:
                            a_prefix, a_pad, a_ext, a_query, _ = _get_engine_symbol('parse_segment_url', parse_segment_url)(a_url)
                            for i in range(start_index, total_segments + 1):
                                a_u = build_segment_url(a_prefix, i, a_pad, a_ext, a_query)
                                a_p = os.path.join(temp_dir, f"a{idx}_seg_{i:07d}.tmp")
                                a_tasks.append((i, a_u, a_p))
                                a_paths.append(a_p)
                        except Exception as pe:
                            log(f"[!] '{a_track.get('name')}' ses segmentleri oluşturulamadı: {pe}")

                audio_track_tasks.append({
                    "name": a_track.get("name", f"Ses {idx+1}").split("(")[0].strip(),
                    "lang": a_track.get("lang", "eng" if (is_track0_in_video or idx > 0) else "tur"),
                    "tasks": a_tasks,
                    "paths": a_paths,
                    "durations": a_durations,
                    "headers": a_headers
                })

            for audio_task in audio_track_tasks:
                if not _hls_timelines_aligned(video_durations, audio_task["durations"]):
                    video_seconds = sum(value or 0 for value in video_durations)
                    audio_seconds = sum(value or 0 for value in audio_task["durations"])
                    message = (
                        f"'{audio_task['name']}' ses zaman çizelgesi video ile uyuşmuyor "
                        f"(video={video_seconds:.3f} sn, ses={audio_seconds:.3f} sn)."
                    )
                    logger.error(message)
                    log(f"[HATA] {message}")
                    return False, message


            # Opsiyonel Altyazı indir ve SRT dönüştür (Türkçe karakter korumalı hibrit kayıt)
            sub_candidates = list(subtitles) if subtitles else []
            if subtitle_url:
                sub_candidates.insert(0, {"url": subtitle_url, "headers": subtitle_headers})

            sub_file_path = _get_engine_symbol('fetch_and_save_subtitle', fetch_and_save_subtitle)(
                subtitles=sub_candidates,
                output_filepath=output_filepath,
                session=self._session,
                default_headers=video_headers,
                log_callback=log
            )

            # Önbellek Taraması (Resume Detection) - Hızlı Bellek Kümesi
            try:
                existing_dir_files = set(os.listdir(temp_dir)) if temp_dir and os.path.exists(temp_dir) else set()
            except Exception:
                existing_dir_files = None

            def _seg_exists_fast(p):
                if existing_dir_files is not None and os.path.basename(p) not in existing_dir_files:
                    return False
                return is_valid_segment_file(p)

            v_cached = sum(1 for p in v_paths if _seg_exists_fast(p))
            a_cached_counts = [sum(1 for p in at["paths"] if _seg_exists_fast(p)) for at in audio_track_tasks]
            completed_counts = [v_cached] + a_cached_counts
            cached_ratios = [v_cached / max(1, len(video_tasks))] + [
                cached_count / max(1, len(at["tasks"]))
                for cached_count, at in zip(a_cached_counts, audio_track_tasks)
            ]
            tot_cached = int((sum(cached_ratios) / len(cached_ratios)) * total_count)

            v_init_bytes = sum(os.path.getsize(p) for p in v_paths if _seg_exists_fast(p))
            a_init_bytes_list = [sum(os.path.getsize(p) for p in at["paths"] if _seg_exists_fast(p)) for at in audio_track_tasks]
            bytes_counts = [v_init_bytes] + a_init_bytes_list
            initial_bytes = sum(bytes_counts)

            if tot_cached > 0:
                set_status(f"Kaldığı Yerden Devam Ediliyor ({tot_cached} / {total_count})...")
                log(f"[i] 🔄 Önbellek algılandı: {tot_cached} / {total_count} parça diskte mevcut. Kalan parçalar indiriliyor...")
            else:
                set_status("Video ve Ses İndiriliyor..." if len(audio_track_tasks) <= 1
                           else "Video ve Çoklu Ses Kanalları İndiriliyor...")
                log("[+] Yüksek hızlı indirme başlatıldı...")

            if progress_callback:
                progress_callback(tot_cached, total_count, initial_bytes, 0.0)
            # Crash Recovery durum kaydı (.vdp_state.json)
            write_recovery_state(temp_dir, {
                "url": video_url,
                "title": os.path.splitext(os.path.basename(output_filepath))[0],
                "output_filepath": output_filepath,
                "total_segments": total_count,
                "downloaded_segments": tot_cached,
                "timestamp": time.time(),
                "custom_headers": _transport_headers(video_headers),
                "is_multi_audio": True,
                "audio_tracks": [{"name": a.get("name"), "lang": a.get("lang")} for a in audio_tracks] if audio_tracks else [],
                "subtitles": subtitles or [],
                "raw_url": recovery_url or video_url,
            })

            start_time = time.time()
            lock = threading.Lock()
            last_calc_time = [time.time()]
            last_calc_bytes = [initial_bytes]
            last_state_write = [time.time()]
            current_ema_spd = [0.0]

            last_cb_time = [0.0]

            def on_stream_progress(stream_idx, comp, tot, b_down):
                with lock:
                    completed_counts[stream_idx] = comp
                    bytes_counts[stream_idx] = b_down
                    ratio_v = completed_counts[0] / max(1, len(video_tasks))
                    ratio_a_list = [completed_counts[idx + 1] / max(1, len(at["tasks"])) for idx, at in enumerate(audio_track_tasks)]
                    combined_ratio = (ratio_v + sum(ratio_a_list)) / (1.0 + len(audio_track_tasks))
                    tot_completed = int(combined_ratio * total_count)
                    tot_bytes = sum(bytes_counts)

                    now = time.time()
                    dt = now - last_calc_time[0]
                    if dt >= 0.4:
                        new_delta = max(0, tot_bytes - last_calc_bytes[0])
                        instant_spd = new_delta / dt
                        if current_ema_spd[0] == 0.0:
                            current_ema_spd[0] = instant_spd
                        else:
                            current_ema_spd[0] = 0.65 * instant_spd + 0.35 * current_ema_spd[0]
                        last_calc_time[0] = now
                        last_calc_bytes[0] = tot_bytes
                    spd = current_ema_spd[0]

                    if (now - last_state_write[0]) >= 2.0:
                        update_recovery_progress(temp_dir, tot_completed)
                        last_state_write[0] = now

                if progress_callback:
                    if (now - last_cb_time[0]) >= 0.15 or tot_completed >= total_count:
                        last_cb_time[0] = now
                        progress_callback(tot_completed, total_count, tot_bytes, spd)

            # Ayrik video/ses playlistleri ayni sharded CDN ailesindeyse tum
            # stream'lere ortak failover havuzu ver. Host ikamesi yalnizca ilk
            # etiket ve TLD ayni oldugunda yapilir; ilgisiz origin'ler karismaz.
            # Manifest URL authorities can be part of a CDN signature. Cross-stream
            # host substitution is therefore unsafe; retries keep each original URL.
            self.shared_fallback_hosts = ()

            def run_stream_dl(stream_idx, tasks, headers, w_count, base_comp=0, full_total=None):
                def cb(comp, tot, b):
                    on_stream_progress(stream_idx, base_comp + comp, full_total if full_total is not None else tot, b)
                return self.download_stream_segments(
                    tasks,
                    headers,
                    thread_count=w_count,
                    progress_callback=cb,
                    log_callback=log,
                )

            # Eşzamanlı (Concurrent Stream) İndirme: Video ve ses akışları paralel çalıştırılarak
            # sıralı şelale (waterfall) darboğazı kırılır ve hat bant genişliği %100 kullanılır.
            num_audio = len(audio_track_tasks)
            if num_audio > 0 and video_tasks:
                worker_budget = min(64, max(1 + num_audio, int(thread_count)))
                all_stream_tasks = list(video_tasks)
                for audio_task in audio_track_tasks:
                    all_stream_tasks.extend(audio_task["tasks"])
                is_cdnimages_family = bool(all_stream_tasks) and all(
                    "cdnimages" in task[1].lower()
                    for task in all_stream_tasks
                )
                if is_cdnimages_family:
                    worker_budget = min(worker_budget, 16)
                    log(
                        "[i] CDNImages çoklu akış koruması: toplam eşzamanlı bağlantı "
                        f"{worker_budget} ile sınırlandı."
                    )
                is_dystream_family = bool(all_stream_tasks) and any(
                    "dystream" in task[1].lower()
                    for task in all_stream_tasks
                )
                if is_dystream_family:
                    worker_budget = min(worker_budget, 6)
                    log(
                        "[i] 🛡️ Dystream çoklu akış koruması: toplam eşzamanlı bağlantı "
                        f"{worker_budget} ile sınırlandı."
                    )
                is_rapidrame_family = bool(all_stream_tasks) and any(
                    "rapidrame.com" in task[1].lower()
                    for task in all_stream_tasks
                )
                if is_rapidrame_family:
                    worker_budget = min(worker_budget, 8)
                    log(
                        "[i] Rapidrame çoklu akış koruması: toplam eşzamanlı bağlantı "
                        f"{worker_budget} ile sınırlandı."
                    )
                w_audio = max(1, worker_budget // (num_audio + 2))
                w_video = max(1, worker_budget - (w_audio * num_audio))
                set_status("Video ve Ses Eşzamanlı İndiriliyor..." if num_audio == 1
                           else "Video ve Çoklu Ses Kanalları Eşzamanlı İndiriliyor...")
                log(f"[+] 🚀 Eşzamanlı Akış Motoru: Video ({w_video} iş parçacığı) ve {num_audio} ses kanalı ({w_audio} iş parçacığı/kanal) paralel indiriliyor.")

                with ThreadPoolExecutor(max_workers=1 + num_audio) as stream_pool:
                    v_future = stream_pool.submit(run_stream_dl, 0, video_tasks, video_headers, w_video, 0, len(video_tasks))
                    a_futures = [
                        stream_pool.submit(run_stream_dl, idx + 1, at["tasks"], at["headers"], w_audio, 0, len(at["tasks"]))
                        for idx, at in enumerate(audio_track_tasks)
                    ]
                    all_futures = [v_future] + a_futures
                    video_boost_triggered = False

                    while any(not f.done() for f in all_futures):
                        if self.cancel_event.is_set():
                            break

                        # Video akışı bittiğinde ve henüz tamamlanmamış ses akışları varsa:
                        # Boşa çıkan tüm video worker'larını (w_video) anında ses akışlarına devret (Dinamik Worker Devri)!
                        if v_future.done() and not video_boost_triggered and not is_rapidrame_family:
                            pending_audio = [f for f in a_futures if not f.done()]
                            if pending_audio:
                                video_boost_triggered = True
                                log(f"[+] 🚀 Video akışı tamamlandı! Boşa çıkan {w_video} iş parçacığı ses akışlarına devredildi (Dinamik Worker Devri / Turbo Boost).")
                                released_per_audio = max(1, w_video // len(pending_audio))
                                self.enable_turbo_boost(extra_workers=released_per_audio)

                        time.sleep(0.05)

                    for f in all_futures:
                        try:
                            f.result()
                        except Exception as e_stream:
                            logger.warning(f"Eşzamanlı akış indirme uyarısı: {e_stream}", exc_info=True)
            elif video_tasks:
                set_status("Video Akışı İndiriliyor...")
                run_stream_dl(0, video_tasks, video_headers, w_count=thread_count, base_comp=0, full_total=len(video_tasks))
            elif num_audio > 0:
                w_audio = max(2, thread_count // num_audio)
                set_status("Ses Kanalları İndiriliyor...")
                with ThreadPoolExecutor(max_workers=num_audio) as stream_pool:
                    stream_futures = [
                        stream_pool.submit(run_stream_dl, idx + 1, at["tasks"], at["headers"], w_audio, 0, len(at["tasks"]))
                        for idx, at in enumerate(audio_track_tasks)
                    ]
                    for f in as_completed(stream_futures):
                        try:
                            f.result()
                        except Exception as e_stream:
                            logger.warning(f"Ses akışı indirme uyarısı: {e_stream}", exc_info=True)

            if self.cancel_event.is_set():
                if self.cleanup_on_cancel and temp_dir:
                    cleanup_filesystem_path(temp_dir)
                set_status("İptal Edildi" if self.cleanup_on_cancel else "DURAKLATILDI")
                log("İndirme iptal edildi ve geçici dosyalar temizlendi." if self.cleanup_on_cancel else "İndirme duraklatıldı. İnen parçalar korundu.")
                return False, "İşlem iptal edildi." if self.cleanup_on_cancel else "İndirme duraklatıldı."

            # Eksiksiz İndirme Doğrulaması (Strict Completeness Validation)
            v_missing = [p for p in v_paths if not is_valid_segment_file(p)]
            if v_missing:
                tot_missing = len(v_missing)
                log(f"[!] UYARI: Video akışı eksik kaldı ({tot_missing} adet parça sunucu zaman aşımı nedeniyle indirilemedi).")
                log("[i] İnen parçalar önbellekte korundu. '▶ İndirmeyi Başlat' butonuna tekrar basarak eksik parçaları kaldığı yerden indirebilirsiniz.")
                set_status(f"Eksik ({len(v_paths)-tot_missing}/{len(v_paths)} indi)")
                return False, f"Video indirmesi eksik kaldı ({tot_missing} parça eksik). Tekrar başlatıp tamamlayın."

            for at in audio_track_tasks:
                a_missing = [p for p in at["paths"] if not is_valid_segment_file(p)]
                if a_missing:
                    tot_a_miss = len(a_missing)
                    log(f"[!] UYARI: '{at['name']}' ses akışı eksik kaldı ({tot_a_miss} adet parça indirilemedi).")
                    set_status(f"Eksik ({len(at['paths'])-tot_a_miss}/{len(at['paths'])} indi)")
                    return False, f"'{at['name']}' ses akışı eksik kaldı ({tot_a_miss} parça eksik). Tekrar başlatıp tamamlayın."

            set_status("Video ve Ses Birleştiriliyor..." if len(audio_track_tasks) <= 1
                       else "Çok Kanallı Akışlar Birleştiriliyor...")

            # Segment payloadlarını ikinci kez raw_*.ts dosyalarına kopyalamadan FFmpeg
            # Concat Demuxer listeleri üret. Bu hem disk baskısını hem de büyük dosya kopya
            # aşamasındaki gecikmeyi kaldırır.
            v_concat = os.path.join(temp_dir, "concat_video.txt")
            a_concats = []
            for idx, at in enumerate(audio_track_tasks):
                a_concat = os.path.join(temp_dir, f"concat_audio_{idx}.txt")
                a_concats.append((a_concat, at["name"], at["lang"]))

            valid_video_paths = [path for path in v_paths if is_valid_segment_file(path)]
            if not valid_video_paths:
                logger.error(
                    "Mux öncesi geçerli video segmenti yok: planlanan=%d, diskte=%d",
                    len(v_paths),
                    sum(1 for p in v_paths if os.path.exists(p)),
                )
                return False, "Video akışı birleştirme öncesinde geçerli segment içermiyor."
            write_concat_file(v_concat, valid_video_paths, video_durations)
            for idx, at in enumerate(audio_track_tasks):
                valid_audio_paths = [path for path in at["paths"] if is_valid_segment_file(path)]
                if not valid_audio_paths:
                    return False, f"'{at['name']}' ses akışı birleştirme öncesinde geçerli segment içermiyor."
                write_concat_file(a_concats[idx][0], valid_audio_paths, at["durations"])

            # FFmpeg ile birleştir
            if _from_dual_stream and len(a_concats) == 1:
                success = self.mux_video_and_audio(
                    video_concat_path=v_concat,
                    audio_concat_path=a_concats[0][0],
                    output_filepath=output_filepath,
                    subtitle_path=sub_file_path,
                    log_callback=log
                )
            else:
                success = self.mux_multi_audio_and_video(
                    v_concat_path=v_concat,
                    audio_concats=a_concats,
                    output_filepath=output_filepath,
                    subtitle_path=sub_file_path,
                    log_callback=log,
                    has_muxed_track0=is_track0_in_video,
                    track0_info=track0_info
                )

            if success:
                cleanup_filesystem_path(temp_dir)
                if not keep_external_srt and sub_file_path and os.path.exists(sub_file_path):
                    try:
                        os.remove(sub_file_path)
                        log(f"[i] Harici altyazı dosyası temizlendi (Altyazı MP4 içine gömüldü): {os.path.basename(sub_file_path)}")
                    except Exception as e_rm:
                        logger.debug("Harici altyazı silinemedi: %s", e_rm, exc_info=True)
                    try:
                        tr_sub = os.path.splitext(sub_file_path)[0] + ".tr.srt"
                        if os.path.exists(tr_sub):
                            os.remove(tr_sub)
                    except Exception:
                        logger.debug("Embedded subtitle sidecar cleanup failed", exc_info=True)
                final_mb = (os.path.getsize(output_filepath) / (1024 * 1024)) if os.path.exists(output_filepath) else 0.0
                set_status("Tamamlandı")
                label = "Film" if (len(a_concats) <= 1 and not is_track0_in_video) else "Çift Sesli Film"
                log(f"[+] {label} başarıyla oluşturuldu: {final_mb:.2f} MB")
                if progress_callback:
                    progress_callback(total_count, total_count, int(final_mb * 1024 * 1024), 0.0)
                return True, output_filepath
            else:
                return False, "FFmpeg ile ses ve görüntü birleştirilemedi."

        except Exception as e:
            set_status(f"Hata: {str(e)[:40]}")
            log(f"[HATA] {e}")
            return False, str(e)
        finally:
            self.is_running = False



    def run_download(self, sample_url, output_filepath, referer=None, total_segments=None,
                     start_index=None, thread_count=16, merge_mode="auto", custom_headers=None,
                     progress_callback=None, log_callback=None, status_callback=None,
                     keep_temp=False, segment_urls=None, subtitles=None, subtitle_url=None, subtitle_headers=None,
                     keep_external_srt=True, recovery_url=None):
        """Tekil HLS / Segment Akışı veya Doğrudan MP4 Video İndirici."""
        if custom_headers is None:
            custom_headers = {}

        def log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    logger.debug("run_download log callback failed", exc_info=True)

        def set_status(text):
            if status_callback:
                status_callback(text)

        # Doğrudan mp4, webm, mkv vb. tek dosya ise
        clean_url_lower = sample_url.split("?")[0].lower()
        if clean_url_lower.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
            if "/seg-" not in sample_url and "/segment" not in sample_url and not re.search(r'_\d+\.mp4', sample_url):
                log("[i] Doğrudan video dosyası tespit edildi, yüksek hızlı indiriciye aktarılıyor...")
                return self.download_direct_file(
                    url=sample_url,
                    output_filepath=output_filepath,
                    custom_headers=custom_headers,
                    thread_count=thread_count,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                    status_callback=status_callback
                )

        # M3U8 Manifesti ise ve segment_urls verilmemişse otomatik ayrıştır
        stream_path = urlparse(sample_url).path
        looks_like_manifest = (
            clean_url_lower.endswith((".m3u8", ".txt"))
            or ".m3u8" in sample_url.lower()
            or "/m.php" in clean_url_lower
            or "/txt/" in clean_url_lower
            or "playlist" in clean_url_lower
            or not os.path.splitext(stream_path)[1]
        )
        if looks_like_manifest and not segment_urls:
            try:
                m3u8_segs = extract_m3u8_info(sample_url, custom_headers)
                if m3u8_segs:
                    segment_urls = m3u8_segs
                    log(f"M3U8 Manifesti Ayrıştırıldı: {len(segment_urls)} segment bulundu.")
            except Exception:
                logger.debug("[engine.py:1964] run_download() sessiz istisna yutuldu", exc_info=True)

        self.reset_cancel()
        self.is_running = True

        try:
            if not referer and custom_headers and "Referer" in custom_headers:
                referer = custom_headers["Referer"]

            if not referer:
                domain_match = re.search(r'https?://[^/]+', sample_url)
                referer = domain_match.group(0) if domain_match else "https://google.com/"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": referer,
                "Origin": referer.rstrip("/"),
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
            if custom_headers:
                headers.update(custom_headers)

            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(output_filepath))[0])
            base_temp = os.path.join(tempfile.gettempdir(), ".vdp_temp")
            temp_dir = os.path.join(base_temp, f".temp_{safe_name}")
            os.makedirs(temp_dir, exist_ok=True)
            self.active_temp_dir = temp_dir

            segment_tasks = []
            segment_paths = []

            if segment_urls and len(segment_urls) > 0:
                total_count = len(segment_urls) if (total_segments is None or total_segments <= 0) else min(len(segment_urls), total_segments)
                active_urls = segment_urls[:total_count]
                log(f"Manifest Segment Listesi Yüklendi: {total_count} adet parça")
                for i, seg_url in enumerate(active_urls):
                    target_path = os.path.join(temp_dir, f"seg_{i:07d}.tmp")
                    segment_tasks.append((i, seg_url, target_path))
                    segment_paths.append(target_path)
            else:
                set_status("URL Ayrıştırılıyor...")
                parsed_res = None
                try:
                    parsed_res = _get_engine_symbol('parse_segment_url', parse_segment_url)(sample_url)
                except ValueError:
                    parsed_res = None

                if parsed_res is None:
                    # Segment numarası bulunamadı, M3U8 manifesti olarak çözmeyi dene
                    m3_segs = extract_m3u8_info(sample_url, headers)
                    if m3_segs:
                        segment_urls = m3_segs
                        total_count = len(segment_urls) if (total_segments is None or total_segments <= 0) else min(len(segment_urls), total_segments)
                        active_urls = segment_urls[:total_count]
                        log(f"M3U8 Manifesti Ayrıştırıldı: {total_count} adet parça")
                        for i, seg_url in enumerate(active_urls):
                            target_path = os.path.join(temp_dir, f"seg_{i:07d}.tmp")
                            segment_tasks.append((i, seg_url, target_path))
                            segment_paths.append(target_path)
                    else:
                        raise ValueError(f"Geçersiz URL formatı. Segment numarası tespit edilemedi: {sample_url[:80]}")
                else:
                    prefix, padding, ext, query_fragment, parsed_sample_idx = parsed_res
                    log(f"Hedef Segment Şablonu: {prefix}{'0' * padding}{ext}{query_fragment}")

                    if total_segments is None or total_segments <= 0:
                        set_status("Segment Aralığı Taranıyor...")
                        detected_start, detected_total = _get_engine_symbol('detect_segment_range', detect_segment_range)(
                            prefix=prefix,
                            padding=padding,
                            ext=ext,
                            query_fragment=query_fragment,
                            headers=headers,
                            sample_index=parsed_sample_idx,
                            cancel_event=self.cancel_event,
                            log_callback=log,
                            status_callback=set_status,
                            session=self._session
                        )
                        start_index = detected_start if start_index is None else start_index
                        total_segments = detected_total

                    if start_index is None:
                        start_index = 0

                    if total_segments is None:
                        raise DownloadError("Segment aralığı tespit edilemedi veya canlı yayın desteklenmiyor.")

                    total_count = max(0, total_segments - start_index + 1)
                    log(f"Toplam Segment: {total_count} adet")
                    for i in range(start_index, total_segments + 1):
                        url = build_segment_url(prefix, i, padding, ext, query_fragment)
                        target_path = os.path.join(temp_dir, f"seg_{i:07d}.tmp")
                        segment_tasks.append((i, url, target_path))
                        segment_paths.append(target_path)

            # Önbellek Taraması (Resume Detection)
            cached_segs = sum(1 for p in segment_paths if is_valid_segment_file(p))
            cached_bytes = sum(os.path.getsize(p) for p in segment_paths if is_valid_segment_file(p))

            if cached_segs > 0:
                set_status(f"Kaldığı Yerden Devam Ediliyor ({cached_segs} / {total_count})...")
                log(f"[i] 🔄 Önbellek algılandı: {cached_segs} / {total_count} parça diskte mevcut. Kalan parçalar indiriliyor...")
            else:
                set_status(f"İndiriliyor (0 / {total_count})...")

            if progress_callback:
                progress_callback(cached_segs, total_count, cached_bytes, 0.0)

            # Crash Recovery durum kaydı (.vdp_state.json)
            write_recovery_state(temp_dir, {
                "url": sample_url,
                "title": os.path.splitext(os.path.basename(output_filepath))[0],
                "output_filepath": output_filepath,
                "total_segments": total_count,
                "downloaded_segments": cached_segs,
                "timestamp": time.time(),
                "custom_headers": _transport_headers(headers),
                "is_multi_audio": False,
                "raw_url": recovery_url or sample_url,
            })

            initial_bytes = cached_bytes
            last_calc_time = [time.time()]
            last_calc_bytes = [initial_bytes]
            last_state_write = [time.time()]
            current_ema_spd = [0.0]

            def p_cb(comp, tot, b):
                now = time.time()
                dt = now - last_calc_time[0]
                if dt >= 0.4:
                    new_delta = max(0, b - last_calc_bytes[0])
                    instant_spd = new_delta / dt
                    if current_ema_spd[0] == 0.0:
                        current_ema_spd[0] = instant_spd
                    else:
                        current_ema_spd[0] = 0.65 * instant_spd + 0.35 * current_ema_spd[0]
                    last_calc_time[0] = now
                    last_calc_bytes[0] = b
                spd = current_ema_spd[0]

                if (now - last_state_write[0]) >= 2.0:
                    update_recovery_progress(temp_dir, comp)
                    last_state_write[0] = now

                if progress_callback:
                    progress_callback(comp, tot, b, spd)

            completed_count, total_bytes, failed_segs = self.download_stream_segments(
                segment_tasks, headers, thread_count=thread_count, progress_callback=p_cb
            )

            if self.cancel_event.is_set():
                if self.cleanup_on_cancel and temp_dir:
                    cleanup_filesystem_path(temp_dir)
                set_status("İptal Edildi" if self.cleanup_on_cancel else "DURAKLATILDI")
                log("İndirme iptal edildi ve geçici dosyalar temizlendi." if self.cleanup_on_cancel else "İndirme duraklatıldı. İnen parçalar korundu.")
                return False, "İşlem iptal edildi." if self.cleanup_on_cancel else "İndirme duraklatıldı."

            if completed_count == 0:
                return False, "Segmentler indirilemedi."

            # Eksiksiz İndirme Doğrulaması (Strict Completeness Validation)
            v_missing = [p for p in segment_paths if not is_valid_segment_file(p)]
            if v_missing:
                tot_missing = len(v_missing)
                log(f"[!] UYARI: İndirme eksik kaldı ({tot_missing} adet parça sunucu zaman aşımı nedeniyle indirilemedi).")
                log("[i] İnen parçalar önbellekte korundu. '▶ İndirmeyi Başlat' butonuna tekrar basarak eksik parçaları kaldığı yerden indirebilirsiniz.")
                set_status(f"Eksik ({len(segment_paths)-tot_missing}/{len(segment_paths)} indi)")
                return False, f"İndirme eksik kaldı ({tot_missing} parça eksik). Tekrar başlatıp tamamlayın."

            set_status("Birleştiriliyor...")
            valid_paths = [p for p in segment_paths if is_valid_segment_file(p)]

            # Ham akışı geçici olarak birleştir
            temp_combined = os.path.join(temp_dir, "combined_stream.ts")
            with open(temp_combined, "wb") as outfile:
                for p in valid_paths:
                    with open(p, "rb") as infile:
                        shutil.copyfileobj(infile, outfile, length=524288)

            # Opsiyonel Altyazı indir ve SRT dönüştür (Türkçe karakter korumalı hibrit kayıt)
            sub_candidates = list(subtitles) if subtitles else []
            if subtitle_url:
                sub_candidates.insert(0, {"url": subtitle_url, "headers": subtitle_headers})

            sub_file_path = _get_engine_symbol('fetch_and_save_subtitle', fetch_and_save_subtitle)(
                subtitles=sub_candidates,
                output_filepath=output_filepath,
                session=self._session,
                default_headers=headers,
                log_callback=log
            )

            # merge_mode: "ffmpeg" -> daima remux, "binary" -> ham birlestirme,
            # "auto" (varsayilan) -> .mp4 hedeflerde remux, digerlerinde ham kopya.
            mode = str(merge_mode or "auto").lower().strip()
            if mode not in ("auto", "ffmpeg", "binary"):
                log(f"[!] Bilinmeyen birleştirme modu '{merge_mode}', 'auto' kullanılıyor.")
                mode = "auto"

            ffmpeg_bin = get_ffmpeg_path()
            remux_success = False
            want_remux = (mode == "ffmpeg") or (mode == "auto" and output_filepath.lower().endswith(".mp4"))
            if mode == "binary":
                log("[i] Birleştirme modu: binary — FFmpeg remux atlanıyor.")
            elif mode == "ffmpeg" and not (ffmpeg_bin and os.path.exists(ffmpeg_bin)):
                log("[!] Birleştirme modu 'ffmpeg' istendi ancak FFmpeg bulunamadı; ham birleştirmeye düşülüyor.")

            if want_remux and ffmpeg_bin and os.path.exists(ffmpeg_bin):
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", temp_combined,
                ]
                if sub_file_path and os.path.exists(sub_file_path):
                    cmd.extend([
                        "-i", os.path.abspath(sub_file_path),
                        "-c:v", "copy",
                        "-c:a", "copy",
                        "-bsf:a", "aac_adtstoasc",
                        "-c:s", "mov_text",
                        "-map", "0:v:0",
                        "-map", "0:a:0?",
                        "-map", "1:s:0?",
                        "-metadata:s:s:0", "language=tur",
                        "-metadata:s:s:0", "title=Türkçe Altyazı",
                        "-disposition:s:0", "default",
                        "-movflags", "+faststart",
                        output_filepath
                    ])
                else:
                    cmd.extend([
                        "-c", "copy",
                        "-bsf:a", "aac_adtstoasc",
                        "-movflags", "+faststart",
                        output_filepath
                    ])
                try:
                    p_ff = _get_engine_symbol('_run_subprocess', subprocess.run)(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300,
                                          creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
                    if p_ff.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
                        remux_success = True
                except subprocess.TimeoutExpired:
                    log("[!] FFmpeg remux zaman aşımına uğradı (300s); ham birleştirmeye düşülüyor.")
                    logger.warning("run_download FFmpeg remux zaman aşımına uğradı", exc_info=True)
                except Exception as ff_err:
                    log(f"[!] FFmpeg remux başarısız ({ff_err}); ham birleştirmeye düşülüyor.")
                    logger.warning("run_download remux hatasi", exc_info=True)

            if remux_success:
                if not keep_external_srt and sub_file_path and os.path.exists(sub_file_path):
                    try:
                        os.remove(sub_file_path)
                        log(f"[i] Harici altyazı dosyası temizlendi (Altyazı MP4 içine gömüldü): {os.path.basename(sub_file_path)}")
                    except Exception as e_rm:
                        logger.debug("Harici altyazı silinemedi: %s", e_rm, exc_info=True)
                    try:
                        tr_sub = os.path.splitext(sub_file_path)[0] + ".tr.srt"
                        if os.path.exists(tr_sub):
                            os.remove(tr_sub)
                    except Exception:
                        logger.debug("Embedded subtitle sidecar cleanup failed", exc_info=True)
            else:
                if os.path.exists(output_filepath):
                    try:
                        os.remove(output_filepath)
                    except Exception:
                        logger.debug("[engine.py:2127] run_download() sessiz istisna yutuldu", exc_info=True)
                shutil.copyfile(temp_combined, output_filepath)

            if not keep_temp:
                cleanup_filesystem_path(temp_dir)

            final_size_mb = os.path.getsize(output_filepath) / (1024 * 1024)
            set_status("Tamamlandı")
            log(f"[+] İndirme tamamlandı! Boyut: {final_size_mb:.2f} MB")
            return True, output_filepath

        except Exception as e:
            set_status(f"Hata: {str(e)[:40]}")
            return False, str(e)
        finally:
            self.is_running = False

    @staticmethod
    def normalize_media_url_for_ytdlp(url: str) -> str:
        """Normalize surrounding whitespace without changing the media address."""
        if not url:
            return url
        return str(url).strip()

    def extract_youtube_info(self, media_url, browser_cookies=None, cookies_file=None, log_callback=None):
        """
        yt-dlp kütüphanesini kullanarak videoyu indirmeden başlık, süre, kapak resmi ve mevcut çözünürlükleri analiz eder.
        """
        media_url = self.normalize_media_url_for_ytdlp(media_url)

        def log(msg):
            if log_callback:
                log_callback(msg)

        if yt_dlp is None:
            raise RuntimeError("yt-dlp kütüphanesi bulunamadı.")

        ffmpeg_bin = get_ffmpeg_path()
        node_path = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if os.path.exists(r"C:\Program Files\nodejs\node.exe") else None)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 20,
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            }
        }
        try:
            if sys.platform == "win32":
                from yt_dlp.networking.impersonate import ImpersonateTarget
                ydl_opts['impersonate'] = ImpersonateTarget.from_str('chrome')
        except Exception:
            logger.debug("[engine.py:2177] extract_youtube_info() sessiz istisna yutuldu", exc_info=True)

        if ffmpeg_bin:
            ydl_opts['ffmpeg_location'] = ffmpeg_bin
        if node_path:
            ydl_opts['js_runtimes'] = {'node': {'path': node_path}}

        if browser_cookies and str(browser_cookies).lower() not in ("kapalı", "none", "yok", "", "false", "0"):
            raw_b = str(browser_cookies).lower().strip()
            browser_map = {
                "chrome": "chrome", "google chrome": "chrome",
                "edge": "edge", "microsoft edge": "edge",
                "brave": "brave", "brave browser": "brave",
                "firefox": "firefox", "mozilla firefox": "firefox",
                "opera": "opera", "vivaldi": "vivaldi", "chromium": "chromium"
            }
            target_browser = browser_map.get(raw_b, raw_b)
            ydl_opts['cookiesfrombrowser'] = (target_browser,)

        if cookies_file:
            cleaned_cfile = os.path.normpath(str(cookies_file).strip().strip('"').strip("'"))
            if os.path.exists(cleaned_cfile):
                ydl_opts['cookiefile'] = cleaned_cfile
                log(f"[i] Çerez dosyası yüklendi: {os.path.basename(cleaned_cfile)}")

        log("[yt-dlp] Medya bilgileri ve mevcut çözünürlükler sorgulanıyor...")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(media_url, download=False)
                if not info:
                    raise RuntimeError("Medya bilgisi alınamadı.")

                title = info.get("title", "Video")
                duration = info.get("duration", 0)
                thumbnail = info.get("thumbnail", "")
                uploader = info.get("uploader", "")

                formats = info.get("formats", [])
                qualities = set()

                for f in formats:
                    h = f.get("height")
                    vcodec = f.get("vcodec")
                    if h and vcodec and vcodec != "none":
                        qualities.add(int(h))

                # Standart çözünürlük sıralaması (Büyükten küçüğe)
                sorted_h = sorted(list(qualities), reverse=True)
                available_qualities = []
                for h in sorted_h:
                    if h >= 2160:
                        lbl = f"🌟 {h}p (4K Ultra HD)"
                    elif h >= 1440:
                        lbl = f"📺 {h}p (2K Quad HD)"
                    elif h >= 1080:
                        lbl = f"🎬 {h}p Full HD"
                    elif h >= 720:
                        lbl = f"📺 {h}p HD"
                    elif h >= 480:
                        lbl = f"📱 {h}p SD"
                    elif h >= 360:
                        lbl = f"⚡ {h}p Düşük"
                    else:
                        lbl = f"⚡ {h}p"
                    if lbl not in available_qualities:
                        available_qualities.append(lbl)

                quality_options = []
                if available_qualities:
                    quality_options.append(f"🌟 En Yüksek Kalite ({available_qualities[0].split()[1]})")
                    for q in available_qualities:
                        if q not in quality_options:
                            quality_options.append(q)
                else:
                    quality_options = [
                        "🌟 En Yüksek Kalite (Otomatik)",
                        "🎬 1080p Full HD",
                        "📺 720p HD",
                        "📱 480p SD",
                        "⚡ 360p Düşük"
                    ]

                # Ses formatlarını ekle
                quality_options.append("🎵 Sadece Ses (MP3 320k Yüksek Kalite)")
                quality_options.append("🎧 Sadece Ses (M4A / Orijinal AAC)")

                log(f"[+] Çözümlendi: '{title[:45]}' ({len(available_qualities)} video kalitesi mevcut)")
                return {
                    "title": title,
                    "duration": duration,
                    "thumbnail": thumbnail,
                    "uploader": uploader,
                    "qualities": quality_options,
                    "raw_info": info
                }
        except Exception as e:
            log(f"[!] Çözümleme Hatası: {e}")
            raise e

    def download_youtube_media(self, media_url, output_dir, format_choice="best",
                               browser_cookies=None, cookies_file=None,
                               progress_callback=None, log_callback=None):
        """
        yt-dlp kütüphanesini kullanarak YouTube, Twitter (X), Instagram, TikTok vb. sitelerden video/ses indirir.
        Tarayıcı oturumları (Chrome, Edge, Brave, Firefox vb.) ve yaş sınırı aşma desteği içerir.
        """
        media_url = self.normalize_media_url_for_ytdlp(media_url)

        def log(msg):
            if log_callback:
                log_callback(msg)

        if yt_dlp is None:
            raise RuntimeError("yt-dlp kütüphanesi bulunamadı.")

        self.reset_cancel()
        self.is_running = True

        ffmpeg_bin = get_ffmpeg_path()
        if sys.platform != "win32":
            if ffmpeg_bin and os.path.exists(ffmpeg_bin):
                ff_loc = ffmpeg_bin
            elif os.path.exists("/data/data/com.videodownloaderpro.app/files/usr/bin/ffmpeg"):
                ff_loc = "/data/data/com.videodownloaderpro.app/files/usr/bin"
            else:
                ff_loc = None
        else:
            bin_dir = os.path.join(os.environ.get("TEMP", r"C:\Users\Public"), "videodownloader_bin")
            os.makedirs(bin_dir, exist_ok=True)
            target_ffmpeg = os.path.join(bin_dir, "ffmpeg.exe")
            if ffmpeg_bin and os.path.exists(ffmpeg_bin):
                if not os.path.exists(target_ffmpeg) or os.path.getsize(target_ffmpeg) != os.path.getsize(ffmpeg_bin):
                    try:
                        shutil.copyfile(ffmpeg_bin, target_ffmpeg)
                    except Exception:
                        logger.debug("[engine.py:2310] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
            if os.path.exists(bin_dir):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            ff_loc = bin_dir if os.path.exists(target_ffmpeg) else ffmpeg_bin

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 20,
            'fragment_retries': 20,
            'continuedl': True,
            'concurrent_fragment_downloads': 32,
            'http_chunk_size': 10485760,
            'buffersize': 2097152,
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            }
        }
        # Hızlı dış indirici aria2c desteği
        aria2c_exe = shutil.which("aria2c")
        if aria2c_exe:
            ydl_opts['external_downloader'] = {'default': 'aria2c'}
            ydl_opts['external_downloader_args'] = {'aria2c': ['-s', '32', '-x', '32', '-k', '1M', '-j', '32', '--min-split-size=1M']}

        try:
            if sys.platform == "win32":
                from yt_dlp.networking.impersonate import ImpersonateTarget
                ydl_opts['impersonate'] = ImpersonateTarget.from_str('chrome')
        except Exception:
            logger.debug("[engine.py:2348] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
        if ff_loc:
            ydl_opts['ffmpeg_location'] = ff_loc
        node_path = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if os.path.exists(r"C:\Program Files\nodejs\node.exe") else None)
        if node_path:
            ydl_opts['js_runtimes'] = {'node': {'path': node_path}}

        # Tarayıcı Çerezleri / Oturum Entegrasyonu
        if browser_cookies and str(browser_cookies).lower() not in ("kapalı", "none", "yok", "", "false", "0"):
            raw_b = str(browser_cookies).lower().strip()
            browser_map = {
                "chrome": "chrome",
                "google chrome": "chrome",
                "edge": "edge",
                "microsoft edge": "edge",
                "brave": "brave",
                "brave browser": "brave",
                "firefox": "firefox",
                "mozilla firefox": "firefox",
                "opera": "opera",
                "vivaldi": "vivaldi",
                "chromium": "chromium"
            }
            target_browser = browser_map.get(raw_b, raw_b)
            ydl_opts['cookiesfrombrowser'] = (target_browser,)
            log(f"[i] Oturum: {target_browser.capitalize()}")

        if cookies_file:
            cleaned_cfile = os.path.normpath(str(cookies_file).strip().strip('"').strip("'"))
            if os.path.exists(cleaned_cfile):
                ydl_opts['cookiefile'] = cleaned_cfile
                log(f"[i] Çerez dosyası yüklendi: {os.path.basename(cleaned_cfile)}")

        has_ffmpeg = bool(ff_loc and (os.path.exists(ff_loc) or (isinstance(ff_loc, str) and os.path.exists(os.path.join(ff_loc, 'ffmpeg.exe')))))
        fmt_str = str(format_choice).lower().strip()
        if not has_ffmpeg:
            if "mp3" in fmt_str or "m4a" in fmt_str or "aac" in fmt_str:
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
            else:
                height_match = re.search(r'(\d+)p', fmt_str)
                if height_match:
                    h = int(height_match.group(1))
                    ydl_opts['format'] = f'best[height<={h}][ext=mp4]/best[height<={h}]/best[ext=mp4]/best'
                elif "2k" in fmt_str:
                    ydl_opts['format'] = 'best[height<=1440][ext=mp4]/best[height<=1440]/best[ext=mp4]/best'
                elif "4k" in fmt_str:
                    ydl_opts['format'] = 'best[height<=2160][ext=mp4]/best[height<=2160]/best[ext=mp4]/best'
                else:
                    ydl_opts['format'] = 'best[ext=mp4]/best'
        else:
            if "mp3" in fmt_str:
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320',
                    }],
                })
            elif "m4a" in fmt_str or "aac" in fmt_str:
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
            else:
                height_match = re.search(r'(\d+)p', fmt_str)
                if height_match:
                    h = int(height_match.group(1))
                    ydl_opts['format'] = f'bestvideo[height={h}]+bestaudio[ext=m4a]/bestvideo[height={h}]+bestaudio/bestvideo[height<={h}]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height={h}]/best[height<={h}]/best'
                    ydl_opts['merge_output_format'] = 'mp4'
                elif "2k" in fmt_str:
                    ydl_opts['format'] = 'bestvideo[height<=1440]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best'
                    ydl_opts['merge_output_format'] = 'mp4'
                elif "4k" in fmt_str:
                    ydl_opts['format'] = 'bestvideo[height<=2160]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160]/best'
                    ydl_opts['merge_output_format'] = 'mp4'
                else:
                    ydl_opts['format'] = 'bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
                    ydl_opts['merge_output_format'] = 'mp4'

        def ytdl_hook(d):
            if self.cancel_event.is_set():
                raise CancelledError("İndirme kullanıcı tarafından iptal edildi.")
            if d['status'] == 'downloading':
                tot = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed') or 0
                ratio = downloaded / tot if tot > 0 else 0
                if progress_callback:
                    progress_callback(downloaded, tot, speed, ratio)
            elif d['status'] == 'finished':
                log(f"[+] İndirme tamamlandı, ses ve video birleştiriliyor...")

        ydl_opts['progress_hooks'] = [ytdl_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(media_url, download=True)
                filename = ydl.prepare_filename(info)
                if "mp3" in fmt_str:
                    target_mp3 = os.path.splitext(filename)[0] + ".mp3"
                    if os.path.exists(target_mp3) and os.path.getsize(target_mp3) > 1024:
                        filename = target_mp3
                    elif os.path.exists(filename) and filename != target_mp3:
                        conv_ok, conv_res = self.convert_media_to_audio(filename, target_mp3, audio_format="mp3", bitrate="320k", log_callback=log)
                        if conv_ok:
                            try:
                                os.remove(filename)
                            except Exception:
                                logger.debug("[engine.py:2454] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
                            filename = target_mp3
                elif has_ffmpeg and os.path.exists(filename) and filename.lower().endswith(('.mp4', '.mkv', '.webm')):
                    # Windows Media Player ve tüm cihazlarla %100 ses uyumluluğu için Opus/Vorbis -> AAC kontrolü
                    try:
                        ff_bin = ffmpeg_bin if (ffmpeg_bin and os.path.exists(ffmpeg_bin)) else "ffmpeg"
                        c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                        probe_proc = subprocess.Popen(
                            [ff_bin, '-i', filename],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            creationflags=c_flags
                        )
                        try:
                            probe_out, _ = probe_proc.communicate(timeout=30)
                        except subprocess.TimeoutExpired:
                            probe_proc.kill()
                            probe_proc.communicate()
                            log("[!] FFmpeg probe zaman aşımına uğradı (30s).")
                            probe_out = ""

                        # Eğer ses akışı Opus veya Vorbis ise, Windows Media Player sessiz oynatır; hızlıca kayıpsız AAC'ye çevir
                        if "Audio: opus" in probe_out or "Audio: vorbis" in probe_out:
                            log("[FFmpeg] Ses akışı evrensel AAC formatına dönüştürülüyor (Windows Media & Mobil uyumluluğu)...")
                            tmp_fixed = os.path.splitext(filename)[0] + "_aactmp.mp4"
                            fix_cmd = [ff_bin, '-y', '-i', filename, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', tmp_fixed]
                            fix_p = subprocess.Popen(
                                fix_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                creationflags=c_flags
                            )
                            try:
                                fix_p.communicate(timeout=600)
                            except subprocess.TimeoutExpired:
                                fix_p.kill()
                                fix_p.communicate()
                                log("[!] FFmpeg AAC dönüştürme zaman aşımına uğradı (600s).")

                            if os.path.exists(tmp_fixed) and os.path.getsize(tmp_fixed) > 1024:
                                try:
                                    os.replace(tmp_fixed, filename)
                                except Exception:
                                    shutil.move(tmp_fixed, filename)
                                log("[+] Ses ve video kristal netliğinde birleştirildi (AAC 192k) ✓")
                    except Exception as _e_aac:
                        log(f"[!] AAC ses kontrolü uyarısı: {_e_aac}")
                return True, filename
        except Exception as e:
            # ─── FIX 6: .part ve .ytdl Temizliği ──────────────────────────────────
            if self.cancel_event.is_set():
                try:
                    for f in os.listdir(output_dir):
                        if f.endswith('.part') or f.endswith('.ytdl'):
                            try:
                                os.remove(os.path.join(output_dir, f))
                            except Exception:
                                logger.debug("[engine.py:2487] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
                except Exception:
                    logger.debug("[engine.py:2489] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
                return False, "İndirme kullanıcı tarafından iptal edildi."
            else:
                # İptal dışı kritik hatalarda geçersiz .ytdl kalıntılarını temizle
                try:
                    for f in os.listdir(output_dir):
                        if f.endswith('.ytdl'):
                            try:
                                os.remove(os.path.join(output_dir, f))
                            except Exception:
                                logger.debug("[engine.py:2499] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
                except Exception:
                    logger.debug("[engine.py:2501] download_youtube_media() sessiz istisna yutuldu", exc_info=True)
            # ────────────────────────────────────────────────────────────────────────
            return False, str(e)
        finally:
            self.is_running = False




normalize_media_url_for_ytdlp = VideoDownloadEngine.normalize_media_url_for_ytdlp


__all__ = [
    "extract_m3u8_info",
    "detect_segment_range",
    "normalize_media_url_for_ytdlp",
    "VideoDownloadEngine",
]
