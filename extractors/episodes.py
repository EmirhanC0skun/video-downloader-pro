# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Series & Episode Scanner.
Scans and generates season/episode URLs from web pages.
"""

import re
from urllib.parse import urlparse, urljoin
import requests

try:
    from curl_cffi import requests as c_requests
except Exception:
    c_requests = None

from logger import get_logger

logger = get_logger("extractors.episodes")


def scan_series_episodes(page_url, log_callback=None):
    """
    Dizi ana sayfası veya bölüm sayfasından o dizinin tüm sezon ve bölüm linklerini otomatik çıkarır.
    """
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception as e:
                logger.debug(f"log_callback error: {e}")

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": page_url,
        "Accept": "*/*"
    }

    try:
        html = ""
        try:
            if c_requests:
                r_c = c_requests.get(page_url, impersonate="chrome124", timeout=12)
                if r_c.status_code == 200:
                    html = r_c.text
        except Exception as ex_c:
            logger.debug(f"scan_series_episodes c_requests error: {ex_c}")
        if not html:
            r = session.get(page_url, headers=headers, timeout=12)
            html = r.text
    except Exception as e:
        log(f"[!] Sayfa açılamadı: {e}")
        return []

    # SERİ FİLM / KOLEKSİYON SAYFALARI ÖZEL TARAMASI
    if any(sk in page_url.lower() for sk in ["/serifilm/", "/seri-film", "/koleksiyon", "/series-movie", "serisi"]):
        col_films = re.findall(r'<a[^>]+href=["\'](https?://[^"\']+/film/[^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
        col_episodes = []
        seen_col = set()
        c_idx = 1
        for f_href, f_text in col_films:
            if f_href not in seen_col and not any(x in f_href for x in ["/filmizle/", "en-cok", "listeleri", "populer", "trend", "/yil/"]):
                seen_col.add(f_href)
                clean_title = re.sub(r'<[^>]+>', ' ', f_text).strip() or f"Film {c_idx}"
                col_episodes.append({
                    "season": 1,
                    "episode": c_idx,
                    "title": f"Film {c_idx:02d} - {clean_title[:45]}",
                    "url": f_href
                })
                c_idx += 1
        if col_episodes:
            log(f"[+] 🎬 Seri Film koleksiyonunda {len(col_episodes)} film bulundu!")
            return col_episodes

    # 1. JETFİLMİZLE & JETPLAYER DİZİ BUTONLARI (data-season & data-episode)
    title_m = re.search(r'<title>(.*?)</title>', html)
    raw_page_title = title_m.group(1) if title_m else ""
    clean_series_name = re.sub(r'(?:Dizisi|Filmi|İzle|Full HD|Türkçe Dublaj|Jetfilmizle|Filmmodu|Dizilla|YabancıDizi|\||-).*', '', raw_page_title, flags=re.IGNORECASE).strip() or "Dizi"

    btn_matches = re.findall(
        r'<button[^>]+data-source-index=["\']([^"\']+)["\'][^>]*data-player-type=["\']([^"\']+)["\'][^>]*data-season=["\']([^"\']+)["\'][^>]*data-episode=["\']([^"\']+)["\'][^>]*>(.*?)</button>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not btn_matches:
        btn_matches = re.findall(
            r'<button[^>]+data-season=["\']([^"\']+)["\'][^>]*data-episode=["\']([^"\']+)["\'][^>]*data-source-index=["\']([^"\']+)["\'][^>]*data-player-type=["\']([^"\']+)["\'][^>]*>(.*?)</button>',
            html, re.DOTALL | re.IGNORECASE
        )
        if btn_matches:
            btn_matches = [(b[2], b[3], b[0], b[1], b[4]) for b in btn_matches]

    if btn_matches:
        episodes = []
        base_clean_url = page_url.split("?")[0]
        for s_idx, p_type, season_num, ep_num, btn_text in btn_matches:
            try:
                s_int = int(season_num)
                e_int = int(ep_num)
            except Exception:
                s_int, e_int = 1, len(episodes) + 1
            ep_url = f"{base_clean_url}?season={s_int}&episode={e_int}&source_index={s_idx}&player_type={p_type}"
            episodes.append({
                "season": s_int,
                "episode": e_int,
                "title": f"{clean_series_name} - {s_int}. Sezon {e_int}. Bölüm",
                "url": ep_url
            })
        if episodes:
            log(f"[+] 📺 {clean_series_name}: Toplam {len(episodes)} bölüm başarıyla tarandı.")
            return episodes

    episodes = []
    links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
    seen_urls = set()

    for href, text_content in links:
        full_href = urljoin(page_url, href.strip())
        clean_text = re.sub(r'<[^>]+>', ' ', text_content).strip()

        is_ep_url = bool(re.search(r'(?:\d+[-_/\s]?(?:sezon|season)|(?:sezon|season)[-_/\s]?\d+).*?(?:\d+[-_/\s]?(?:bolum|episode|bölüm)|(?:bolum|episode|bölüm)[-_/\s]?\d+)|s\d+e\d+', full_href, re.IGNORECASE))
        is_ep_text = bool(re.search(r'\d+\s*\.?\s*(?:sezon|season).*?\d+\s*\.?\s*(?:bölüm|bolum|episode)', clean_text, re.IGNORECASE))

        if (is_ep_url or is_ep_text) and full_href not in seen_urls and not full_href.endswith((".jpg", ".png", ".jpeg", ".webp", "#respond")):
            if "#" in full_href or "replytocom" in full_href:
                continue

            seen_urls.add(full_href)

            s_match = re.search(r'(\d+)\s*[-_.]?\s*(?:sezon|season)|(?:sezon|season)\s*[-_.]?\s*(\d+)', f"{clean_text} {full_href}", re.IGNORECASE)
            e_match = re.search(r'(\d+)\s*[-_.]?\s*(?:bölüm|bolum|episode)|(?:bölüm|bolum|episode)\s*[-_.]?\s*(\d+)', f"{clean_text} {full_href}", re.IGNORECASE)

            s_num = int(s_match.group(1) or s_match.group(2)) if s_match else 1
            e_num = int(e_match.group(1) or e_match.group(2)) if e_match else (len(episodes) + 1)

            disp_text = clean_text if ("sezon" in clean_text.lower() or "bölüm" in clean_text.lower()) else f"{s_num}. Sezon {e_num}. Bölüm"
            title = f"{clean_series_name} - S{s_num:02d}E{e_num:02d} - {disp_text}"
            episodes.append({
                "season": s_num,
                "episode": e_num,
                "title": title[:55],
                "url": full_href
            })

    episodes.sort(key=lambda x: (x["season"], x["episode"]))
    return episodes


def generate_episode_urls(template_url, start_ep, end_ep):
    """
    Verilen URL içerisindeki bölüm sayısını otomatik tespit edip istenen aralıkta (start_ep - end_ep)
    bölüm bağlantı listesi üretir.
    """
    ep_match = re.search(r'(bolum|episode|ep)[-_/\s]*(\d+)', template_url, re.IGNORECASE)
    results = []

    if ep_match:
        prefix = template_url[:ep_match.start(2)]
        suffix = template_url[ep_match.end(2):]
        pad = len(ep_match.group(2))

        for i in range(start_ep, end_ep + 1):
            formatted_ep = f"{i:0{pad}d}" if pad > 1 else str(i)
            url_i = f"{prefix}{formatted_ep}{suffix}"
            results.append({
                "season": 1,
                "episode": i,
                "title": f"Bölüm {i:02d}",
                "url": url_i
            })
    else:
        for i in range(start_ep, end_ep + 1):
            results.append({
                "season": 1,
                "episode": i,
                "title": f"Bölüm {i:02d}",
                "url": f"{template_url.rstrip('/')}-{i}-bolum"
            })
    return results
