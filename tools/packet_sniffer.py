import os
import sys
import re
import time
import base64
from urllib.parse import urlparse, urljoin
import requests

_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging

        def get_logger(name):
            return logging.getLogger(name)

logger = get_logger("sniffer")


def decrypt_rapidvid_av(e):
    """
    Rapidvid av('...') şifreli oynatıcı anahtarını çözer.
    """
    try:
        rev = e[::-1]
        t = base64.b64decode(rev).decode('latin1')
        o = ""
        for i in range(len(t)):
            r = "K9L"[i % 3]
            n = ord(t[i]) - (ord(r[0]) % 5 + 1)
            o += chr(n)
        return base64.b64decode(o).decode('utf-8')
    except Exception:
        return None


def pick_highest_bandwidth_variant(master_url, master_text, default=None):
    """
    Master playlist icindeki en yuksek BANDWIDTH'e sahip varyantin mutlak URL'sini dondurur.

    Onceki secim `var_lines[0] if "1080" in var_lines[0] else var_lines[-1]` idi;
    BANDWIDTH/RESOLUTION okunmadigi icin varyantlari azalan sirada yayinlayan
    sitelerde en dusuk kalite seciliyordu.
    """
    if not master_text:
        return default

    lines = master_text.splitlines()
    best_bw = -1
    best_url = None
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        bw_m = re.search(r'BANDWIDTH=(\d+)', line)
        bw = int(bw_m.group(1)) if bw_m else 0
        for nxt in lines[i + 1:]:
            nxt = nxt.strip()
            if not nxt:
                continue
            if nxt.startswith("#"):
                break
            if bw > best_bw:
                best_bw = bw
                best_url = urljoin(master_url, nxt)
            break

    if best_url:
        return best_url

    # #EXT-X-STREAM-INF yoksa duz liste: ilk gecerli satiri kullan.
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            return urljoin(master_url, line)
    return default


def parse_master_m3u8_payload(master_url, master_text, base_headers, title, extra_subtitles=None):
    """
    Master M3U8 akışını ayrıştırarak ses kanallarını, video akışını, segment listelerini ve altyazıları üretir.
    """
    audio_tracks = []
    subtitles = list(extra_subtitles) if extra_subtitles else []
    total_segments_count = 0
    primary_video_url = ""
    all_v_segs = []

    # 1. Ses kanallarını yakala (#EXT-X-MEDIA:TYPE=AUDIO)
    audio_matches = re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO.*?NAME=[\'"]([^\'"]+)[\'"].*?URI=[\'"]([^\'"]+)[\'"]', master_text, re.IGNORECASE)
    for name, uri in audio_matches:
        aud_sub_url = urljoin(master_url, uri)
        try:
            r_aud = requests.get(aud_sub_url, headers=base_headers, timeout=8)
            if r_aud.status_code == 200:
                init_match = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']', r_aud.text)
                init_seg = [urljoin(aud_sub_url, init_match.group(1))] if init_match else []

                aud_segs = [urljoin(aud_sub_url, l.strip()) for l in r_aud.text.splitlines() if l.strip() and not l.startswith("#")]
                all_aud_segs = init_seg + aud_segs
                if all_aud_segs:
                    if total_segments_count == 0:
                        total_segments_count = len(all_aud_segs)
                    n_low = name.lower()
                    is_tr = any(k in n_low for k in ["turk", "türk", "tr", "dublaj"])
                    label = f"Türkçe Dublaj ({name})" if is_tr else f"Orijinal / İngilizce ({name})"
                    audio_tracks.append({
                        "name": label,
                        "lang": "tur" if is_tr else "eng",
                        "segments": all_aud_segs,
                        "sample_segment_url": all_aud_segs[0],
                        "count": len(all_aud_segs),
                        "headers": base_headers
                    })
        except Exception:
            logger.debug("[sniffer.py:62] parse_master_m3u8_payload() sessiz istisna yutuldu", exc_info=True)

    # 2. Altyazıları yakala (#EXT-X-MEDIA:TYPE=SUBTITLES)
    sub_matches = re.findall(r'#EXT-X-MEDIA:TYPE=SUBTITLES.*?NAME=[\'"]([^\'"]+)[\'"].*?URI=[\'"]([^\'"]+)[\'"]', master_text, re.IGNORECASE)
    for name, uri in sub_matches:
        sub_url = urljoin(master_url, uri)
        is_tr = any(k in name.lower() for k in ["turk", "türk", "tr", "altyazı"])
        subtitles.append({
            "name": f"Türkçe Altyazı ({name})" if is_tr else f"Altyazı ({name})",
            "url": sub_url,
            "lang": "tur" if is_tr else "und",
            "headers": base_headers
        })

    # 3. Video akışını yakala
    var_lines = [l.strip() for l in master_text.splitlines() if l.strip() and not l.startswith("#")]
    if var_lines:
        v_sub_url = pick_highest_bandwidth_variant(master_url, master_text,
                                                   urljoin(master_url, var_lines[-1]))
        try:
            r_vsub = requests.get(v_sub_url, headers=base_headers, timeout=8)
            if r_vsub.status_code == 200:
                init_match = re.search(r'#EXT-X-MAP:URI=["\']([^"\']+)["\']', r_vsub.text)
                init_seg = [urljoin(v_sub_url, init_match.group(1))] if init_match else []

                v_segs = [urljoin(v_sub_url, l.strip()) for l in r_vsub.text.splitlines() if l.strip() and not l.startswith("#")]
                all_v_segs = init_seg + v_segs
                if all_v_segs:
                    primary_video_url = all_v_segs[0]
                    if total_segments_count == 0:
                        total_segments_count = len(all_v_segs)
        except Exception:
            logger.debug("[sniffer.py:93] parse_master_m3u8_payload() sessiz istisna yutuldu", exc_info=True)

    if not primary_video_url and audio_tracks:
        primary_video_url = audio_tracks[0]["sample_segment_url"]

    if primary_video_url:
        if not audio_tracks:
            audio_tracks.append({
                "name": "🎬 Standart / Orijinal Akış",
                "lang": "tur",
                "segments": all_v_segs,
                "sample_segment_url": primary_video_url,
                "count": len(all_v_segs) or total_segments_count,
                "headers": base_headers
            })

        return {
            "success": True,
            "title": title,
            "video_url": primary_video_url,
            "video_headers": base_headers,
            "video_segments": all_v_segs,
            "audio_tracks": audio_tracks,
            "subtitles": subtitles,
            "total_segments": total_segments_count or len(all_v_segs) or 1000
        }
    return None


def sniff_media_stream(url, timeout=12, log_callback=None):
    """
    Playwright / Chromium kullanarak dinamik, lazy-load veya JS şifreli sayfalardaki
    gerçek medya akışlarını (M3U8, MPD, MP4, Altyazılar) DOM ve ağ seviyesinde otonom yakalar.
    """
    def log(msg):
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                logger.debug("[sniffer.py:132] log() sessiz istisna yutuldu", exc_info=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("[!] Playwright kütüphanesi yüklü değil.")
        return None

    # Standalone EXE uyumluluğu için AppData ms-playwright yolunu zorunlu kıl
    localappdata = os.environ.get("LOCALAPPDATA", "")
    ms_playwright_dir = os.path.join(localappdata, "ms-playwright")
    if os.path.exists(ms_playwright_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ms_playwright_dir

    log("[i] Akıllı Ağ Dinleyicisi (Headless Sniffer) başlatılıyor...")
    captured_m3u8s = []
    captured_mp4s = []
    captured_segments = []
    captured_subtitles = []
    page_title = "Web Medya Akışı"
    detected_master_url = None
    detected_headers = {}

    start_time = time.time()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    with sync_playwright() as p:
        browser = None
        launch_args = [
            "--headless=new",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--ignore-certificate-errors",
            "--allow-running-insecure-content",
            "--mute-audio"
        ]

        # 1. Strateji: Sistem Google Chrome
        try:
            browser = p.chromium.launch(headless=True, channel="chrome", args=launch_args)
        except Exception:
            logger.debug("[sniffer.py:174] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

        # 2. Strateji: Sistem Microsoft Edge
        if not browser:
            try:
                browser = p.chromium.launch(headless=True, channel="msedge", args=launch_args)
            except Exception:
                logger.debug("[sniffer.py:181] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

        # 3. Strateji: Yerel ms-playwright Chromium
        if not browser:
            try:
                browser = p.chromium.launch(headless=True, args=launch_args)
            except Exception:
                logger.debug("[sniffer.py:188] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

        # 4. Strateji: Doğrudan Executable Yolları
        if not browser:
            candidate_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(localappdata, r"Google\Chrome\Application\chrome.exe")
            ]
            for cp in candidate_paths:
                if os.path.exists(cp):
                    try:
                        browser = p.chromium.launch(headless=True, executable_path=cp, args=launch_args)
                        if browser:
                            break
                    except Exception:
                        logger.debug("[sniffer.py:206] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

        if not browser:
            log("[!] Tarayıcı (Chromium / Chrome / Edge) başlatılamadı.")
            return None

        context = browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="tr-TR",
            ignore_https_errors=True
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['tr-TR', 'tr', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        def on_request(req):
            r_url = req.url
            if any(ad in r_url.lower() for ad in ["googleads", "doubleclick", "analytics", "facebook", "clarity", "hotjar", "mc.yandex", "banner"]):
                return

            req_h = dict(req.headers)
            clean_url = r_url.split("?")[0].lower()

            if ".m3u8" in r_url.lower() or "master.txt" in r_url.lower() or "playlist.txt" in r_url.lower():
                captured_m3u8s.append((r_url, req_h))
            elif any(clean_url.endswith(f".{ext}") for ext in ["mp4", "mkv", "webm"]):
                if not any(ign in r_url.lower() for ign in ["logo", "preview", "ad_", "trailer"]):
                    captured_mp4s.append((r_url, req_h))
            elif any(clean_url.endswith(f".{ext}") for ext in ["vtt", "srt"]):
                captured_subtitles.append({
                    "name": "Altyazı Dosyası",
                    "url": r_url,
                    "lang": "tur" if "tur" in r_url.lower() or "tr" in r_url.lower() else "und",
                    "headers": req_h
                })
            elif any(k in r_url.lower() for k in ["image2_", "imageaud", "sublist_", "/segment-", "/chunk-", "/seg_"]):
                captured_segments.append((r_url, req_h))

        page.on("request", on_request)

        try:
            log("1. Sayfa taranıyor...")
            page.goto(url, wait_until="commit", timeout=20000)

            # Cloudflare / Bot Koruması Çok Dilli Kontrolü ("Just a moment", "Bir dakika lütfen...", vb.)
            CF_KEYWORDS = ["just a moment", "bir dakika", "attention required", "ddos-guard", "cloudflare", "güvenlik doğrulaması", "checking your browser"]
            
            cur_title = (page.title() or "").lower()
            if any(kw in cur_title for kw in CF_KEYWORDS) or "__cf_chl" in page.url:
                log("[i] Cloudflare güvenlik doğrulaması bekleniyor...")
                try:
                    page.wait_for_function(
                        "() => !['just a moment', 'bir dakika', 'attention required', 'ddos-guard', 'cloudflare', 'güvenlik doğrulaması', 'checking your browser'].some(k => (document.title || '').toLowerCase().includes(k))",
                        timeout=25000
                    )
                except Exception:
                    logger.debug("[sniffer.py:267] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

                # Turnstile Checkbox tıklama denemesi
                try:
                    for f in page.frames:
                        for sel in ['input[type="checkbox"]', '.ctp-checkbox-label', '#challenge-stage', 'iframe[src*="cloudflare"]']:
                            loc = f.locator(sel)
                            if loc.count() > 0:
                                loc.first.click(timeout=2000)
                except Exception:
                    logger.debug("[sniffer.py:277] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

                time.sleep(1.5)

            page.wait_for_load_state("domcontentloaded")
            raw_title = page.title()
            if raw_title:
                page_title = raw_title.split("-")[0].split("|")[0].strip()

            log(f"2. Başlık: {page_title} (Oynatıcı ve Akışlar Çözümleniyor...)")

            # -------------------------------------------------------------
            # ADIM A: DOM İçindeki window.scx Yapısını Otonom Çözümleme & iframe Enjeksiyonu
            # -------------------------------------------------------------
            page.evaluate("""() => {
                const scx_data = typeof scx !== 'undefined' ? scx : null;
                let targets = [];
                if (scx_data && typeof scx_data === 'object') {
                    for (let k in scx_data) {
                        let v = scx_data[k];
                        if (v && v.sx && Array.isArray(v.sx.t)) {
                            targets.push(...v.sx.t);
                        }
                    }
                }
                document.querySelectorAll('iframe').forEach(i => {
                    let s = i.getAttribute('data-src') || i.src;
                    if (s && s.startsWith('http')) targets.push(s);
                });
                
                targets.forEach(u => {
                    let ifr = document.createElement('iframe');
                    ifr.className = 'sniffer_injected_ifr';
                    ifr.style.width = '640px';
                    ifr.style.height = '360px';
                    ifr.src = u;
                    document.body.appendChild(ifr);
                });

                // Play butonlarına da tıkla
                const triggers = document.querySelectorAll('.ply, .ply-cover, .ply img, #play-video');
                triggers.forEach(t => { try { t.click(); } catch(e){} });
            }""")

            # -------------------------------------------------------------
            # ADIM B: Çerçeve (iframe) Taraması & Altyazı Tespiti
            # -------------------------------------------------------------
            for check_idx in range(15):
                for frame in page.frames:
                    try:
                        f_html = frame.content()

                        # Altyazı tespiti (JWPlayer Tracks)
                        jw_res_pl = frame.evaluate("""() => {
                            try {
                                if (window.jwplayer && typeof window.jwplayer === 'function') {
                                    const pl = jwplayer().getPlaylist ? jwplayer().getPlaylist() : null;
                                    if (pl && pl.length > 0) return pl[0];
                                }
                            } catch(e){}
                            return null;
                        }""")
                        if jw_res_pl and jw_res_pl.get("tracks"):
                            for tr in jw_res_pl["tracks"]:
                                tr_file = tr.get("file")
                                if tr_file and any(ext in tr_file.lower() for ext in [".vtt", ".srt", "/tur-", "sub"]):
                                    lbl = tr.get("label") or tr.get("name") or "Türkçe Altyazı"
                                    if not any(s["url"] == tr_file for s in captured_subtitles):
                                        captured_subtitles.append({
                                            "name": lbl,
                                            "url": tr_file,
                                            "lang": "tur" if any(k in lbl.lower() for k in ["tur", "türk", "tr"]) else "und",
                                            "headers": {
                                                "User-Agent": user_agent,
                                                "Referer": "https://rapidvid.net/"
                                            }
                                        })

                        # Rapidvid av('...') kontrolü
                        av_m = re.findall(r'av\([\'"]([^\'"]+)[\'"]\)', f_html)
                        if av_m:
                            detected_master_url = decrypt_rapidvid_av(av_m[0])
                            if detected_master_url:
                                detected_headers = {
                                    "User-Agent": user_agent,
                                    "Referer": "https://rapidvid.net/",
                                    "Origin": "https://rapidvid.net"
                                }
                                log(f"[+] Rapidvid Master Playlist Yakalandı: {detected_master_url[:60]}...")
                                break

                        if jw_res_pl and jw_res_pl.get("file"):
                            detected_master_url = jw_res_pl["file"]
                            ref_origin = f"{urlparse(frame.url or url).scheme}://{urlparse(frame.url or url).netloc}"
                            detected_headers = {
                                "User-Agent": user_agent,
                                "Referer": f"{ref_origin}/",
                                "Origin": ref_origin
                            }
                            log(f"[+] JWPlayer Akış Adresi Yakalandı: {detected_master_url[:60]}...")
                            break
                    except Exception:
                        logger.debug("[sniffer.py:379] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)
                if detected_master_url:
                    break
                page.wait_for_timeout(500)

            # -------------------------------------------------------------
            # ADIM C: Ağ İsteklerini Dinleme Fallback
            # -------------------------------------------------------------
            if not detected_master_url:
                while time.time() - start_time < timeout:
                    if captured_m3u8s or captured_mp4s or len(captured_segments) >= 2:
                        break
                    page.wait_for_timeout(300)

        except Exception as e:
            log(f"[!] Sniffer işlem uyarısı: {e}")
        finally:
            try:
                browser.close()
            except Exception:
                logger.debug("[sniffer.py:399] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

    # Çözümleme Aşaması
    # Durum 1: JWPlayer veya doğrudan yakalanan Master URL
    if detected_master_url:
        is_direct_video = any(ext in detected_master_url.lower() for ext in [".mp4", ".webm", ".mkv", "/mp4/"]) and ".m3u8" not in detected_master_url.lower()
        if is_direct_video:
            log(f"[+] 🎯 Doğrudan MP4 Akışı Yakalandı: {os.path.basename(detected_master_url.split('?')[0])}")
            return {
                "success": True,
                "title": page_title,
                "video_url": detected_master_url,
                "video_headers": detected_headers,
                "audio_tracks": [],
                "subtitles": captured_subtitles,
                "total_segments": 1,
                "direct_file": True
            }
        try:
            r_mast = requests.get(detected_master_url, headers=detected_headers, stream=True, timeout=8)
            if r_mast.status_code == 200:
                content_type = r_mast.headers.get("Content-Type", "").lower()
                if "video" in content_type or "octet-stream" in content_type:
                    return {
                        "success": True,
                        "title": page_title,
                        "video_url": detected_master_url,
                        "video_headers": detected_headers,
                        "audio_tracks": [],
                        "subtitles": captured_subtitles,
                        "total_segments": 1,
                        "direct_file": True
                    }
                first_chunk = next(r_mast.iter_content(chunk_size=4096), b"").decode("utf-8", errors="ignore")
                if "#EXTM3U" in first_chunk:
                    # Tam playlist'i al
                    r_full = requests.get(detected_master_url, headers=detected_headers, timeout=8)
                    res = parse_master_m3u8_payload(detected_master_url, r_full.text, detected_headers, page_title, extra_subtitles=captured_subtitles)
                    if res:
                        sub_count = len(res.get('subtitles', []))
                        sub_info = f", {sub_count} Altyazı" if sub_count > 0 else ""
                        log(f"[+] Akış ve Kanallar Başarıyla Ayrıştırıldı! ({res.get('total_segments')} Parça, {len(res.get('audio_tracks', []))} Ses Kanalı{sub_info})")
                        return res
        except Exception as e:
            log(f"[!] Master M3U8 ayrıştırma uyarısı: {e}")

    # Durum 2: Yakalanan M3U8 istekleri
    if captured_m3u8s:
        target_m3u8, headers = captured_m3u8s[0]
        try:
            r_m = requests.get(target_m3u8, headers=headers, timeout=8)
            if r_m.status_code == 200:
                res = parse_master_m3u8_payload(target_m3u8, r_m.text, headers, page_title, extra_subtitles=captured_subtitles)
                if res:
                    log(f"[+] M3U8 Akışı Ayrıştırıldı! ({res.get('total_segments')} Parça)")
                    return res
        except Exception:
            logger.debug("[sniffer.py:456] sniff_media_stream() sessiz istisna yutuldu", exc_info=True)

    # Durum 3: Doğrudan MP4
    if captured_mp4s:
        target_mp4, headers = captured_mp4s[0]
        log(f"[+] Doğrudan MP4 yakalandı: {os.path.basename(target_mp4.split('?')[0])}")
        return {
            "success": True,
            "title": page_title,
            "video_url": target_mp4,
            "video_headers": headers,
            "audio_tracks": [],
            "subtitles": captured_subtitles,
            "total_segments": 1,
            "direct_file": True
        }

    log("[!] Sniffer ile sayfada oynatılan medya akışı yakalanamadı.")
    return None
