# -*- coding: utf-8 -*-
"""
Video Downloader Pro — HLS Master Quality Variant Parser.
Extracts video variants and selects the optimal bandwidth/resolution stream.
"""

import re
from urllib.parse import urljoin
from logger import get_logger

logger = get_logger("extractors.variants")


def extract_media_playlist_timeline(playlist_url, playlist_text):
    """Return absolute media/init URLs and their aligned HLS EXTINF durations."""
    if not playlist_text:
        return [], []

    segment_urls = []
    segment_durations = []
    pending_duration = None

    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MAP:"):
            map_match = re.search(r'URI=["\']([^"\']+)["\']', line)
            if map_match:
                segment_urls.append(urljoin(playlist_url, map_match.group(1)))
                segment_durations.append(None)
            continue
        if line.startswith("#EXTINF:"):
            duration_text = line.partition(":")[2].partition(",")[0].strip()
            try:
                parsed_duration = float(duration_text)
                pending_duration = parsed_duration if parsed_duration > 0 else None
            except ValueError:
                logger.debug("Invalid EXTINF duration ignored: %r", duration_text)
                pending_duration = None
            continue
        if line.startswith("#"):
            continue

        segment_urls.append(urljoin(playlist_url, line))
        segment_durations.append(pending_duration)
        pending_duration = None

    return segment_urls, segment_durations


def extract_master_quality_variants(master_url, master_m3u8_text):
    """
    Master M3U8 metnindeki tüm #EXT-X-STREAM-INF video varyantlarını ayrıştırır,
    çözünürlük ve bitrate'e göre etiketlendirir ve en yüksek kaliteden en düşüğe sıralar.
    """
    if not master_m3u8_text:
        return []
    variants = []
    lines = master_m3u8_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bw_m = re.search(r'BANDWIDTH=(\d+)', line)
            res_m = re.search(r'RESOLUTION=([0-9x]+)', line)
            bw = int(bw_m.group(1)) if bw_m else 0
            res_str = res_m.group(1) if res_m else ""

            h = 0
            if "x" in res_str:
                try:
                    h = int(res_str.split("x")[1])
                except Exception as e:
                    logger.debug(f"extract_master_quality_variants resolution error: {e}")

            if h >= 1600 or "3840" in res_str or "2160" in res_str:
                q_label = f"🌟 4K UHD ({res_str})"
            elif h >= 800 or "1920" in res_str:
                q_label = f"🎬 1080p Full HD ({res_str})"
            elif h >= 500 or "1280" in res_str:
                q_label = f"📺 720p HD ({res_str})"
            elif h >= 350 or "854" in res_str or "480" in res_str:
                q_label = f"📱 480p SD ({res_str})"
            elif h > 0 or "640" in res_str or "360" in res_str:
                q_label = f"⚡ 360p Düşük ({res_str})"
            else:
                q_label = f"🎬 Kalite ({bw//1000} kbps)" if bw > 0 else "🎬 Standart Kalite"

            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and not nxt.startswith("#"):
                    v_u = urljoin(master_url, nxt)
                    variants.append({
                        "label": q_label,
                        "resolution": res_str,
                        "bandwidth": bw,
                        "url": v_u
                    })

    if variants:
        variants.sort(key=lambda x: x["bandwidth"], reverse=True)
    return variants


def select_best_variant_url(master_url, master_m3u8_text, default=None):
    """
    Master playlist icindeki en yuksek BANDWIDTH'e sahip varyantin mutlak URL'sini dondurur.
    """
    variants = extract_master_quality_variants(master_url, master_m3u8_text)
    if variants:
        return variants[0]["url"]

    # #EXT-X-STREAM-INF etiketi yoksa (duz alt-playlist listesi) ilk gecerli satiri al.
    for line in (master_m3u8_text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return urljoin(master_url, line)
    return default
