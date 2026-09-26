# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Segment and Direct File Downloaders.
"""

import os
import time
import shutil
import tempfile
import threading
import hashlib
import re
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

try:
    from curl_cffi import requests as c_requests
    from curl_cffi.requests import AsyncSession as c_AsyncSession
except ImportError:
    c_requests = None
    c_AsyncSession = None

from engine_core.crypto import decrypt_hls_segment
from engine_core.utils import (
    is_valid_segment_file,
    cleanup_filesystem_path,
)

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
    from exceptions import CancelledError
except ImportError:
    try:
        from core.exceptions import CancelledError
    except ImportError:
        class CancelledError(Exception): pass

logger = get_logger("engine_core.downloader")

_INTERNAL_STREAM_HEADER_KEYS = {"aes_key", "aes_iv", "aes_media_sequence"}


def _close_response(response):
    if response is not None and hasattr(response, "close"):
        try:
            response.close()
        except Exception:
            logger.debug("Segment response could not be closed", exc_info=True)


class SegmentDownloaderMixin:
    """Segment downloading, retry handling, and direct file streaming mixin."""

    def is_turbo_boosted(self):
        """Video tamamlandığında veya boşa çıkan worker olduğunda Turbo Boost durumunu sorgular."""
        return getattr(self, "turbo_boost_event", None) is not None and self.turbo_boost_event.is_set()

    def download_segment_file(self, url, headers, target_path, max_retries=4, chunk_size=65536,
                              fallback_host=None, segment_index=None):
        if self.cancel_event.is_set():
            return False, 0

        if is_valid_segment_file(target_path):
            return True, os.path.getsize(target_path)

        aes_key = None
        aes_iv = None
        aes_media_sequence = 0
        req_headers = headers
        if isinstance(headers, dict):
            aes_key = headers.get("aes_key")
            aes_iv = headers.get("aes_iv")
            aes_media_sequence = headers.get("aes_media_sequence", 0)
            if any(str(k).lower() in _INTERNAL_STREAM_HEADER_KEYS for k in headers):
                req_headers = {
                    k: v for k, v in headers.items()
                    if str(k).lower() not in _INTERNAL_STREAM_HEADER_KEYS
                }

        crypto_sequence = segment_index
        if segment_index is not None:
            try:
                crypto_sequence = int(aes_media_sequence) + int(segment_index)
            except (TypeError, ValueError):
                logger.warning("Invalid AES media sequence; task index will be used")

        temp_part = target_path + ".part"
        current_url = url
        if isinstance(fallback_host, str):
            fallback_hosts = [fallback_host]
        else:
            fallback_hosts = list(fallback_host or [])
        fallback_position = 0

        def switch_to_sibling_host():
            nonlocal current_url, fallback_position
            parsed = urlparse(current_url)
            while fallback_position < len(fallback_hosts):
                candidate_host = fallback_hosts[fallback_position]
                fallback_position += 1
                if candidate_host and candidate_host != parsed.netloc:
                    current_url = urlunparse((
                        parsed.scheme,
                        candidate_host,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    ))
                    return True
            return False

        for attempt in range(1, max_retries + 1):
            if self.cancel_event.is_set():
                if os.path.exists(temp_part):
                    try:
                        os.remove(temp_part)
                    except OSError:
                        logger.debug("[engine.py:734] download_segment_file() temp_part kaldirma istisnasi", exc_info=True)
                return False, 0

            session = self._get_session()
            response = None
            try:
                # Askıda kalan soketleri düşür (workers.dev için 6s, genel için 10s; handshake için 5.0s)
                t_read = 6.0 if "workers.dev" in current_url.lower() else 10.0
                # Cok-shardli CDN'lerde bozuk bir origin, connect timeout'unu
                # birden fazla IP icin tuketebiliyor. Kardes host varken daha
                # erken gec; tek-origin akislarda ihtiyatli degerleri koru.
                t_connect = 2.0 if len(fallback_hosts) > 1 else 5.0
                if len(fallback_hosts) > 1:
                    t_read = min(t_read, 6.0)
                response = session.get(current_url, headers=req_headers, timeout=(t_connect, t_read))
                if response.status_code == 200:
                    if hasattr(response, "content") and isinstance(response.content, (bytes, bytearray)):
                        raw_data = response.content
                    elif hasattr(response, "iter_content"):
                        try:
                            raw_data = b"".join(response.iter_content(chunk_size=chunk_size))
                        except Exception:
                            raw_data = b""
                    else:
                        raw_data = b""

                    if self.cancel_event.is_set():
                        return False, 0
                    if not raw_data:
                        continue

                    # ─── FIX 2: Segment İçerik Doğrulama ──────────────────────
                    # M3U8 playlist veya HTML sayfası segment olarak gelirse reddet
                    _seg_peek = raw_data[:16] if isinstance(raw_data, (bytes, bytearray)) else b""
                    if _seg_peek.startswith(b"#EXTM3U") or _seg_peek.startswith(b"#EXT-X"):
                        return False, 0
                    if _seg_peek.startswith(b"<!DOCTYPE") or _seg_peek.startswith(b"<html") or _seg_peek.startswith(b"<HTML"):
                        return False, 0
                    _ct = response.headers.get("Content-Type", "").lower() if hasattr(response, "headers") else ""
                    # Bazi CDN'ler .png/.jpg gorunumlu gercek MPEG-TS parcilarini
                    # hatali olarak application/x-mpegURL ile etiketliyor. Govde
                    # TS sync byte'i ile basliyorsa icerik tipi yerine bayta guven.
                    mislabeled_transport_stream = _seg_peek.startswith(b"\x47")
                    if "text/html" in _ct or ("mpegurl" in _ct and not mislabeled_transport_stream):
                        return False, 0
                    # ───────────────────────────────────────────────────────────

                    if aes_key:
                        decrypted = decrypt_hls_segment(raw_data, aes_key, aes_iv, crypto_sequence)
                        if decrypted is None:
                            # Sifreli veriyi asla diske yazma: oynatilamayan dosya uretir.
                            logger.warning("Segment cozulemedi, atlaniyor: %s", current_url[:120])
                            return False, 0
                        raw_data = decrypted
                    with open(temp_part, "wb") as f:
                        f.write(raw_data)
                    bytes_written = len(raw_data)

                    if self.cancel_event.is_set():
                        if os.path.exists(temp_part):
                            os.remove(temp_part)
                        return False, 0

                    published = False
                    try:
                        os.replace(temp_part, target_path)
                        published = True
                    except Exception:
                        try:
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            os.rename(temp_part, target_path)
                            published = True
                        except Exception:
                            logger.debug("[engine.py:685] download_segment_file() sessiz istisna yutuldu", exc_info=True)
                    if published and is_valid_segment_file(target_path):
                        return True, bytes_written
                    logger.debug(
                        "Segment payload could not be published as a valid file: index=%s target=%s",
                        segment_index,
                        target_path,
                    )
                    continue
                elif response.status_code in (403, 429) and c_requests:
                    c_resp = None
                    try:
                        c_resp = c_requests.get(current_url, headers=req_headers, impersonate="chrome124", timeout=10)
                        if c_resp.status_code == 200:
                            raw_data = c_resp.content
                            if aes_key:
                                decrypted = decrypt_hls_segment(raw_data, aes_key, aes_iv, crypto_sequence)
                                if decrypted is None:
                                    logger.warning("Segment cozulemedi (curl_cffi), atlaniyor: %s", current_url[:120])
                                    return False, 0
                                raw_data = decrypted
                            with open(temp_part, "wb") as f_c:
                                f_c.write(raw_data)
                            try:
                                os.replace(temp_part, target_path)
                            except Exception:
                                logger.debug("[engine.py] curl_cffi yolunda .part yeniden adlandirilamadi",
                                             exc_info=True)
                                return False, 0
                            return True, len(raw_data)
                    except Exception:
                        logger.debug("[engine.py:716] curl_cffi fallback istisnasi", exc_info=True)
                    finally:
                        _close_response(c_resp)
                
                if response.status_code in (404, 403, 500, 502, 503, 429):
                    if switch_to_sibling_host():
                        continue
                    if attempt < max_retries:
                        time.sleep(0.25 * attempt)
                        continue
                return False, 0
            except Exception as e_seg:
                logger.debug("Seg %s (att %d/%d) istisnasi: %s -> %s", segment_index, attempt, max_retries, type(e_seg).__name__, e_seg)
                # Askıda kalan veya bağlantısı kopan soketi hemen düşür
                if hasattr(self._tls, "session"):
                    try:
                        self._tls.session.close()
                    except Exception:
                        logger.debug("[engine.py:832] session.close() istisnasi", exc_info=True)
                    del self._tls.session
                # DNS / Bağlantı hatası durumunda fallback host'a otomatik geç
                switch_to_sibling_host()
            finally:
                _close_response(response)

        if os.path.exists(temp_part):
            try:
                os.remove(temp_part)
            except OSError:
                logger.debug("[engine.py:737] download_segment_file() sessiz istisna yutuldu", exc_info=True)
        return False, 0

    def download_stream_segments(self, segment_tasks, headers, thread_count, progress_callback=None, log_callback=None,
                                 fallback_hosts=None):
        def log(msg):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    logger.debug("[engine.py:746] log() sessiz istisna yutuldu", exc_info=True)

        # CDN soket boğulması ve hız düşüşünü önleyen optimum paralel worker sınırı
        max_stream_workers = 64
        if segment_tasks and any("cdnimages" in t[1].lower() for t in segment_tasks[:5]):
            cdnimages_hosts = {urlparse(task[1]).netloc for task in segment_tasks}
            if len(cdnimages_hosts) <= 1:
                max_stream_workers = 2
            elif len(cdnimages_hosts) <= 4:
                max_stream_workers = 4
            else:
                max_stream_workers = 16
            thread_count = min(thread_count, max_stream_workers)

        # Segment listesindeki baskin CDN hostu; 404 veya DNS hatasinda tekil
        # segmentler bu hosta yonlendirilerek kurtarilir (CDN host auto-healing).
        fallback_host = None
        if segment_tasks:
            host_freq = {}
            for _, u, _ in segment_tasks:
                h = urlparse(u).netloc
                if h:
                    host_freq[h] = host_freq.get(h, 0) + 1
            if host_freq:
                top_host, top_count = max(host_freq.items(), key=lambda kv: kv[1])
                if top_count / max(1, len(segment_tasks)) > 0.7:
                    fallback_host = top_host

        # Video ve ayrik ses playlistleri ayni CDN ailesinin farkli shard'larina
        # dagitilabilir. Pipeline tarafindan dogrulanmis kardes host havuzu,
        # ozellikle tek hosta sabitlenmis ses akisini gecici shard arizalarindan
        # kurtarir. Mevcut akistan bulunan hostlari da koruyup sirali tekillestir.
        if fallback_hosts is None:
            fallback_hosts = getattr(self, "shared_fallback_hosts", ())
        if fallback_hosts:
            combined_hosts = []
            local_hosts = (
                [fallback_host] if isinstance(fallback_host, str) else list(fallback_host or ())
            )
            # Keep-alive daraltmasinda her stream once kendi playlist hostlarini
            # kullanir; diger stream'lerden gelen havuz yalniz failover'dur.
            for host in local_hosts + list(fallback_hosts):
                if host and host not in combined_hosts:
                    combined_hosts.append(host)
            fallback_host = tuple(combined_hosts)

        # 1. Önbellek Taraması (Resume Detection): Zaten inmiş geçerli parçaları tespit et
        cached_tasks = []
        pending_tasks = []
        cached_bytes = 0

        target_dir = os.path.dirname(segment_tasks[0][2]) if segment_tasks else None
        try:
            existing_dir_files = set(os.listdir(target_dir)) if target_dir and os.path.exists(target_dir) else set()
        except Exception:
            existing_dir_files = None

        for idx, url, path in segment_tasks:
            base_name = os.path.basename(path)
            if existing_dir_files is not None and base_name not in existing_dir_files:
                pending_tasks.append((idx, url, path))
            elif is_valid_segment_file(path):
                cached_tasks.append((idx, url, path))
                cached_bytes += os.path.getsize(path)
            else:
                pending_tasks.append((idx, url, path))

        completed_count = len(cached_tasks)
        total_bytes = cached_bytes
        failed_indices = []

        if completed_count > 0:
            log(f"[i] 🔄 Önbellek algılandı: {completed_count} / {len(segment_tasks)} parça önceden indirilmiş! Kalan {len(pending_tasks)} parça indiriliyor...")
            if progress_callback:
                progress_callback(completed_count, len(segment_tasks), total_bytes)

        if not pending_tasks:
            log(f"[[+]] Tüm {len(segment_tasks)} segment önbellekten eksiksiz yüklendi!")
            return completed_count, total_bytes, []

        # Dinamik shard daraltmasi ana tur URL'lerini degistirebilir. Recovery,
        # kalici olarak yavas/bozuk secilen havuza mahkum kalmamali; manifestin
        # her segment icin verdigi ozgun hostu geri kullanabilsin.
        original_pending_urls = {idx: url for idx, url, _path in pending_tasks}

        # Some wildcard HLS CDNs put almost every segment on a new hostname.
        # Thousands of cold DNS/TLS handshakes create false failures even though
        # the manifest-provided hosts serve byte-identical signed paths. Limit
        # only this exact CDN layout to a bounded, same-token host pool.
        dynamic_cfd_hosts = []
        dynamic_cfd_token = None
        dynamic_cfd_family = True
        for _idx, task_url, _path in pending_tasks:
            task_host = urlparse(task_url).netloc.lower()
            match = re.fullmatch(r"(lkm-[a-z0-9]+)\.([a-z0-9]{10})\.cfd", task_host)
            if not match:
                dynamic_cfd_family = False
                break
            if dynamic_cfd_token is None:
                dynamic_cfd_token = match.group(1)
            elif match.group(1) != dynamic_cfd_token:
                dynamic_cfd_family = False
                break
            if task_host not in dynamic_cfd_hosts:
                dynamic_cfd_hosts.append(task_host)

        if dynamic_cfd_family and len(dynamic_cfd_hosts) > 32:
            stable_hosts = tuple(dynamic_cfd_hosts[:64])
            stabilized_tasks = []
            for task_position, (idx, task_url, path) in enumerate(pending_tasks):
                parsed_task = urlparse(task_url)
                stable_url = urlunparse((
                    parsed_task.scheme,
                    stable_hosts[task_position % len(stable_hosts)],
                    parsed_task.path,
                    parsed_task.params,
                    parsed_task.query,
                    parsed_task.fragment,
                ))
                stabilized_tasks.append((idx, stable_url, path))
            pending_tasks = stabilized_tasks
            fallback_host = stable_hosts
            log(
                f"[i] Wildcard CDN DNS havuzu {len(dynamic_cfd_hosts)} hosttan "
                f"{len(stable_hosts)} manifest hostuna daraltıldı."
            )

        # curl_cffi async yolu deneyseldir ve yalnız açıkça istendiğinde çalışır. Çok-hostlu
        # playlistler binlerce farklı origin içerebilir; bunları otomatik olarak batch yoluna
        # geçirmek DNS/TLS yükü ve batch head-of-line beklemeleri üretir.
        use_curl_async = bool(os.environ.get("VDP_USE_CURL_ASYNC"))
        if use_curl_async and c_AsyncSession:
            # Yüksek hızlı HTTP/2 Multiplexing AsyncSession motoru
            try:
                c_comp, c_bytes, failed_indices = self._download_stream_curl_async(
                    pending_tasks=pending_tasks,
                    headers=headers,
                    thread_count=thread_count,
                    base_completed=completed_count,
                    base_bytes=total_bytes,
                    total_tasks_len=len(segment_tasks),
                    progress_callback=progress_callback,
                    log_callback=log
                )
                completed_count += c_comp
                total_bytes += c_bytes
            except Exception as e_async:
                log(f"[i] Async motor yedekleme moduna geçiyor: {e_async}")
                failed_indices = [t[0] for t in pending_tasks if not is_valid_segment_file(t[2])]
        else:
            # 🚀 Optimum Eşzamanlılık ve CDN Koruma Kalkanı (Anti-Congestion Sweet Spot)
            # Cloudflare Worker (.workers.dev) IP başına 12 bağlantıda rate-limit uygular.
            # Dystream / Diziyou sunucuları 48 iş parçacığına kadar tam bant genişliği (60-80+ MB/s) sağlar.
            # Pilavyer / FilmModu 6 farklı Cloudflare alan adına dağıtılmış olduğundan 36 iş parçacığına kadar güvenle ölçeklenir.
            # Diğer yüksek kapasiteli CDN'ler kullanıcının belirlediği thread_count (32-64x) ile tam hızda çalışır.
            is_cf_worker = pending_tasks and any("workers.dev" in t[1].lower() for t in pending_tasks[:5])
            is_dy_stream = pending_tasks and any("dystream" in t[1].lower() for t in pending_tasks[:5])
            is_pilavyer = pending_tasks and any("pilavyer" in t[1].lower() for t in pending_tasks[:5])

            if is_cf_worker:
                eff_workers = min(thread_count, 10)
                log(f"[i] 🛡️ Cloudflare Worker CDN tespit edildi: İş parçacığı {eff_workers} olarak optimize edildi.")
            elif is_dy_stream:
                eff_workers = min(max(2, thread_count), 6)
                if eff_workers < thread_count:
                    log(f"[i] 🛡️ Dystream/Nginx CDN koruma kalkanı: İş parçacığı {eff_workers} olarak optimize edildi.")
            elif is_pilavyer:
                eff_workers = min(max(4, thread_count), 48)
                if eff_workers < thread_count:
                    log(f"[i] 🛡️ Pilavyer/Cloudflare CDN koruma kalkanı: İş parçacığı {eff_workers} olarak optimize edildi.")
            else:
                eff_workers = min(max(2, thread_count), 64)
                if eff_workers < thread_count:
                    log(f"[i] 🛡️ CDN koruma ve maksimum verim kalkanı: İş parçacığı {eff_workers} olarak optimize edildi.")

            # Multi-Domain Round-Robin Interleaving (Anti-Host Congestion & Rate-Limit Shield)
            # FilmModu/Pilavyer gibi parçaları 6 farklı alt alan adına (pilavyer1..6) dağıtan CDN'lerde
            # görevleri sırayla d1, d2, d3... şeklinde dağıtarak tek bir host üzerinde TCP yığılmasını önle
            tasks_domains = set(urlparse(t[1]).netloc for t in pending_tasks)
            # Bazi HLS saglayicilari neredeyse her segment icin yeni bir kardes
            # hostname uretir. Bu, keep-alive'i tamamen etkisizlestirip binlerce
            # DNS/TLS kurulumu yapar. Ayni CDN ailesi daha once dogrulandiysa
            # yogun dinamik shard listesini dort kararlı hosta round-robin daralt.

            if len(tasks_domains) > 1:
                by_dom = {}
                for t in pending_tasks:
                    d = urlparse(t[1]).netloc
                    by_dom.setdefault(d, []).append(t)
                interleaved = []
                max_len = max(len(v) for v in by_dom.values())
                dom_keys = list(by_dom.keys())
                for i in range(max_len):
                    for d in dom_keys:
                        if i < len(by_dom[d]):
                            interleaved.append(by_dom[d][i])
                pending_tasks = interleaved

            with ThreadPoolExecutor(max_workers=eff_workers) as executor:
                # Kayan Pencere (Sliding Window Bounded Queue): Bellek şişmesini ve askıda kalan
                # binlerce future nesnesini önlemek için aynı anda en fazla eff_workers * 4 görev tutulur.
                task_iter = iter(pending_tasks)
                window_size = min(len(pending_tasks), max(16, eff_workers * 4))
                futures = {}

                for task_idx_init in range(window_size):
                    task = next(task_iter, None)
                    if task:
                        idx, url, path = task
                        f = executor.submit(self.download_segment_file, url, headers, path,
                                            max_retries=4, fallback_host=fallback_host, segment_index=idx)
                        futures[f] = (idx, path)
                        if is_dy_stream and task_idx_init < eff_workers:
                            time.sleep(0.025)

                while futures:
                    if self.cancel_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    # Turbo Boost dinamik worker devri: Video bittiğinde boşa çıkan worker'ları anında bu akışa devret
                    boost_workers = min(
                        max_stream_workers,
                        eff_workers + max(0, int(getattr(self, "turbo_extra_workers", 0))),
                    )
                    if self.is_turbo_boosted() and getattr(executor, "_max_workers", eff_workers) < boost_workers:
                        previous_workers = getattr(executor, "_max_workers", eff_workers)
                        executor._max_workers = boost_workers
                        for _ in range(boost_workers - previous_workers):
                            executor._adjust_thread_count()
                        window_size = min(len(pending_tasks), boost_workers * 4)
                        while len(futures) < window_size and not self.cancel_event.is_set():
                            next_task = next(task_iter, None)
                            if not next_task:
                                break
                            n_idx, n_url, n_path = next_task
                            nf = executor.submit(self.download_segment_file, n_url, headers, n_path,
                                                 max_retries=4, fallback_host=fallback_host, segment_index=n_idx)
                            futures[nf] = (n_idx, n_path)

                    done, _ = wait(futures.keys(), timeout=0.5, return_when=FIRST_COMPLETED)
                    if not done:
                        continue

                    for future in done:
                        idx, path = futures.pop(future)
                        try:
                            success, b_down = future.result()
                            if success:
                                completed_count += 1
                                total_bytes += b_down
                            else:
                                failed_indices.append(idx)
                        except Exception:
                            logger.warning(
                                "Segment worker failed unexpectedly: index=%s url=%s",
                                idx,
                                original_pending_urls.get(idx, "")[:160],
                                exc_info=True,
                            )
                            failed_indices.append(idx)

                        if progress_callback:
                            progress_callback(completed_count, len(segment_tasks), total_bytes)

                        # Yeni görevi pencereye al
                        next_task = next(task_iter, None)
                        if next_task and not self.cancel_event.is_set():
                            n_idx, n_url, n_path = next_task
                            nf = executor.submit(self.download_segment_file, n_url, headers, n_path,
                                                 max_retries=4, fallback_host=fallback_host, segment_index=n_idx)
                            futures[nf] = (n_idx, n_path)

        # Ana indirme turundan sonra iki sabit ve merkezi kurtarma turu uygula.
        # Pipeline seviyesinde ek retry döngüsü yoktur; böylece geçici CDN tail
        # hataları tamamlanırken kalıcı bir hata sonsuz döngüye dönüşmez.
        max_sweep_rounds = 2
        sweep_round = 1
        while failed_indices and sweep_round <= max_sweep_rounds and not self.cancel_event.is_set():
            retry_tasks = [
                (i, original_pending_urls.get(i, u), p)
                for (i, u, p) in pending_tasks
                if i in failed_indices and not is_valid_segment_file(p)
            ]
            failed_indices = []
            if not retry_tasks:
                break
            log(f"[i] 🔄 {len(retry_tasks)} eksik parça için otomatik kurtarma turu #{sweep_round} başlatılıyor...")
            time.sleep(0.3 * sweep_round)
            # Ilk tur hizli ve sinirli; yalniz hala kalan tail segmentleri icin
            # ikinci/son tur dusuk eszamanlilik ve daha genis host denemesiyle
            # calisir. Tur sayisi sabittir, sonsuz recovery dongusu olusmaz.
            final_sweep = max_sweep_rounds > 1 and sweep_round == max_sweep_rounds
            retry_workers = min(len(retry_tasks), 2 if final_sweep else 6)
            retry_attempts = 4 if final_sweep else 2
            with ThreadPoolExecutor(max_workers=retry_workers) as retry_exec:
                retry_futures = {
                    retry_exec.submit(self.download_segment_file, url, headers, path, max_retries=retry_attempts,
                                      fallback_host=fallback_host, segment_index=idx): (idx, path)
                    for idx, url, path in retry_tasks
                }
                for future in as_completed(retry_futures):
                    if self.cancel_event.is_set():
                        retry_exec.shutdown(wait=False, cancel_futures=True)
                        break
                    idx, path = retry_futures[future]
                    try:
                        success, b_down = future.result()
                        if success or is_valid_segment_file(path):
                            completed_count += 1
                            total_bytes += b_down
                        else:
                            failed_indices.append(idx)
                    except Exception:
                        logger.warning(
                            "Segment recovery worker failed: index=%s url=%s",
                            idx,
                            original_pending_urls.get(idx, "")[:160],
                            exc_info=True,
                        )
                        if not is_valid_segment_file(path):
                            failed_indices.append(idx)

                    if progress_callback:
                        progress_callback(completed_count, len(segment_tasks), total_bytes)
            sweep_round += 1

        # A rate-limited origin can leave only a handful of segments after the
        # two normal sweeps. Give that small tail one final serial verification;
        # keep it strictly bounded so permanent failures can never loop.
        if 0 < len(failed_indices) <= 8 and not self.cancel_event.is_set():
            tail_tasks = [
                (i, original_pending_urls.get(i, u), p)
                for (i, u, p) in pending_tasks
                if i in failed_indices and not is_valid_segment_file(p)
            ]
            failed_indices = []
            if tail_tasks:
                log(f"[i] {len(tail_tasks)} parça için seri son doğrulama başlatılıyor...")
                time.sleep(0.9)
                with ThreadPoolExecutor(max_workers=1) as tail_executor:
                    tail_futures = {
                        tail_executor.submit(
                            self.download_segment_file,
                            url,
                            headers,
                            path,
                            max_retries=6,
                            fallback_host=fallback_host,
                            segment_index=idx,
                        ): (idx, path)
                        for idx, url, path in tail_tasks
                    }
                    for future in as_completed(tail_futures):
                        idx, path = tail_futures[future]
                        try:
                            success, b_down = future.result()
                            if success or is_valid_segment_file(path):
                                completed_count += 1
                                total_bytes += b_down
                            else:
                                failed_indices.append(idx)
                        except Exception:
                            logger.warning(
                                "Segment final verification failed: index=%s url=%s",
                                idx,
                                original_pending_urls.get(idx, "")[:160],
                                exc_info=True,
                            )
                            if not is_valid_segment_file(path):
                                failed_indices.append(idx)

                        if progress_callback:
                            progress_callback(completed_count, len(segment_tasks), total_bytes)

        return completed_count, total_bytes, failed_indices

    def _download_stream_curl_async(self, pending_tasks, headers, thread_count,
                                   base_completed=0, base_bytes=0, total_tasks_len=0,
                                   progress_callback=None, log_callback=None):
        """
        libcurl tabanlı HTTP/2 Multiplexing motoru.
        Uzun akışlarda CDN ve Cloudflare Worker tıkanmasını önlemek için paralel oturum grupları (Rotating Batched Sessions)
        kullanarak tek bağlantı kilitlenmelerini sıfırlar ve maksimum hat hızına (5-15 MB/s) ulaşır.
        """
        import asyncio

        comp_count = [0]
        bytes_down = [0]
        failed_ids = []
        lock = threading.Lock()

        aes_key = None
        aes_iv = None
        aes_media_sequence = 0
        req_headers = dict(headers or {})
        if isinstance(headers, dict):
            aes_key = headers.get("aes_key")
            aes_iv = headers.get("aes_iv")
            aes_media_sequence = headers.get("aes_media_sequence", 0)
            if any(str(k).lower() in _INTERNAL_STREAM_HEADER_KEYS for k in headers):
                req_headers = {
                    k: v for k, v in headers.items()
                    if str(k).lower() not in _INTERNAL_STREAM_HEADER_KEYS
                }

        concurrency = min(12, max(6, thread_count // 2 if thread_count > 12 else thread_count))
        batch_size = 32

        async def _run():
            initial_sem_permits = 6 if self.is_turbo_boosted() else 2
            batch_sem = asyncio.Semaphore(initial_sem_permits)  # Eşzamanlı taze AsyncSession oturumu
            boosted_expanded = [self.is_turbo_boosted()]

            async def _process_batch(batch):
                if self.cancel_event.is_set():
                    return
                # Video bittiğinde veya Turbo Boost tetiklendiğinde oturum havuzunu anında genişlet
                if self.is_turbo_boosted() and not boosted_expanded[0]:
                    boosted_expanded[0] = True
                    for _ in range(4):
                        batch_sem.release()

                async with batch_sem:
                    eff_concurrency = min(32, max(16, thread_count)) if self.is_turbo_boosted() else concurrency
                    sem = asyncio.Semaphore(eff_concurrency)
                    async with c_AsyncSession(impersonate="chrome124", max_clients=eff_concurrency) as sess:
                        sess.headers.update(req_headers)

                        async def _fetch(idx, u, p):
                            if self.cancel_event.is_set():
                                return
                            if is_valid_segment_file(p):
                                with lock:
                                    comp_count[0] += 1
                                    bytes_down[0] += os.path.getsize(p)
                                    if progress_callback:
                                        tot_show = total_tasks_len if total_tasks_len > 0 else len(pending_tasks)
                                        progress_callback(base_completed + comp_count[0], tot_show, base_bytes + bytes_down[0])
                                return
                            async with sem:
                                for attempt in range(1, 4):
                                    if self.cancel_event.is_set():
                                        return
                                    try:
                                        r = await sess.get(u, timeout=10)
                                        if r.status_code == 200 and len(r.content) > 0:
                                            raw = r.content
                                            # M3U8 / HTML validation
                                            _peek = raw[:16]
                                            if _peek.startswith((b"#EXTM3U", b"#EXT-X", b"<!DOCTYPE", b"<html", b"<HTML")):
                                                with lock:
                                                    failed_ids.append(idx)
                                                return

                                            if aes_key:
                                                try:
                                                    crypto_sequence = int(aes_media_sequence) + int(idx)
                                                except (TypeError, ValueError):
                                                    crypto_sequence = idx
                                                decrypted = decrypt_hls_segment(raw, aes_key, aes_iv, crypto_sequence)
                                                if decrypted is None:
                                                    logger.warning("Segment cozulemedi (async), atlaniyor: %s", u[:120])
                                                    with lock:
                                                        failed_ids.append(idx)
                                                    return
                                                raw = decrypted

                                            with open(p, "wb") as f:
                                                f.write(raw)

                                            with lock:
                                                comp_count[0] += 1
                                                bytes_down[0] += len(raw)
                                                if progress_callback:
                                                    tot_show = total_tasks_len if total_tasks_len > 0 else len(pending_tasks)
                                                    progress_callback(base_completed + comp_count[0], tot_show, base_bytes + bytes_down[0])
                                            return
                                    except Exception:
                                        await asyncio.sleep(0.08)

                                with lock:
                                    failed_ids.append(idx)

                        tasks = [_fetch(i, u, p) for i, u, p in batch]
                        await asyncio.gather(*tasks)

            for batch_start in range(0, len(pending_tasks), batch_size):
                if self.cancel_event.is_set():
                    break
                batch = pending_tasks[batch_start:batch_start + batch_size]
                await _process_batch(batch)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        return comp_count[0], bytes_down[0], failed_ids



    def download_direct_file(self, url, output_filepath, headers=None, custom_headers=None, thread_count=16,
                             progress_callback=None, log_callback=None, status_callback=None):
        """
        Doğrudan MP4 / MKV / Video dosyalarını yüksek hızlı çoklu parçalı (Parallel Range Chunk) veya stream olarak indirir.
        Hata durumunda otomatik olarak tek kanallı akış moduna (single-stream fallback) geçerek indirmeyi garantiye alır.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        def set_status(text):
            if status_callback:
                status_callback(text)

        self.reset_cancel()
        self.is_running = True
        incoming_headers = dict(headers or {})
        if custom_headers:
            incoming_headers.update(custom_headers)

        try:
            set_status("Doğrudan Dosya Bağlantısı Kuruluyor...")
            default_hdrs = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
            default_hdrs.update(incoming_headers)
            headers = default_hdrs

            out_dir = os.path.dirname(output_filepath)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            log(f"[Direct MP4] Test ediliyor: {url[:80]}...")
            r_head = None
            c_session = None
            use_curl_cffi = False

            def close_direct_probe():
                nonlocal c_session
                _close_response(r_head)
                if c_session is not None:
                    try:
                        c_session.close()
                    except Exception:
                        logger.debug("download_direct_file(): curl probe session could not close", exc_info=True)
                    c_session = None

            # 1. Standart requests oturumu ile dene (Hızlı 3s kontrol)
            for probe_timeout in (3, 10):
                try:
                    r_head = self._session.get(
                        url,
                        headers=headers,
                        stream=True,
                        timeout=probe_timeout,
                    )
                    if r_head.status_code in (200, 206):
                        break
                    _close_response(r_head)
                    r_head = None
                except Exception:
                    logger.debug("Direct probe with requests failed: %s", url, exc_info=True)
                    _close_response(r_head)
                    r_head = None

            # 2. Standart istek başarısız ise curl_cffi (Chrome 124 TLS Taklidi) ile dene (Hızlı 3s kontrol)
            if r_head is None and c_requests:
                try:
                    c_session = c_requests.Session(impersonate="chrome124")
                    r_head_c = c_session.get(url, headers=headers, stream=True, timeout=3)
                    if r_head_c.status_code in (200, 206):
                        r_head = r_head_c
                        use_curl_cffi = True
                    else:
                        _close_response(r_head_c)
                except Exception:
                    logger.debug("[engine.py:1652] download_direct_file() sessiz istisna yutuldu", exc_info=True)

            if r_head is None or r_head.status_code not in (200, 206):
                close_direct_probe()
                # 3. HTTP 403 / WAF Engeli durumunda KULLANICIYA HATA VERMEDEN ÖNCE yt-dlp dene!
                log("[i] 🔄 Doğrudan indirme HTTP 403 ile engellendi. Kullanıcıya hata gösterilmeden Evrensel Medya Motoru (yt-dlp) devreye alınıyor...")
                try:
                    out_dir_target = out_dir or os.path.dirname(output_filepath) or "."
                    def ytdl_prog(down, tot, spd, ratio):
                        if progress_callback:
                            progress_callback(down, tot or down, down, spd)

                    ok_yt, res_yt = self.download_youtube_media(
                        media_url=url,
                        output_dir=out_dir_target,
                        format_choice="best",
                        progress_callback=ytdl_prog,
                        log_callback=log
                    )
                    if ok_yt and os.path.exists(res_yt):
                        set_status("Tamamlandı")
                        log(f"[+] Evrensel motor ile video başarıyla indirildi: {os.path.basename(res_yt)}")
                        if res_yt != output_filepath:
                            try:
                                if os.path.exists(output_filepath):
                                    os.remove(output_filepath)
                                os.rename(res_yt, output_filepath)
                                return True, output_filepath
                            except Exception:
                                return True, res_yt
                        return True, res_yt
                except Exception as ex_yt:
                    log(f"[!] Evrensel motor yedekleme notu: {ex_yt}")

                status_code = getattr(r_head, 'status_code', 'Bilinmiyor')
                return False, f"Sunucu hatası: HTTP {status_code}. Site Cloudflare/IP kilidi uyguluyor olabilir."

            total_bytes = int(r_head.headers.get("Content-Length", 0))
            accept_ranges = r_head.headers.get("Accept-Ranges", "").lower() == "bytes"

            # ─── FIX 1: Content-Type Doğrulama ─────────────────────────────────────
            # Sunucu HTML sayfası, M3U8 playlist veya metin döndürdüyse kaydetme
            content_type = r_head.headers.get("Content-Type", "").lower()
            _INVALID_CONTENT_TYPES = ("text/html", "application/xhtml", "text/xml",
                                      "application/xml", "application/json",
                                      "application/x-mpegurl", "application/vnd.apple.mpegurl",
                                      "audio/mpegurl", "audio/x-mpegurl")
            if any(bad in content_type for bad in _INVALID_CONTENT_TYPES):
                log(f"[!] ❌ Sunucu video yerine '{content_type}' döndürdü — dosya kaydedilmedi.")
                close_direct_probe()
                if "mpegurl" in content_type or "m3u8" in content_type.lower():
                    log("[i] 💡 URL bir M3U8 playlist'i. Segment indirme motoruna yönlendiriliyor...")
                    return False, f"M3U8_REDIRECT:{url}"
                return False, f"Sunucu geçersiz içerik döndürdü ({content_type}). Bu URL bir HTML sayfası veya metin dosyası."

            # Boyut sıfırsa ilk birkaç byte'ı okuyup içerik kontrolü yap
            if total_bytes < 1000 or total_bytes == 0:
                try:
                    peek = r_head.iter_content(chunk_size=64).__next__()
                    if peek.startswith(b"#EXTM3U"):
                        log("[!] ❌ Yanıt içeriği M3U8 playlist — dosya kaydedilmedi.")
                        close_direct_probe()
                        return False, f"M3U8_REDIRECT:{url}"
                    if peek.startswith(b"<!DOCTYPE") or peek.startswith(b"<html"):
                        log("[!] ❌ Yanıt içeriği HTML sayfası — dosya kaydedilmedi.")
                        close_direct_probe()
                        return False, "Sunucu HTML sayfası döndürdü. Video URL'si bulunamadı."
                except Exception:
                    logger.debug("[engine.py:1716] download_direct_file() sessiz istisna yutuldu", exc_info=True)
            # ────────────────────────────────────────────────────────────────────────

            log(f"[Direct MP4] Boyut: {total_bytes / (1024 * 1024):.2f} MB (Parçalı Range Desteği: {accept_ranges}, TLS Bypass: {use_curl_cffi})")

            # Baslik yoklamasi icin acilan akis yanitini kapat; aksi halde soket
            # indirme boyunca havuzda tutulu kalir.
            close_direct_probe()

            start_time = time.time()
            downloaded_bytes = [0]
            parallel_success = False

            # --- PARALEL RANGE (FİBER HIZ & KESİNTİSİZ RESUME) MODU ---
            if accept_ranges and total_bytes > 5 * 1024 * 1024 and thread_count > 1:
                set_status("Çok Parçalı İndiriliyor (Fiber Hız & Resume Koruması)...")
                # CDN kilitlenmelerini önleyen dengeli 8 iş parçacığı
                num_chunks = min(max(thread_count, 4), 8)
                chunk_size = total_bytes // num_chunks
                base_temp = os.path.join(tempfile.gettempdir(), ".vdp_temp")
                os.makedirs(base_temp, exist_ok=True)

                # Deterministik klasör adı: Parça sayısı, URL ve dosya adı karmasıyla sabitlenir
                url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
                safe_stem = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(output_filepath))[0])[:25]
                temp_dir = os.path.join(base_temp, f".temp_direct_{safe_stem}_{num_chunks}p_{url_hash}")
                os.makedirs(temp_dir, exist_ok=True)

                try:
                    from engine_core.recovery import write_recovery_state
                    write_recovery_state(temp_dir, {
                        "url": url,
                        "title": os.path.splitext(os.path.basename(output_filepath))[0],
                        "output_filepath": output_filepath,
                        "total_segments": num_chunks,
                        "downloaded_segments": 0,
                        "timestamp": time.time(),
                        "custom_headers": custom_headers or {},
                        "is_multi_audio": False,
                        "raw_url": url,
                    })
                except Exception:
                    logger.debug("Direct download recovery state could not be written", exc_info=True)

                tasks = []
                part_files = []
                part_bytes_downloaded = {}
                part_lock = threading.Lock()

                for i in range(num_chunks):
                    s_byte = i * chunk_size
                    e_byte = (total_bytes - 1) if (i == num_chunks - 1) else ((i + 1) * chunk_size - 1)
                    p_path = os.path.join(temp_dir, f"part_{i:03d}.tmp")
                    part_files.append(p_path)
                    part_len = e_byte - s_byte + 1
                    existing_len = os.path.getsize(p_path) if os.path.exists(p_path) else 0
                    if existing_len > part_len:
                        try:
                            os.remove(p_path)
                        except OSError:
                            logger.debug("[engine.py:download_direct_file] corrupted part silinemedi", exc_info=True)
                        existing_len = 0
                    part_bytes_downloaded[i] = existing_len
                    tasks.append((i, s_byte, e_byte, p_path))

                # Önceden inmiş parçaları tara ve ilerlemeyi anında hesapla
                initial_down = sum(part_bytes_downloaded.values())
                if initial_down > 0:
                    log(f"[+] 💾 Önceki indirmeden {initial_down / (1024 * 1024):.1f} MB parça verisi bulundu; kaldığı yerden devam ediliyor!")
                    if progress_callback:
                        progress_callback(initial_down, total_bytes, initial_down, 0)

                def report_part_progress(part_idx, chunk_len):
                    with part_lock:
                        part_bytes_downloaded[part_idx] += chunk_len
                        tot_down = min(total_bytes, sum(part_bytes_downloaded.values()))
                        elapsed = max(0.001, time.time() - start_time)
                        spd = tot_down / elapsed
                        if progress_callback:
                            progress_callback(tot_down, total_bytes, tot_down, spd)

                def dl_part(idx, s_byte, e_byte, p_path):
                    part_len = e_byte - s_byte + 1
                    # 1. Zaten diskte tam olan parçaları doğrudan başarılı say
                    if os.path.exists(p_path) and os.path.getsize(p_path) == part_len:
                        with part_lock:
                            part_bytes_downloaded[idx] = part_len
                        return True

                    for attempt in range(5):
                        if self.cancel_event.is_set():
                            return False

                        existing_size = os.path.getsize(p_path) if os.path.exists(p_path) else 0
                        if existing_size >= part_len:
                            with part_lock:
                                part_bytes_downloaded[idx] = part_len
                            return True

                        curr_s_byte = s_byte + existing_size
                        h = dict(headers)
                        h["Range"] = f"bytes={curr_s_byte}-{e_byte}"

                        resp = None
                        try:
                            open_mode = "ab" if existing_size > 0 else "wb"
                            resp = self._session.get(url, headers=h, stream=True, timeout=(15, 60))

                            if resp.status_code != 206:
                                logger.warning(
                                    "[engine.py:download_direct_file] Range istegi %s dondu; "
                                    "paralel parca biriktirme iptal ediliyor.",
                                    resp.status_code,
                                )
                                return False

                            content_range = resp.headers.get("Content-Range", "")
                            range_match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range.strip())
                            if not range_match or (
                                int(range_match.group(1)) != curr_s_byte
                                or int(range_match.group(2)) != e_byte
                            ):
                                logger.warning(
                                    "[engine.py:download_direct_file] Gecersiz Content-Range: %r",
                                    content_range,
                                )
                                return False

                            with open(p_path, open_mode) as f_out:
                                for chunk in resp.iter_content(chunk_size=262144):
                                    if self.cancel_event.is_set():
                                        return False
                                    if chunk:
                                        f_out.write(chunk)
                                        report_part_progress(idx, len(chunk))

                            if os.path.exists(p_path) and os.path.getsize(p_path) == part_len:
                                with part_lock:
                                    part_bytes_downloaded[idx] = part_len
                                return True
                        except Exception as e_part:
                            logger.debug(f"[engine.py:download_direct_file] parça {idx} deneme {attempt+1} uyarısı: {e_part}", exc_info=True)
                            time.sleep(0.5)
                        finally:
                            if resp is not None:
                                try:
                                    resp.close()
                                except Exception:
                                    logger.debug("[engine.py:download_direct_file] resp.close() hatasi", exc_info=True)
                    return False

                with ThreadPoolExecutor(max_workers=num_chunks) as exec_pool:
                    futs = {idx: exec_pool.submit(dl_part, idx, s, e, p) for idx, s, e, p in tasks}
                    results = {idx: fut.result() for idx, fut in futs.items()}

                    # Eksik veya hata alan parçaları kurtarma döngüsü
                    for retry_round in range(5):
                        failed_parts = [t for t in tasks if not results.get(t[0])]
                        if not failed_parts or self.cancel_event.is_set():
                            break
                        log(f"[!] {len(failed_parts)} parça tamamlanıyor (Kaldığı yerden, Tur {retry_round+1})...")
                        retry_futs = {t[0]: exec_pool.submit(dl_part, t[0], t[1], t[2], t[3]) for t in failed_parts}
                        for p_idx, r_fut in retry_futs.items():
                            results[p_idx] = r_fut.result()

                if self.cancel_event.is_set():
                    if self.cleanup_on_cancel:
                        for p in part_files:
                            if os.path.exists(p):
                                try:
                                    os.remove(p)
                                except OSError:
                                    logger.debug("[engine.py:1835] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                        if os.path.exists(temp_dir):
                            try:
                                shutil.rmtree(temp_dir, ignore_errors=True)
                            except Exception:
                                logger.debug("[engine.py:1840] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                    set_status("İptal Edildi" if self.cleanup_on_cancel else "DURAKLATILDI")
                    return False, "İşlem iptal edildi." if self.cleanup_on_cancel else "İndirme duraklatıldı."

                if all(results.values()):
                    set_status("Dosya Birleştiriliyor...")
                    with open(output_filepath, "wb") as f_final:
                        for p in part_files:
                            if os.path.exists(p):
                                with open(p, "rb") as f_part:
                                    shutil.copyfileobj(f_part, f_final, length=1048576)
                                try:
                                    os.remove(p)
                                except OSError:
                                    logger.debug("[engine.py:1854] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except OSError:
                        logger.debug("[engine.py:1858] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                    parallel_success = True

                if not parallel_success:
                    # Kurtarma turlari da yetmedi: tek kanalli moda gecmeden once
                    # yarim inen parca dosyalarini ve gecici klasoru mutlaka birak.
                    failed_n = sum(1 for ok in results.values() if not ok)
                    log(f"[!] {failed_n} parça kurtarılamadı; tek kanallı akış moduna geçiliyor.")
                    cleanup_filesystem_path(temp_dir)

            # --- TEK KANALLI AKIŞ MODU (FALLBACK / NORMAL) ---
            if not parallel_success:
                set_status("Doğrudan Akış İndiriliyor...")
                downloaded_bytes[0] = 0
                single_ok = False
                if not use_curl_cffi:
                    try:
                        with self._session.get(url, headers=headers, stream=True, timeout=30) as r_stream:
                            if r_stream.status_code in (200, 206):
                                expected_stream_bytes = int(r_stream.headers.get("Content-Length", 0) or 0)
                                with open(output_filepath, "wb") as f_final:
                                    for chunk in r_stream.iter_content(chunk_size=131072):
                                        if self.cancel_event.is_set():
                                            if self.cleanup_on_cancel and os.path.exists(output_filepath):
                                                try:
                                                    os.remove(output_filepath)
                                                except OSError:
                                                    logger.debug("[engine.py:1877] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                                            set_status("İptal Edildi" if self.cleanup_on_cancel else "DURAKLATILDI")
                                            return False, "İşlem iptal edildi." if self.cleanup_on_cancel else "İndirme duraklatıldı."
                                        if chunk:
                                            f_final.write(chunk)
                                            downloaded_bytes[0] += len(chunk)
                                            elapsed = max(0.001, time.time() - start_time)
                                            spd = downloaded_bytes[0] / elapsed
                                            if progress_callback:
                                                progress_callback(downloaded_bytes[0], total_bytes or downloaded_bytes[0], downloaded_bytes[0], spd)
                                actual_stream_bytes = os.path.getsize(output_filepath) if os.path.exists(output_filepath) else 0
                                single_ok = actual_stream_bytes > 0 and (
                                    expected_stream_bytes <= 0
                                    or actual_stream_bytes == expected_stream_bytes
                                )
                    except Exception:
                        logger.warning("Direct single-stream requests download failed: %s", url, exc_info=True)
                        single_ok = False
                        if os.path.exists(output_filepath):
                            try:
                                os.remove(output_filepath)
                            except OSError:
                                logger.debug("Incomplete direct output could not be removed", exc_info=True)

                if not single_ok and c_requests:
                    r_stream = None
                    try:
                        r_stream = c_requests.get(url, headers=headers, stream=True, timeout=30, impersonate="chrome124")
                        if r_stream.status_code in (200, 206):
                            expected_stream_bytes = int(r_stream.headers.get("Content-Length", 0) or 0)
                            downloaded_bytes[0] = 0
                            with open(output_filepath, "wb") as f_final:
                                for chunk in r_stream.iter_content(chunk_size=131072):
                                    if self.cancel_event.is_set():
                                        if self.cleanup_on_cancel and os.path.exists(output_filepath):
                                            try:
                                                os.remove(output_filepath)
                                            except OSError:
                                                logger.debug("[engine.py:1902] download_direct_file() sessiz istisna yutuldu", exc_info=True)
                                        set_status("İptal Edildi" if self.cleanup_on_cancel else "DURAKLATILDI")
                                        return False, "İşlem iptal edildi." if self.cleanup_on_cancel else "İndirme duraklatıldı."
                                    if chunk:
                                        f_final.write(chunk)
                                        downloaded_bytes[0] += len(chunk)
                                        elapsed = max(0.001, time.time() - start_time)
                                        spd = downloaded_bytes[0] / elapsed
                                        if progress_callback:
                                            progress_callback(downloaded_bytes[0], total_bytes or downloaded_bytes[0], downloaded_bytes[0], spd)
                            actual_stream_bytes = os.path.getsize(output_filepath) if os.path.exists(output_filepath) else 0
                            single_ok = actual_stream_bytes > 0 and (
                                expected_stream_bytes <= 0
                                or actual_stream_bytes == expected_stream_bytes
                            )
                    except Exception as e_cffi:
                        log(f"[!] curl_cffi akış uyarısı: {e_cffi}")
                        logger.warning("Direct single-stream curl download failed: %s", url, exc_info=True)
                        single_ok = False
                        if os.path.exists(output_filepath):
                            try:
                                os.remove(output_filepath)
                            except OSError:
                                logger.debug("Incomplete curl direct output could not be removed", exc_info=True)
                    finally:
                        _close_response(r_stream)

            if (parallel_success or single_ok) and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
                final_mb = os.path.getsize(output_filepath) / (1024 * 1024)
                set_status("Tamamlandı")
                log(f"[+] Doğrudan video başarıyla indirildi: {final_mb:.2f} MB")
                return True, output_filepath
            else:
                if os.path.exists(output_filepath):
                    try:
                        os.remove(output_filepath)
                    except OSError:
                        logger.debug("Invalid direct output could not be removed", exc_info=True)
                return False, "Dosya indirilemedi (0 bayt)."

        except Exception as e:
            logger.exception("Direct file download failed: %s", url)
            set_status(f"Hata: {str(e)[:40]}")
            return False, str(e)
        finally:
            self.is_running = False




__all__ = ["SegmentDownloaderMixin"]
