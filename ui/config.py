# -*- coding: utf-8 -*-
"""
Video Downloader Pro — UI Configuration & Preference Management.
Handles user settings persistence, default directories, notifications, and error formatting.
"""

import os
import sys
import json
from logger import get_logger

logger = get_logger("ui.config")

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".video_downloader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULT_AGGRESSIVE_DPI_DOMAINS = (
    "discord", "roblox", "hdfilmcehennemi", "dizibox",
    "fullhdfilmizlesene", "filmmodu", "bicaps", "jetfilmizle",
)


def load_user_config():
    """Kullanici ayar dosyasini okur; yoksa bos sozluk dondurur."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        logger.warning("Ayar dosyasi okunamadi: %s", CONFIG_FILE, exc_info=True)
    return {}


def save_user_config(data):
    """Kullanici ayar dosyasini yazar."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logger.warning("Ayar dosyasi yazilamadi: %s", CONFIG_FILE, exc_info=True)
        return False


def _get_load_cfg():
    gui_mod = sys.modules.get("gui")
    if gui_mod and hasattr(gui_mod, "load_user_config"):
        return gui_mod.load_user_config
    return load_user_config


def _get_save_cfg():
    gui_mod = sys.modules.get("gui")
    if gui_mod and hasattr(gui_mod, "save_user_config"):
        return gui_mod.save_user_config
    return save_user_config


def get_default_download_directory():
    """
    Varsayılan indirme klasörünü döndürür.
    Öncelik:
      1. settings.json içindeki 'download_dir' (kullanıcı daha önce değiştirmişse)
      2. Standart Kullanıcı Videoları: C:\\Users\\<Kullanıcı>\\Videos\\VideoDownloaderPro
    Klasör diskte yoksa otomatik olarak oluşturulur.
    """
    try:
        cfg = _get_load_cfg()()
        custom_dir = str(cfg.get("download_dir", "")).strip().strip('"')
        if custom_dir and os.path.isdir(custom_dir):
            return custom_dir
    except Exception:
        logger.debug("[ui.config] load_user_config download_dir istisnası", exc_info=True)

    home = os.path.expanduser("~")
    videos_dir = os.path.join(home, "Videos")
    if not os.path.exists(videos_dir):
        alt_videos = os.path.join(home, "Videolar")
        if os.path.exists(alt_videos):
            videos_dir = alt_videos
        else:
            try:
                os.makedirs(videos_dir, exist_ok=True)
            except Exception:
                videos_dir = home

    target_dir = os.path.join(videos_dir, "VideoDownloaderPro")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        logger.debug("[ui.config] get_default_download_directory makedirs istisnası", exc_info=True)
    return target_dir


def set_custom_download_directory(new_dir):
    """Kullanıcının belirlediği indirme klasörünü settings.json'a kaydeder."""
    if not new_dir:
        return False
    try:
        os.makedirs(new_dir, exist_ok=True)
    except Exception:
        logger.debug("[ui.config] set_custom_download_directory makedirs istisnası", exc_info=True)
    try:
        cfg = _get_load_cfg()()
        cfg["download_dir"] = new_dir
        return _get_save_cfg()(cfg)
    except Exception:
        logger.debug("[ui.config] set_custom_download_directory kaydetme istisnası", exc_info=True)
        return False


def get_subtitle_output_mode():
    """
    Kullanıcının altyazı çıktı tercihi:
    'embed_and_keep_srt' (varsayılan) -> Altyazıyı MP4 içine göm + Harici .srt kaydet
    'embed_only' -> Yalnızca MP4 içine göm (Harici .srt temizle)
    """
    try:
        cfg = _get_load_cfg()()
        return cfg.get("subtitle_output_mode", "embed_and_keep_srt")
    except Exception:
        return "embed_and_keep_srt"


def set_subtitle_output_mode(mode):
    """Kullanıcının altyazı çıktı tercihini kaydeder."""
    try:
        cfg = _get_load_cfg()()
        cfg["subtitle_output_mode"] = mode
        return _get_save_cfg()(cfg)
    except Exception:
        return False


def should_keep_external_srt():
    """Harici .srt dosyasının saklanıp saklanmayacağını döndürür."""
    return get_subtitle_output_mode() != "embed_only"


def get_notification_sound_enabled() -> bool:
    """İndirme tamamlandığında ses çalınsın mı (varsayılan True)."""
    try:
        cfg = _get_load_cfg()()
        return bool(cfg.get("notify_sound", True))
    except Exception:
        return True


def set_notification_sound_enabled(enabled: bool) -> bool:
    """İndirme tamamlandığında ses çalma ayarını kaydeder."""
    try:
        cfg = _get_load_cfg()()
        cfg["notify_sound"] = bool(enabled)
        return _get_save_cfg()(cfg)
    except Exception:
        return False


def get_desktop_notification_enabled() -> bool:
    """İndirme tamamlandığında masaüstü bildirimi gösterilsin mi (varsayılan True)."""
    try:
        cfg = _get_load_cfg()()
        return bool(cfg.get("notify_desktop", True))
    except Exception:
        return True


def set_desktop_notification_enabled(enabled: bool) -> bool:
    """İndirme tamamlandığında masaüstü bildirimi ayarını kaydeder."""
    try:
        cfg = _get_load_cfg()()
        cfg["notify_desktop"] = bool(enabled)
        return _get_save_cfg()(cfg)
    except Exception:
        return False


def find_goodbyedpi_dir():
    """
    GoodbyeDPI kurulum klasorunu bulur.
    Sirasiyla: VDP_GOODBYEDPI_DIR -> settings.json -> yaygin konumlar.
    Bulunamazsa None dondurur ve DPI ozelligi sessizce devre disi kalir.
    """
    env_dir = os.environ.get("VDP_GOODBYEDPI_DIR", "").strip().strip('"')
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    cfg_dir = str(_get_load_cfg()().get("goodbyedpi_dir", "")).strip().strip('"')
    if cfg_dir and os.path.isdir(cfg_dir):
        return cfg_dir

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Desktop", "GoodbyeDPI"),
        os.path.join(home, "GoodbyeDPI"),
        os.path.join(os.environ.get("ProgramFiles", ""), "GoodbyeDPI"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return None


def find_desktop_ffmpeg():
    """
    Masaüstü ortamında FFmpeg ikilisini arar.
    Sırasıyla:
      1. engine.get_ffmpeg_path() (PATH ve ortam değişkenleri)
      2. sys.executable yanı veya ./bin/ffmpeg.exe
      3. Standart konumlardan kontrol
    Bulunursa mutlak yolu döndürür, aksi halde None.
    """
    try:
        from engine import get_ffmpeg_path
        p = get_ffmpeg_path()
        if p and os.path.exists(p):
            return p
    except Exception:
        logger.debug("[ui.config] get_ffmpeg_path() hatası", exc_info=True)

    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(os.path.join(meipass, exe_name))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, exe_name))
        candidates.append(os.path.join(exe_dir, "bin", exe_name))

    candidates.append(os.path.join(os.getcwd(), exe_name))
    candidates.append(os.path.join(os.getcwd(), "bin", exe_name))

    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def format_seconds(secs):
    if secs is None or secs < 0 or secs > 86400 * 7:
        return "--:--"
    secs = int(secs)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


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
        return "🔒 Dosya yazma izni engellendi.\nÇözüm: Hedef dosyanın veya klasörün başka bir programda (VLC / Oynatıcı) açık olmadığından emin olun."
    elif "unsupported url" in err_lower or "no video source" in err_lower or "bulunamadı" in err_lower or "kaynak bulunamadı" in err_lower:
        return "ℹ️ Sayfada oynatılabilir video akışı bulunamadı.\nÇözüm: Bölüm henüz siteye yüklenmemiş olabilir veya farklı bir kaynak seçiniz."
    return str(err_msg)
