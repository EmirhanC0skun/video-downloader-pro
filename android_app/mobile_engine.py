import os
import sys
import re
import time
import base64
import json as jsonlib
import subprocess
import threading
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from requests.cookies import RequestsCookieJar
from requests.structures import CaseInsensitiveDict

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(APP_DIR, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging

        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("mobile_engine")

# Modül yükleme: Doğrudan veya core paketinden
VideoDownloadEngine = None
get_ffmpeg_path = None
parse_curl_command = None
resolve_film_page = None
scan_series_episodes_func = None
load_history = None
add_history_entry = None
_init_error = None

# Önce doğrudan aynı dizinden veya core paketinden yüklemeyi dene
for loader in [
    lambda: (__import__("core.engine", fromlist=["VideoDownloadEngine", "get_ffmpeg_path", "parse_curl_command"]),
             __import__("core.extractor", fromlist=["resolve_film_page", "scan_series_episodes"]),
             __import__("core.history", fromlist=["load_history", "add_history_entry"])),
    lambda: (__import__("engine", fromlist=["VideoDownloadEngine", "get_ffmpeg_path", "parse_curl_command"]),
             __import__("extractor", fromlist=["resolve_film_page", "scan_series_episodes"]),
             __import__("history", fromlist=["load_history", "add_history_entry"]))
]:
    try:
        m_eng, m_ext, m_hist = loader()
        VideoDownloadEngine = getattr(m_eng, "VideoDownloadEngine", None)
        get_ffmpeg_path = getattr(m_eng, "get_ffmpeg_path", None)
        parse_curl_command = getattr(m_eng, "parse_curl_command", None)
        resolve_film_page = getattr(m_ext, "resolve_film_page", None)
        scan_series_episodes_func = getattr(m_ext, "scan_series_episodes", None)
        load_history = getattr(m_hist, "load_history", None)
        add_history_entry = getattr(m_hist, "add_history_entry", None)
        if VideoDownloadEngine and resolve_film_page:
            break
    except Exception as ex:
        _init_error = str(ex)


_android_page = None
_android_media_service = None


class AndroidNativeResponse:
    """Small requests-compatible response backed by Android's native HTTP stack."""

    def __init__(self, payload):
        self.status_code = int(payload.get("status") or 0)
        self.url = str(payload.get("url") or "")
        raw_headers = payload.get("headers") or {}
        self.headers = CaseInsensitiveDict()
        self._header_values = {}
        for name, values in raw_headers.items():
            value_list = values if isinstance(values, list) else [values]
            clean_values = [str(value) for value in value_list]
            self._header_values[str(name).lower()] = clean_values
            self.headers[str(name)] = ", ".join(clean_values)
        try:
            self.content = base64.b64decode(payload.get("body_base64") or "", validate=True)
        except (ValueError, TypeError):
            self.content = b""
        self.encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        charset_match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
        if charset_match:
            self.encoding = charset_match.group(1).strip("\"'")

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    @property
    def text(self):
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def json(self):
        return jsonlib.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(
                f"{self.status_code} response for {self.url}",
                response=self,
            )

    def iter_content(self, chunk_size=1):
        size = max(1, int(chunk_size or 1))
        for offset in range(0, len(self.content), size):
            yield self.content[offset:offset + size]

    def close(self):
        return None


class AndroidNativeSession:
    """Subset of requests.Session using Dart HttpClient for Android TLS."""

    def __init__(self, requester):
        self._requester = requester
        self.headers = CaseInsensitiveDict()
        self.cookies = RequestsCookieJar()
        self.verify = True

    @staticmethod
    def _timeout_seconds(timeout):
        if isinstance(timeout, (tuple, list)):
            values = [float(value) for value in timeout if value is not None]
            return max(values) if values else 15.0
        return float(timeout or 15.0)

    def request(
        self,
        method,
        url,
        headers=None,
        params=None,
        data=None,
        json=None,
        timeout=None,
        allow_redirects=True,
        **_kwargs,
    ):
        if params:
            parsed = urlsplit(str(url))
            extra_query = urlencode(params, doseq=True)
            merged_query = "&".join(part for part in (parsed.query, extra_query) if part)
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, merged_query, parsed.fragment))

        request_headers = CaseInsensitiveDict(self.headers)
        request_headers.update(headers or {})
        cookie_header = requests.utils.dict_from_cookiejar(self.cookies)
        if cookie_header and "Cookie" not in request_headers:
            request_headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in cookie_header.items()
            )

        body = ""
        if json is not None:
            body = jsonlib.dumps(json, ensure_ascii=False, separators=(",", ":"))
            request_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            body = urlencode(data, doseq=True) if isinstance(data, (dict, list, tuple)) else str(data)
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

        timeout_seconds = self._timeout_seconds(timeout)
        payload = self._requester({
            "method": str(method).upper(),
            "url": str(url),
            "headers": dict(request_headers),
            "body": body,
            "timeout_seconds": timeout_seconds,
            "follow_redirects": bool(allow_redirects),
            "max_response_bytes": 8 * 1024 * 1024,
        })
        if not isinstance(payload, dict):
            raise requests.RequestException("Android native HTTP bridge returned no response")
        response = AndroidNativeResponse(payload)
        for raw_cookie in response._header_values.get("set-cookie", []):
            parsed_cookie = SimpleCookie()
            try:
                parsed_cookie.load(raw_cookie)
            except CookieError:
                continue
            for morsel in parsed_cookie.values():
                self.cookies.set(morsel.key, morsel.value)
        return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        return None


def _native_http_request(payload):
    future = _run_android_task("http_request", payload)
    if future is None:
        raise requests.RequestException("Android native HTTP bridge is unavailable")
    timeout = float(payload.get("timeout_seconds") or 15) + 10
    return future.result(timeout=timeout) if hasattr(future, "result") else future


def _create_android_http_session():
    if _android_page is None or _android_media_service is None:
        return None
    return AndroidNativeSession(_native_http_request)


def configure_android_services(page, controller=None):
    """Bind native Android services to the Flet page once at application start."""
    global _android_page, _android_media_service
    _android_page = page
    try:
        from vdpro_android_bridge import AndroidMediaService

        _android_media_service = AndroidMediaService()
        page.services.append(_android_media_service)
    except (ImportError, AttributeError) as exc:
        logger.warning("Android native media bridge could not be initialized: %s", exc)
        return None

    if controller is not None:
        try:
            import flet as ft

            storage_paths = ft.StoragePaths()
            page.services.append(storage_paths)

            async def configure_storage():
                try:
                    base_dir = await storage_paths.get_application_documents_directory()
                    if base_dir:
                        controller.set_download_dir(os.path.join(base_dir, "VideoDownloader"))
                except (OSError, RuntimeError, AttributeError):
                    logger.warning("Android application storage could not be resolved", exc_info=True)

            page.run_task(configure_storage)
        except (ImportError, AttributeError):
            logger.warning("Flet StoragePaths service is unavailable", exc_info=True)
    return _android_media_service


def _run_android_task(method_name, *args, **kwargs):
    if _android_page is None or _android_media_service is None:
        return None

    async def invoke():
        try:
            method = getattr(_android_media_service, method_name)
            return await method(*args, **kwargs)
        except (OSError, RuntimeError, AttributeError, ValueError):
            logger.warning("Android service call failed: %s", method_name, exc_info=True)
            return False

    return _android_page.run_task(invoke)


def scan_media_file(filepath: str):
    """Publish a completed video to Android MediaStore/Gallery."""
    if not filepath or not os.path.exists(filepath):
        return None
    if _android_page is None or _android_media_service is None:
        return None

    async def publish_and_notify():
        try:
            published = await _android_media_service.publish_video(filepath)
            filename = os.path.basename(filepath)
            message = (
                f"{filename} galeriye kaydedildi."
                if published
                else f"{filename} indirildi; galeriye eklenemedi."
            )
            await _android_media_service.finish_download(
                filename, bool(published), message
            )
            return bool(published)
        except (OSError, RuntimeError, AttributeError, ValueError):
            logger.warning("Android MediaStore publish failed", exc_info=True)
            return False

    return _android_page.run_task(publish_and_notify)


def update_download_notification(
    title: str,
    progress_ratio: float = 0.0,
    speed_str: str = "",
    eta_str: str = "",
    is_completed: bool = False,
    is_failed: bool = False,
):
    """Update the native foreground-service notification."""
    clean_title = (title or "Video indiriliyor")[:80]
    if is_completed or is_failed:
        message = (
            "Dosya galeriye kaydedildi."
            if is_completed
            else "İndirme işlemi sonlandırıldı."
        )
        return _run_android_task(
            "finish_download", clean_title, is_completed and not is_failed, message
        )
    pct = max(0, min(100, int((progress_ratio or 0.0) * 100)))
    if pct == 0:
        return _run_android_task("start_download", clean_title)
    return _run_android_task(
        "update_download", clean_title, pct, speed_str or "", eta_str or ""
    )


def acquire_android_wakelock():
    """The native foreground service owns its bounded CPU/Wi-Fi locks."""
    return None


def release_android_wakelock():
    """The native foreground service releases locks when it stops."""
    return None


def request_android_permissions():
    """Request notification and battery-optimization access through Android UI."""
    return _run_android_task("request_permissions")


def send_mobile_notification(title: str, message: str):
    """Show a native completion notification."""
    return _run_android_task("finish_download", title, True, message)


def get_default_mobile_download_dir():
    """
    Android Galeri ve Medya dizinlerini (DCIM / Movies) birincil hedef olarak belirler.
    Böylece indirilen tüm videolar Samsung Galeri, Google Fotoğraflar ve Video Oynatıcılarda anında görünür.
    """
    candidates = [
        os.path.join(os.path.expanduser("~"), "VideoDownloader"),
        os.path.join(os.environ.get("TMPDIR", ""), "VideoDownloader"),
    ]
    for d in candidates:
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, f".test_perm_{int(time.time()*1000)}.tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return d
        except Exception:
            continue

    fallback = os.path.join(os.path.expanduser("~"), "VideoDownloader")
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        logger.debug("[android_app/mobile_engine.py:238] get_default_mobile_download_dir() sessiz istisna yutuldu", exc_info=True)
    return fallback


def translate_user_friendly_error(err_msg: str) -> str:
    """
    Teknik istisnaları ve ağ kodlarını kullanıcı dostu, anlaşılır Türkçe önerilere çevirir.
    """
    err_lower = str(err_msg).lower()
    if "403" in err_lower or "forbidden" in err_lower:
        return "🛡️ Sunucu erişim koruması (403).\nÇözüm: Alternatif oynatıcıyı seçin veya Tarayıcı Çerezleri/Oturumu seçeneğini açarak tekrar deneyin."
    elif "timeout" in err_lower or "timed out" in err_lower or "offline" in err_lower or "11001" in err_lower or "getaddrinfo" in err_lower:
        return "🌐 Sunucuya bağlanılamadı veya zaman aşımına uğradı.\nÇözüm: İnternet bağlantınızı veya film sitesinin adresini kontrol edin."
    elif "segment" in err_lower and ("tespit" in err_lower or "bulunamadı" in err_lower or "format" in err_lower or "geçersiz" in err_lower):
        return "⚠️ Akış parçaları tespit edilemedi.\nÇözüm: Sayfadaki diğer oynatıcı seçeneklerini deneyin veya cURL komutuyla içe aktarın."
    elif "permission" in err_lower or "erişim engellendi" in err_lower or "winerror 5" in err_lower:
        return "🔒 Dosya yazma izni engellendi.\nÇözüm: Hedef dosyanın veya klasörün başka bir programda açık olmadığından emin olun."
    elif "unsupported url" in err_lower or "no video source" in err_lower or "bulunamadı" in err_lower or "kaynak bulunamadı" in err_lower:
        return "ℹ️ Sayfada oynatılabilir video akışı bulunamadı.\nÇözüm: Bölüm henüz siteye yüklenmemiş olabilir veya farklı bir kaynak seçiniz."
    return str(err_msg)


class MobileDownloadController:
    """
    Flet Material 3 mobil arayüzü ile VideoDownloadEngine arasındaki reaktif köprü.
    Film, YouTube, Dizi Kuyruğu ve Medya Dönüştürücü operasyonlarını yönetir.
    """
    def __init__(self):
        self.engine = VideoDownloadEngine() if VideoDownloadEngine else None
        self.download_dir = get_default_mobile_download_dir()
        self.active_download_title = ""
        self.is_downloading = False
        self.is_paused = False
        self.state = "IDLE"  # IDLE, DOWNLOADING, PAUSED, COMPLETED, CANCELLED, ERROR
        self.start_time = 0.0
        self.elapsed_accumulated = 0.0
        self.speed_threads = 4  # Mobil icin varsayilan dengeli hiz profili

        # Arayuz kancalari. `switch_tab()` ve durum rozeti bunlari okur;
        # main.py baglamadan once cagrilirsa AttributeError yerine sessiz
        # kalmalari icin burada None olarak kurulurlar.
        self.nav_handler = None
        self.status_handler = None
        self.active_tab_index = 0

        # Kuyruk ve Toplu Indirme Durumlari
        self.queue_items = []
        self.is_queue_running = False
        self.is_queue_paused = False
        self.current_queue_item_id = None
        self.queue_thread = None
        self.queue_callback = None

    def _emit_status(self):
        """Arayuze durum degisikligini bildirir (ust cubuktaki canli rozet).

        Dinleyici yoksa ya da cizim sirasinda hata alirsa sessiz kalir: durum
        rozetini boyayamamak indirmeyi durdurmamali.
        """
        handler = getattr(self, "status_handler", None)
        if handler is None:
            return
        try:
            handler(self.state)
        except Exception:
            logger.debug("[mobile_engine] status_handler cizim hatasi", exc_info=True)

    def switch_tab(self, tab_index, url=None, auto_resolve=False):
        """
        Herhangi bir ekrandan veya geçmişten diğer sekmeye geçişi ve otomatik URL çözümlemesini tetikler.
        """
        self.active_tab_index = tab_index
        if self.nav_handler:
            self.nav_handler(tab_index, url=url, auto_resolve=auto_resolve)

    def set_download_dir(self, new_dir):
        if os.path.exists(new_dir):
            self.download_dir = new_dir
            return True
        try:
            os.makedirs(new_dir, exist_ok=True)
            self.download_dir = new_dir
            return True
        except Exception:
            return False

    def resolve_media_url(self, url, log_cb=None):
        if not resolve_film_page:
            if log_cb:
                log_cb(f"[!] Medya çözümleyici modülü yüklenemedi: {_init_error or 'Bilinmeyen Hata'}")
            return None
        try:
            return resolve_film_page(
                url,
                log_callback=log_cb,
                session=_create_android_http_session(),
            )
        except Exception as e:
            try:
                source_host = urlsplit(str(url)).netloc or "unknown-host"
            except ValueError:
                source_host = "invalid-host"
            logger.warning(
                "Android media resolution failed for %s: %s",
                source_host,
                e,
                exc_info=True,
            )
            if log_cb:
                log_cb(f"[!] Çözümleme Hatası: {e}")
            return None

    def extract_social_info(self, media_url, cookies_file=None, log_cb=None):
        """
        YouTube, Instagram, TikTok ve diğer sosyal medya linklerinden dinamik çözünürlükleri ve başlığı sorgular.
        """
        if not self.engine:
            return {"title": "Video", "qualities": ["best", "1080p", "720p", "480p", "360p", "mp3", "m4a"]}
        try:
            cleaned_cfile = os.path.normpath(str(cookies_file).strip().strip('"').strip("'")) if (cookies_file and os.path.exists(os.path.normpath(str(cookies_file).strip().strip('"').strip("'")))) else None
            return self.engine.extract_youtube_info(media_url=media_url, cookies_file=cleaned_cfile, log_callback=log_cb)
        except Exception as e:
            if log_cb:
                log_cb(f"[!] Sosyal Medya Çözümleme Hatası: {e}")
            raise e

    def download_social_media(self, media_url, format_choice="best", cookies_file=None, progress_cb=None, log_cb=None):
        """
        Sosyal medya ve YouTube videolarını seçilen kalitede ve otomatik AAC ses dönüşümü ile indirir.
        """
        if not self.engine:
            return False, "İndirme motoru başlatılamadı."
        self.start_download_session(title=media_url)
        cleaned_cfile = os.path.normpath(str(cookies_file).strip().strip('"').strip("'")) if (cookies_file and os.path.exists(os.path.normpath(str(cookies_file).strip().strip('"').strip("'")))) else None
        return self.engine.download_youtube_media(
            media_url=media_url,
            output_dir=self.download_dir,
            format_choice=format_choice,
            cookies_file=cleaned_cfile,
            progress_callback=progress_cb,
            log_callback=log_cb
        )

    # =========================================================================
    # YAŞAM DÖNGÜSÜ & STATE MACHINE (PAUSE / RESUME / CANCEL)
    # =========================================================================
    def start_download_session(self, title=""):
        self.active_download_title = title
        self.is_downloading = True
        self.is_paused = False
        self.state = "DOWNLOADING"
        self.start_time = time.time()
        self.elapsed_accumulated = 0.0
        self.last_notif_time = 0.0
        acquire_android_wakelock()
        update_download_notification(title, progress_ratio=0.0, speed_str="Başlatılıyor...", eta_str="--:--")
        self._emit_status()
        if self.engine:
            self.engine.reset_cancel()

    def update_live_progress(self, completed, total, speed_bps, ratio, eta_str="--:--"):
        """Canlı indirme ilerlemesini Android bildirim çubuğuna ve UI dinleyicilerine aktarır."""
        now = time.time()
        if ratio >= 1.0 or (now - getattr(self, "last_notif_time", 0.0) >= 1.0):
            self.last_notif_time = now
            spd_mb = f"⚡ {speed_bps/(1024*1024):.2f} MB/s" if speed_bps > 0 else ""
            update_download_notification(
                title=self.active_download_title or "Video İndiriliyor",
                progress_ratio=ratio,
                speed_str=spd_mb,
                eta_str=eta_str
            )

    def finish_download_session(self, success=True, filename=""):
        """İndirme tamamlandığında bildirim çubuğunu günceller ve wakelock kilidini bırakır."""
        self.is_downloading = False
        self.is_paused = False
        self.state = "COMPLETED" if success else "ERROR"
        release_android_wakelock()
        t = filename or self.active_download_title or "Video"
        if success:
            update_download_notification(t, progress_ratio=1.0)
        else:
            update_download_notification(t, is_failed=True)
        self._emit_status()

    def pause_download(self):
        if self.is_downloading and not self.is_paused:
            self.is_paused = True
            self.state = "PAUSED"
            self.elapsed_accumulated += max(0.0, time.time() - self.start_time)
            update_download_notification(self.active_download_title, speed_str="⏸️ Duraklatıldı")
            self._emit_status()
            if self.engine:
                self.engine.pause()
            return True
        return False

    def resume_download(self):
        if self.is_paused:
            self.is_paused = False
            self.state = "DOWNLOADING"
            self.start_time = time.time()
            acquire_android_wakelock()
            update_download_notification(self.active_download_title, speed_str="▶️ Devam Ediliyor...")
            self._emit_status()
            if self.engine:
                self.engine.resume()
            return True
        return False

    def cancel_current_download(self, cleanup=True):
        self.is_downloading = False
        self.is_paused = False
        self.state = "CANCELLED"
        self.start_time = 0.0
        self.elapsed_accumulated = 0.0
        release_android_wakelock()
        update_download_notification(self.active_download_title, is_failed=True)
        self._emit_status()
        if self.engine:
            self.engine.cancel(cleanup=cleanup)

    def get_elapsed_seconds(self):
        if not self.is_downloading and not self.is_paused:
            return 0
        if self.is_paused:
            return int(self.elapsed_accumulated)
        return int(self.elapsed_accumulated + max(0.0, time.time() - self.start_time))

    # =========================================================================
    # DİZİ & TOPLU İNDİRME KUYRUĞU (BATCH / QUEUE ENGINE)
    # =========================================================================
    def add_queue_item(self, title, url, media_type="film", audio_choice=None, resolved_data=None):
        item_id = f"item_{int(time.time() * 1000)}_{len(self.queue_items)}"
        item = {
            "id": item_id,
            "title": title or f"Medya {len(self.queue_items) + 1}",
            "url": url,
            "media_type": media_type,
            "audio_choice": audio_choice,
            "resolved_data": resolved_data,
            "status": "Bekliyor",
            "progress": 0.0,
            "speed": "0.0 MB/s",
            "size": "0.0 MB",
            "out_path": ""
        }
        self.queue_items.append(item)
        return item

    def remove_queue_item(self, item_id):
        if self.current_queue_item_id == item_id and self.is_queue_running:
            self.cancel_queue_item(item_id)
        self.queue_items = [it for it in self.queue_items if it["id"] != item_id]

    def cancel_queue_item(self, item_id):
        """Kuyruktaki tek bir öğeyi iptal eder veya indiriliyorsa motoru durdurur."""
        for it in self.queue_items:
            if it["id"] == item_id:
                it["status"] = "İptal Edildi ⏹️"
                it["progress"] = 0.0
                it["speed"] = ""
                if self.current_queue_item_id == item_id and self.engine:
                    self.engine.cancel()
                if self.queue_callback:
                    self.queue_callback(it)
                break

    def retry_queue_item(self, item_id):
        """İptal edilen veya hatalı öğeyi yeniden kuyruğa alır."""
        for it in self.queue_items:
            if it["id"] == item_id:
                it["status"] = "Bekliyor"
                it["progress"] = 0.0
                it["speed"] = ""
                if self.queue_callback:
                    self.queue_callback(it)
                break

    def clear_queue(self):
        if self.is_queue_running:
            self.stop_queue()
        self.queue_items.clear()
        self.is_queue_paused = False
        self.current_queue_item_id = None

    def toggle_queue_pause(self, status_update_cb=None):
        if self.is_queue_running and not self.is_queue_paused:
            self.pause_queue()
            return "PAUSED"
        else:
            self.resume_queue(status_update_cb=status_update_cb)
            return "RUNNING"

    def pause_queue(self):
        if self.is_queue_running and not self.is_queue_paused:
            self.is_queue_paused = True
            self.is_queue_running = False
            if self.engine:
                self.engine.cancel()
            if self.current_queue_item_id:
                for it in self.queue_items:
                    if it["id"] == self.current_queue_item_id and it["status"] not in ("Tamamlandı", "İptal Edildi ⏹️"):
                        it["status"] = "⏸️ Duraklatıldı"
                        if self.queue_callback:
                            self.queue_callback(it)

    def resume_queue(self, status_update_cb=None):
        self.is_queue_paused = False
        self.start_queue(status_update_cb=status_update_cb)

    def stop_queue(self):
        self.is_queue_running = False
        self.is_queue_paused = False
        self.current_queue_item_id = None
        if self.engine:
            self.engine.cancel()

    def start_queue(self, status_update_cb=None, callback=None):
        if self.is_queue_running:
            return
        self.is_queue_running = True
        self.is_queue_paused = False
        self.queue_callback = status_update_cb or callback
        if self.engine:
            self.engine.reset_cancel()

        def queue_worker():
            for item in self.queue_items:
                if not self.is_queue_running or self.is_queue_paused:
                    break
                if item["status"] in ("Tamamlandı", "İptal Edildi ⏹️"):
                    continue

                item_id = item["id"]
                self.current_queue_item_id = item_id
                item["status"] = "İndiriliyor %0"
                if self.queue_callback:
                    self.queue_callback(item)

                out_filename = re.sub(r'[\\/*?:"<>|]', '_', item["title"]).strip() + ".mp4"
                out_path = os.path.join(self.download_dir, out_filename)

                last_queue_cb_time = [0.0]

                def item_prog(comp, tot, b=0, spd=0, *args):
                    if not self.is_queue_running or self.is_queue_paused:
                        return
                    ratio = comp / tot if tot > 0 else 0
                    item["progress"] = ratio
                    spd_mb = spd / (1024 * 1024) if spd > 0 else 0
                    item["speed"] = f"⚡ {spd_mb:.2f} MB/s" if spd_mb > 0 else ""
                    item["size"] = f"{b/(1024*1024):.1f} MB" if b > 0 else f"{comp}/{tot}"
                    item["status"] = f"İndiriliyor %{ratio*100:.0f}"
                    now = time.time()
                    if ratio >= 1.0 or (now - last_queue_cb_time[0] >= 0.08):
                        last_queue_cb_time[0] = now
                        if self.queue_callback:
                            self.queue_callback(item)

                try:
                    url = item["url"]
                    if item.get("media_type") == "social" or any(d in url.lower() for d in ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "twitter.com", "x.com"]):
                        def yt_prog(down, tot, spd, ratio):
                            if not self.is_queue_running or self.is_queue_paused:
                                return
                            item["progress"] = ratio
                            spd_mb = spd / (1024 * 1024) if spd > 0 else 0
                            item["speed"] = f"⚡ {spd_mb:.2f} MB/s" if spd_mb > 0 else ""
                            item["size"] = f"{down/(1024*1024):.1f} MB"
                            item["status"] = f"İndiriliyor %{ratio*100:.0f}"
                            now = time.time()
                            if ratio >= 1.0 or (now - last_queue_cb_time[0] >= 0.08):
                                last_queue_cb_time[0] = now
                                if self.queue_callback:
                                    self.queue_callback(item)

                        success, res = self.engine.download_youtube_media(
                            media_url=url,
                            output_dir=self.download_dir,
                            format_choice="best",
                            progress_callback=yt_prog
                        )
                    else:
                        # Film / Dizi / HLS / MP4 Çözümü
                        if item.get("resolved_data"):
                            res_data = item["resolved_data"]
                        else:
                            res_data = self.resolve_media_url(url)

                        if res_data and res_data.get("success", True):
                            vid_url = res_data.get("video_url")
                            headers = res_data.get("video_headers", {})
                            segs = res_data.get("video_segments")
                            audio_tracks = res_data.get("audio_tracks", [])
                            tot_s = res_data.get("total_segments") or (len(segs) if segs else 1000)
                            threads = int(getattr(self, "speed_threads", 4))

                            v_clean = (vid_url or "").lower().split("?")[0]
                            is_direct = res_data.get("direct_file") or (not any(k in v_clean for k in [".m3u8", ".mpd", "seg-", "fragment"]) and v_clean.endswith((".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi")))

                            if is_direct and not segs:
                                success, res = self.engine.download_direct_file(
                                    url=vid_url,
                                    output_filepath=out_path,
                                    thread_count=threads,
                                    custom_headers=headers,
                                    progress_callback=item_prog
                                )
                            elif len(audio_tracks) >= 2 and item.get("audio_choice") == "dual":
                                success, res = self.engine.run_multi_audio_download(
                                    video_url=vid_url,
                                    audio_tracks=audio_tracks[:2],
                                    output_filepath=out_path,
                                    video_headers=headers,
                                    total_segments=tot_s,
                                    thread_count=threads,
                                    progress_callback=item_prog,
                                    video_segments=segs
                                )
                            else:
                                has_sep = False
                                sel_aud = audio_tracks[0] if audio_tracks else None
                                if sel_aud and sel_aud.get("sample_segment_url") and vid_url != sel_aud.get("sample_segment_url"):
                                    has_sep = True

                                if has_sep and sel_aud:
                                    success, res = self.engine.run_dual_stream_download(
                                        video_url=vid_url,
                                        audio_url=sel_aud["sample_segment_url"],
                                        output_filepath=out_path,
                                        video_headers=headers,
                                        audio_headers=sel_aud.get("headers", headers),
                                        total_segments=sel_aud.get("count", tot_s),
                                        thread_count=threads,
                                        progress_callback=item_prog,
                                        video_segments=segs,
                                        audio_segments=sel_aud.get("segments")
                                    )
                                else:
                                    tgt_url = sel_aud["sample_segment_url"] if sel_aud else vid_url
                                    tgt_h = sel_aud.get("headers", headers) if sel_aud else headers
                                    tgt_segs = sel_aud.get("segments") if sel_aud else segs
                                    success, res = self.engine.run_download(
                                        sample_url=tgt_url,
                                        output_filepath=out_path,
                                        thread_count=threads,
                                        total_segments=tot_s,
                                        custom_headers=tgt_h,
                                        segment_urls=tgt_segs,
                                        progress_callback=item_prog
                                    )
                        else:
                            success, res = False, "Çözümlenemedi"

                    if success:
                        item["status"] = "Tamamlandı"
                        item["progress"] = 1.0
                        item["out_path"] = res
                        scan_media_file(res)
                        send_mobile_notification("İndirme Tamamlandı ✅", f"{item['title']} galeriye kaydedildi.")
                        if add_history_entry:
                            f_sz = os.path.getsize(res) if os.path.exists(res) else 0
                            add_history_entry(item["title"] or os.path.basename(res), res, size_bytes=f_sz, source_url=url, media_type="Dizi / Kuyruk")
                    elif self.is_queue_paused or not self.is_queue_running:
                        item["status"] = "⏸️ Duraklatıldı"
                    elif item.get("status") == "İptal Edildi ⏹️":
                        item["status"] = "İptal Edildi ⏹️"
                    else:
                        item["status"] = f"Hata: {str(res)[:25]}"
                except Exception as ex:
                    if self.is_queue_paused or not self.is_queue_running:
                        item["status"] = "⏸️ Duraklatıldı"
                    elif item.get("status") == "İptal Edildi ⏹️":
                        item["status"] = "İptal Edildi ⏹️"
                    else:
                        item["status"] = f"Hata: {str(ex)[:25]}"

                if self.queue_callback:
                    self.queue_callback(item)
                time.sleep(0.5)

            self.is_queue_running = False
            self.current_queue_item_id = None
            if not self.is_queue_paused and self.queue_callback:
                # Kuyruk bitti bildirimi
                send_mobile_notification("Kuyruk Tamamlandı 🎉", "Tüm kuyruk indirmeleri başarıyla tamamlandı.")

        self.queue_thread = threading.Thread(target=queue_worker, daemon=True)
        self.queue_thread.start()

    # =========================================================================
    # DİZİ BÖLÜM TARAYICI (SERIES EPISODE SCANNER)
    # =========================================================================
    def scan_series_episodes(self, base_url, start_ep=1, end_ep=10, all_episodes=False):
        """
        Dizi linkini veya şablonunu analiz ederek bölüm linklerini otomatik üretir.
        all_episodes=True ise ve DOM tarayıcı varsa tüm bölümleri keşfeder.
        """
        if all_episodes and scan_series_episodes_func:
            try:
                scanned = scan_series_episodes_func(base_url)
                if scanned and isinstance(scanned, list) and len(scanned) > 0:
                    return scanned
            except Exception:
                logger.debug("[android_app/mobile_engine.py:699] scan_series_episodes() sessiz istisna yutuldu", exc_info=True)

        results = []
        for ep in range(start_ep, end_ep + 1):
            ep_url = ""
            if "-bolum" in base_url or "-sezon" in base_url:
                ep_url = re.sub(r'(\d+)-bolum', f'{ep}-bolum', base_url)
            elif re.search(r'/episode-\d+', base_url):
                ep_url = re.sub(r'/episode-\d+', f'/episode-{ep}', base_url)
            elif re.search(r'ep=\d+', base_url):
                ep_url = re.sub(r'ep=\d+', f'ep={ep}', base_url)
            else:
                clean_base = base_url.rstrip('/')
                ep_url = f"{clean_base}/{ep}-bolum"

            results.append({
                "title": f"Bölüm {ep}",
                "url": ep_url,
                "episode": ep
            })
        return results

    # =========================================================================
    # MEDYA DÖNÜŞTÜRÜCÜ (CONVERTER ENGINE) — FFmpeg + Pure-Python Hibrit
    # =========================================================================
    @staticmethod
    def _iter_ts_pes_payload(fin, audio_pid=None):
        """
        MPEG-TS akisindan ses PID'ine ait PES yuklerini sirayla verir.

        188 baytlik TS paketleri okunur, uyum baytlari (adaptation field) ve PES
        basliklari atlanir. Boylece cikti gercek ADTS cerceve akisidir; onceki
        surumdeki gibi TS baslik baytlari ses verisi sanilmaz.
        """
        SYNC = 0x47
        PACKET = 188
        pmt_pids = set()
        audio_pids = set() if audio_pid is None else {audio_pid}

        while True:
            pkt = fin.read(PACKET)
            if len(pkt) < PACKET:
                return
            if pkt[0] != SYNC:
                # Senkronu yeniden yakala
                idx = pkt.find(bytes([SYNC]), 1)
                if idx == -1:
                    continue
                fin.seek(idx - PACKET, 1)
                continue

            pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
            payload_start = bool(pkt[1] & 0x40)
            adaptation = (pkt[3] >> 4) & 0x03
            offset = 4
            if adaptation in (2, 3):
                offset += 1 + pkt[4]
            if adaptation == 2 or offset >= PACKET:
                continue
            payload = pkt[offset:]

            # PAT (PID 0) -> PMT PID'leri
            if pid == 0 and payload_start and not audio_pids:
                ptr = payload[0] if payload else 0
                sec = payload[1 + ptr:]
                if len(sec) > 8:
                    section_len = ((sec[1] & 0x0F) << 8) | sec[2]
                    body = sec[8:3 + section_len - 4]
                    for i in range(0, len(body) - 3, 4):
                        prog = (body[i] << 8) | body[i + 1]
                        pmt = ((body[i + 2] & 0x1F) << 8) | body[i + 3]
                        if prog != 0:
                            pmt_pids.add(pmt)
                continue

            # PMT -> ses akisi PID'leri (stream_type 0x0F = AAC/ADTS, 0x03/0x04 = MPEG audio)
            if pid in pmt_pids and payload_start and not audio_pids:
                ptr = payload[0] if payload else 0
                sec = payload[1 + ptr:]
                if len(sec) > 12:
                    section_len = ((sec[1] & 0x0F) << 8) | sec[2]
                    prog_info_len = ((sec[10] & 0x0F) << 8) | sec[11]
                    i = 12 + prog_info_len
                    limit = min(len(sec), 3 + section_len - 4)
                    while i + 4 < limit:
                        stream_type = sec[i]
                        epid = ((sec[i + 1] & 0x1F) << 8) | sec[i + 2]
                        es_len = ((sec[i + 3] & 0x0F) << 8) | sec[i + 4]
                        if stream_type in (0x03, 0x04, 0x0F, 0x11):
                            audio_pids.add(epid)
                        i += 5 + es_len
                continue

            if pid not in audio_pids:
                continue

            if payload_start and len(payload) > 8 and payload[:3] == b"\x00\x00\x01":
                pes_header_len = payload[8]
                payload = payload[9 + pes_header_len:]
            if payload:
                yield payload

    @staticmethod
    def _adts_frame_length(buf, i):
        """Verilen konumdaki ADTS cercevesinin uzunlugunu dondurur, gecersizse 0."""
        if i + 7 > len(buf):
            return 0
        if buf[i] != 0xFF or (buf[i + 1] & 0xF0) != 0xF0:
            return 0
        if (buf[i + 1] & 0x06) != 0:          # layer alani daima 00 olmali
            return 0
        sampling_idx = (buf[i + 2] >> 2) & 0x0F
        if sampling_idx > 12:
            return 0
        length = ((buf[i + 3] & 0x03) << 11) | (buf[i + 4] << 3) | ((buf[i + 5] & 0xE0) >> 5)
        return length if 7 <= length <= 8192 else 0

    def _extract_audio_pure_python(self, input_file, out_file, log_cb=None):
        """
        Android 14 SELinux / izin engeli durumunda calisan Saf Python Ses Ayiklayici.

        MPEG-TS akisindan ses PID'ini cozup ADTS cercevelerini butun halinde yazar.
        Parca sinirlari arasinda kalan cerceveler artik kaybolmaz (bkz. B4).
        MP4/M4A gibi konteynerlerde ses akisi yeniden paketlenemez; bu durumda
        sessizce bozuk dosya uretmek yerine acik bir hata dondurulur.
        """
        try:
            with open(input_file, "rb") as fin:
                header = fin.read(188 * 4)
                fin.seek(0)

                is_ts = bool(header) and header[0] == 0x47 and (
                    len(header) < 189 or header[188] == 0x47
                )

                if not is_ts:
                    # MP4/M4A/WebM: konteyner ayristirmadan ses akisi cikarilamaz.
                    # Eskiden dosya oldugu gibi kopyalanip .mp3 adi veriliyor ve
                    # "basarili" raporlaniyordu (bkz. B4).
                    msg = ("Bu dosya MPEG-TS degil; FFmpeg olmadan ses akisi ayiklanamiyor. "
                           "Lutfen FFmpeg kurulu bir ortamda tekrar deneyin.")
                    if log_cb:
                        log_cb(f"[!] {msg}")
                    return False, msg

                if log_cb:
                    log_cb("Saf Python motoru ile MPEG-TS ses akisi ayristiriliyor...")

                frames = 0
                carry = b""

                def drain(buf, fout, final=False):
                    """Tampondan tam ADTS cercevelerini yazar, kalan kuyrugu dondurur."""
                    written = 0
                    i = 0
                    limit = len(buf)
                    while i < limit:
                        # Baslik icin 7 bayt yoksa dur: kalan kuyruk bir sonraki
                        # yuke tasinmali. Eskiden bu baytlar tek tek atlanip
                        # kaybediliyordu; paket sinirina denk gelen her cerceve
                        # bozuluyordu (B4'un asil hatasi).
                        if not final and limit - i < 7:
                            break
                        flen = self._adts_frame_length(buf, i)
                        if flen == 0:
                            i += 1
                            continue
                        if i + flen > limit:
                            if final:
                                break
                            break
                        fout.write(buf[i:i + flen])
                        written += 1
                        i += flen
                    return buf[i:], written

                with open(out_file, "wb") as fout:
                    for payload in self._iter_ts_pes_payload(fin):
                        carry, n = drain(carry + payload, fout)
                        frames += n
                        if len(carry) > 65536:      # senkron kaybi: tamponu sinirla
                            carry = carry[-8192:]
                    if carry:
                        _, n = drain(carry, fout, final=True)
                        frames += n

            if frames == 0 or not os.path.exists(out_file) or os.path.getsize(out_file) < 1024:
                if os.path.exists(out_file):
                    try:
                        os.remove(out_file)
                    except OSError:
                        logger.debug("[android_app/mobile_engine.py:890] _extract_audio_pure_python() sessiz istisna yutuldu", exc_info=True)
                return False, "Dosyada ADTS ses cercevesi bulunamadi."

            if log_cb:
                log_cb(f"[+] {frames} ADTS ses cercevesi ayiklandi.")
            return True, out_file
        except Exception as ex:
            return False, f"Saf Python donusturme hatasi: {ex}"

    def convert_media(self, input_file, target_format="mp3", progress_cb=None, log_cb=None):
        """
        Yerel medya dönüştürme (FFmpeg + Saf Python Hibrit).
        """
        if not os.path.exists(input_file):
            return False, "Girdi dosyası bulunamadı."

        base_name = os.path.splitext(input_file)[0]
        out_file = f"{base_name}_converted.{target_format.lower()}"

        ffmpeg_bin = get_ffmpeg_path()
        can_try_ffmpeg = ffmpeg_bin and os.path.exists(ffmpeg_bin)

        if can_try_ffmpeg:
            cmd = [ffmpeg_bin, "-y", "-i", input_file]
            if target_format.lower() == "mp3":
                cmd.extend(["-vn", "-acodec", "libmp3lame", "-b:a", "320k", out_file])
            elif target_format.lower() == "mp4":
                cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k", out_file])
            elif target_format.lower() == "mkv":
                cmd.extend(["-c", "copy", out_file])
            else:
                cmd.extend([out_file])

            if log_cb:
                log_cb(f"Dönüştürülüyor: {os.path.basename(out_file)}")

            proc_env = os.environ.copy()
            if sys.platform != "win32":
                ff_dir = os.path.dirname(ffmpeg_bin)
                proc_env["LD_LIBRARY_PATH"] = f"{ff_dir}:/data/local/tmp:" + proc_env.get("LD_LIBRARY_PATH", "")
                proc_env["PATH"] = f"{ff_dir}:/data/local/tmp:" + proc_env.get("PATH", "")

            try:
                p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", env=proc_env)
                if p.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                    return True, out_file
            except Exception as ex:
                if log_cb:
                    log_cb(f"FFmpeg başlatılamadı ({ex}), Saf Python dönüştürücüye geçiliyor...")

        # FFmpeg çalışmazsa veya Android SELinux engeli varsa Saf Python Ayıklayıcıyı çalıştır.
        # Çıktı ham ADTS/AAC akışıdır; MP3 değildir — uzantı buna göre .aac olur,
        # aksi halde oynatıcılar MP3 sanıp açamıyordu (B4).
        if target_format.lower() in ("mp3", "m4a", "aac"):
            aac_out = f"{base_name}_converted.aac"
            return self._extract_audio_pure_python(input_file, aac_out, log_cb=log_cb)

        return False, "Dönüştürme başarısız oldu."

    # =========================================================================
    # İNDİRİLEN DOSYALAR & GEÇMİŞ
    # =========================================================================
    def get_completed_files(self):
        """
        İndirme klasöründeki MP4, MKV, MP3 dosyalarını listeler.
        """
        results = []
        if not os.path.exists(self.download_dir):
            return results

        valid_exts = {".mp4", ".mkv", ".mp3", ".webm", ".ts", ".m4a"}
        try:
            for f in os.listdir(self.download_dir):
                full_path = os.path.join(self.download_dir, f)
                if os.path.isfile(full_path) and os.path.splitext(f)[1].lower() in valid_exts:
                    size_mb = os.path.getsize(full_path) / (1024 * 1024)
                    mtime = os.path.getmtime(full_path)
                    date_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(mtime))
                    results.append({
                        "name": f,
                        "path": full_path,
                        "size_mb": round(size_mb, 1),
                        "date": date_str,
                        "is_audio": f.lower().endswith((".mp3", ".m4a"))
                    })
        except Exception:
            logger.debug("[android_app/mobile_engine.py:976] get_completed_files() sessiz istisna yutuldu", exc_info=True)

        results.sort(key=lambda x: os.path.getmtime(x["path"]) if os.path.exists(x["path"]) else 0, reverse=True)
        return results

    def delete_completed_file(self, filepath):
        """
        İndirilen medya dosyasını diskten siler.
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            logger.debug("[android_app/mobile_engine.py:990] delete_completed_file() sessiz istisna yutuldu", exc_info=True)
        return False

    def open_file_externally(self, filepath):
        """
        Dosyayı varsayılan sistem / Android medya oynatıcısında açar.
        """
        if not filepath or not os.path.exists(filepath):
            return False
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
                return True
            elif sys.platform == "darwin":
                subprocess.run(["open", filepath])
                return True
            elif os.environ.get("ANDROID_ARGUMENT") or "ANDROID_ROOT" in os.environ:
                return _run_android_task("open_file", filepath) is not None
            else:
                subprocess.run(["xdg-open", filepath], capture_output=True, timeout=5)
                return True
        except (OSError, RuntimeError, subprocess.SubprocessError):
            logger.warning("Dosya sistem oynatıcısında açılamadı: %s", filepath, exc_info=True)
        return False
