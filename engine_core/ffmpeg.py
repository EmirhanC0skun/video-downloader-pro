# -*- coding: utf-8 -*-
"""
Video Downloader Pro — FFmpeg, Subtitles, and Media Conversion.
"""

import os
import re
import sys
import shutil
import subprocess
from urllib.parse import urljoin
import requests

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None

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
    from exceptions import FFmpegNotFoundError
except ImportError:
    try:
        from core.exceptions import FFmpegNotFoundError
    except ImportError:
        class FFmpegNotFoundError(Exception): pass

logger = get_logger("engine_core.ffmpeg")


def _close_response(response):
    if response is not None and hasattr(response, "close"):
        try:
            response.close()
        except Exception:
            logger.debug("Subtitle response could not be closed", exc_info=True)


def _transport_headers(headers):
    """Remove internal HLS metadata and normalize values for HTTP clients."""
    clean = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() in {"aes_key", "aes_iv", "aes_media_sequence"}:
            continue
        if isinstance(value, (str, int, float)):
            clean[str(key)] = str(value)
    return clean


def write_concat_file(concat_path, segment_paths, segment_durations=None):
    """Write an FFmpeg concat-demuxer list while preserving HLS timeline durations."""
    normalized_paths = []
    for path in segment_paths:
        absolute_path = os.path.abspath(os.fspath(path))
        if "\n" in absolute_path or "\r" in absolute_path:
            raise ValueError("Concat segment path cannot contain a newline.")
        normalized_paths.append(absolute_path)
    if not normalized_paths:
        raise ValueError("Concat list requires at least one segment path.")
    if segment_durations is not None and len(segment_durations) != len(normalized_paths):
        raise ValueError("Concat durations must align with segment paths.")

    with open(concat_path, "w", encoding="utf-8", newline="\n") as concat_file:
        concat_file.write("ffconcat version 1.0\n")
        for index, absolute_path in enumerate(normalized_paths):
            escaped_path = absolute_path.replace("'", "'\\''")
            concat_file.write(f"file '{escaped_path}'\n")
            duration = segment_durations[index] if segment_durations is not None else None
            if duration is not None and float(duration) > 0:
                concat_file.write(f"duration {float(duration):.15g}\n")


def _run_subprocess(*args, **kwargs):
    """Backwards-compatibility bridge with unittest.mock patching 'engine.subprocess.run'."""
    # FFmpeg Windows konsolunda dosya adlarini OEM/yerel kod sayfasiyla
    # yazabilir. text=True sistem cp1254 decoder'ina birakilirsa reader thread
    # UnicodeDecodeError ile olur ve gercek stderr kaybolur. Tanilamayi koru.
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    eng = sys.modules.get("engine")
    if eng and hasattr(eng, "subprocess") and hasattr(eng.subprocess, "run"):
        return eng.subprocess.run(*args, **kwargs)
    return subprocess.run(*args, **kwargs)



def vtt_to_srt(vtt_text):
    """
    WebVTT formatındaki altyazıyı standart SubRip (SRT) formatına dönüştürür.
    """
    if not vtt_text:
        return ""
    lines = vtt_text.replace('\r\n', '\n').split('\n')
    srt_lines = []
    sub_index = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.startswith('STYLE') or line.startswith('REGION'):
            i += 1
            continue
        
        time_match = re.search(r'(?:(\d{2}:)?(\d{2}:\d{2}\.\d{3}))\s*-->\s*(?:(\d{2}:)?(\d{2}:\d{2}\.\d{3}))', line)
        if time_match:
            def fix_time(t_str):
                if not t_str:
                    return "00:00:00,000"
                if t_str.count(':') == 1:
                    t_str = "00:" + t_str
                return t_str.replace('.', ',')

            parts = line.split('-->')
            start_t = fix_time(parts[0].strip().split()[0])
            end_t = fix_time(parts[1].strip().split()[0])

            srt_lines.append(str(sub_index))
            srt_lines.append(f"{start_t} --> {end_t}")
            sub_index += 1

            i += 1
            while i < len(lines) and lines[i].strip():
                clean_text = re.sub(r'<[^>]+>', '', lines[i].strip())
                if clean_text:
                    srt_lines.append(clean_text)
                i += 1
            srt_lines.append('')
        else:
            i += 1

    return '\n'.join(srt_lines)



def decode_subtitle_bytes(raw_bytes: bytes) -> str:
    """
    Ham altyazı baytlarını Türkçe karakterleri (ş, ğ, ı, ö, ü, ç) bozmadan temiz UTF-8 metne dönüştürür.
    """
    if not raw_bytes:
        return ""
    for enc in ("utf-8-sig", "utf-8", "windows-1254", "iso-8859-9", "cp1252"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def fetch_and_save_subtitle(subtitles, output_filepath, session=None, default_headers=None, log_callback=None):
    """
    Verilen altyazı adayları listesinden en uygun altyazıyı indirir, UTF-8 .srt formatına çevirip
    hem MP4'ün yanına .tr.srt / .srt olarak kaydeder hem de FFmpeg muxer için dosya yolunu döndürür.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    if not subtitles:
        return None

    sub_candidates = list(subtitles) if isinstance(subtitles, (list, tuple)) else [subtitles]

    def _sub_priority(s):
        if not isinstance(s, dict):
            return (5, 0)
        name = (s.get("name") or s.get("label") or "")
        lang = (s.get("lang") or "")
        kind = (s.get("kind") or "subtitles").lower()
        nl = f"{name} {lang}".lower()
        forced = bool(s.get("forced")) or (kind == "captions") or any(k in nl for k in ["forced", "tabela", "sign", "ekran"])
        is_tr = any(k in nl for k in ["tur", "türk", "tr"])
        is_en = any(k in nl for k in ["eng", "ing"])

        # Öncelik Sıralaması:
        # Tier 0: Türkçe Tam Diyalog (default işaretli)
        # Tier 1: Türkçe Tam Diyalog
        # Tier 2: Türkçe Sadece Zorunlu / Tabela (Forced)
        # Tier 3: İngilizce Tam Diyalog
        # Tier 4: İngilizce Zorunlu
        # Tier 5: Diğer Diller
        if is_tr:
            if not forced:
                return (0 if s.get("default") else 1, 0)
            return (2, 0)
        if is_en:
            return (3 if not forced else 4, 0)
        return (5 if not forced else 6, 0)

    sub_candidates.sort(key=_sub_priority)

    base_no_ext = os.path.splitext(output_filepath)[0]
    owns_session = session is None
    sess = session or requests.Session()

    def close_owned_session():
        if owns_session:
            try:
                sess.close()
            except Exception:
                logger.debug("Owned subtitle session could not be closed", exc_info=True)

    for s_item in sub_candidates:
        s_url = s_item.get("url") if isinstance(s_item, dict) else s_item
        if not s_url or not isinstance(s_url, str) or not s_url.startswith("http"):
            continue
        source_headers = (s_item.get("headers") if isinstance(s_item, dict) else None) or default_headers or {}
        s_head = _transport_headers(source_headers)
        try:
            r_sub = None
            if c_requests:
                try:
                    r_sub = c_requests.get(s_url, headers=s_head, impersonate="chrome124", timeout=10)
                except Exception:
                    logger.debug("Subtitle curl request failed: %s", s_url, exc_info=True)
                    r_sub = None
            if not r_sub or r_sub.status_code != 200:
                _close_response(r_sub)
                r_sub = sess.get(s_url, headers=s_head, timeout=10)

            if r_sub and r_sub.status_code == 200 and len(r_sub.content) > 10:
                raw_text = decode_subtitle_bytes(r_sub.content)
                if "#EXTM3U" in raw_text:
                    vtt_segs = [urljoin(s_url, line.strip()) for line in raw_text.splitlines() if line.strip() and not line.startswith("#")]
                    collected_vtt = []
                    for v_url in vtt_segs:
                        r_v = None
                        try:
                            r_v = (c_requests.get(v_url, headers=s_head, impersonate="chrome124", timeout=10) if c_requests else sess.get(v_url, headers=s_head, timeout=10))
                            if r_v and r_v.status_code == 200:
                                collected_vtt.append(decode_subtitle_bytes(r_v.content))
                        except Exception:
                            logger.debug("Subtitle segment request failed: %s", v_url, exc_info=True)
                            continue
                        finally:
                            _close_response(r_v)
                    if collected_vtt:
                        raw_text = "\n".join(collected_vtt)

                srt_content = vtt_to_srt(raw_text) if "WEBVTT" in raw_text else raw_text
                if not srt_content.strip() or "#EXTM3U" in srt_content:
                    continue

                srt_out_path = base_no_ext + ".srt"
                with open(srt_out_path, "w", encoding="utf-8") as f_srt:
                    f_srt.write(srt_content)

                try:
                    tr_srt_path = base_no_ext + ".tr.srt"
                    with open(tr_srt_path, "w", encoding="utf-8") as f_tr:
                        f_tr.write(srt_content)
                except Exception:
                    logger.debug("Turkish subtitle sidecar could not be written", exc_info=True)

                s_name = s_item.get("name", "Türkçe") if isinstance(s_item, dict) else "Türkçe"
                log(f"[+] Altyazı dosyası başarıyla indirildi ({s_name}): {os.path.basename(srt_out_path)}")
                close_owned_session()
                return srt_out_path
        except Exception as sub_e:
            log(f"[!] Altyazı indirme uyarısı ({str(s_url)[:40]}): {sub_e}")
            logger.warning("Subtitle download failed: %s", s_url, exc_info=True)
        finally:
            _close_response(r_sub)

    close_owned_session()
    return None


def get_ffmpeg_path():
    """
    Sistemde yüklü FFmpeg'i, Android uygulama dizinlerini, yerel /data/local/tmp veya native JNI binary'sini arar.
    """
    # 1. Android uygulama önbellek ve veri dizinleri (SELinux çalıştırma izni verir)
    candidate_dirs = []
    _tmpdir = os.environ.get("TMPDIR", "")
    if _tmpdir:
        candidate_dirs.append(_tmpdir)
    candidate_dirs.extend([
        "/data/user/0/com.videodownloaderpro.videodownloaderpro/cache",
        "/data/data/com.videodownloaderpro.videodownloaderpro/cache",
        "/data/user/0/com.videodownloaderpro.videodownloaderpro/files",
        "/data/data/com.videodownloaderpro.videodownloaderpro/files",
        "/data/local/tmp"
    ])

    for cd in candidate_dirs:
        ff = os.path.join(cd, "ffmpeg")
        if os.path.exists(ff):
            try:
                os.chmod(ff, 0o755)
            except Exception:
                logger.debug("[engine.py:223] get_ffmpeg_path() sessiz istisna yutuldu", exc_info=True)
            return ff

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        logger.debug(f"Using system FFmpeg: {sys_ffmpeg}")
        return sys_ffmpeg

    try:
        import glob
        for f in glob.glob("/data/app/**/libffmpeg.so", recursive=True):
            if os.path.exists(f):
                return f
    except Exception:
        logger.debug("[engine.py:237] get_ffmpeg_path() sessiz istisna yutuldu", exc_info=True)

    if imageio_ffmpeg is not None:
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            logger.debug(f"Using imageio_ffmpeg binary: {exe}")
            return exe
        except Exception as ex:
            logger.warning(f"Failed to get imageio_ffmpeg executable: {ex}")
    logger.warning("FFmpeg binary could not be found on system.")
    return None




class FFmpegMixin:
    """FFmpeg remuxing, multi-audio multiplexing, and media conversion mixin."""

    def mux_video_and_audio(self, video_concat_path, audio_concat_path, output_filepath, subtitle_path=None, log_callback=None):
        """
        FFmpeg ile indirilen saf video, saf ses ve opsiyonel altyazı akışlarını tek bir .mp4 dosyasına birleştirir.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        out_dir = os.path.dirname(output_filepath)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise FFmpegNotFoundError("FFmpeg bulunamadığı için çoklu ses kanalları birleştirilemedi.")

        log("[FFmpeg] Ses ve Görüntü kanalları tam senkron birleştiriliyor (Muxing)...")

        def _get_input_args(path):
            abs_p = os.path.abspath(path)
            if abs_p.lower().endswith(".txt"):
                return ["-f", "concat", "-safe", "0", "-i", abs_p]
            return ["-i", abs_p]

        cmd = [ffmpeg_bin, "-y", "-nostats", "-loglevel", "error"]
        cmd.extend(_get_input_args(video_concat_path))
        cmd.extend(_get_input_args(audio_concat_path))

        if subtitle_path and os.path.exists(subtitle_path):
            log(f"[FFmpeg] Altyazı tespit edildi, MP4 içine gömülüyor: {os.path.basename(subtitle_path)}")
            cmd.extend([
                "-i", os.path.abspath(subtitle_path),
                "-c:v", "copy",
                "-c:a", "copy",
                "-c:s", "mov_text",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-map", "2:s:0?",
                "-metadata:s:s:0", "language=tur",
                "-metadata:s:s:0", "title=Türkçe Altyazı",
                "-disposition:s:0", "default"
            ])
        else:
            cmd.extend([
                "-c:v", "copy",
                "-c:a", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0"
            ])

        cmd.extend([
            "-movflags", "+faststart",
            "-shortest",
            os.path.abspath(output_filepath)
        ])

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        proc_env = os.environ.copy()
        if sys.platform != "win32":
            ff_dir = os.path.dirname(ffmpeg_bin)
            proc_env["LD_LIBRARY_PATH"] = f"{ff_dir}:/data/local/tmp:/data/user/0/com.videodownloaderpro.videodownloaderpro/cache:/data/data/com.videodownloaderpro.videodownloaderpro/cache:" + proc_env.get("LD_LIBRARY_PATH", "")

        proc = None
        try:
            proc = _run_subprocess(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=creationflags, env=proc_env, timeout=600)
        except subprocess.TimeoutExpired as e_to:
            log(f"[!] FFmpeg birleştirme zaman aşımına uğradı (600 sn): {e_to}")
        except Exception as e_proc:
            log(f"[!] FFmpeg çalıştırma uyarısı: {e_proc}")

        if proc and proc.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
            log(f"[+] Film sesli olarak başarıyla oluşturuldu: {os.path.basename(output_filepath)}")
            return True
        else:
            # Fallback 1: AAC re-encode if ADTS filter failed
            try:
                cmd_fb = [ffmpeg_bin, "-y", "-nostats", "-loglevel", "error"]
                cmd_fb.extend(_get_input_args(video_concat_path))
                cmd_fb.extend(_get_input_args(audio_concat_path))
                if subtitle_path and os.path.exists(subtitle_path):
                    cmd_fb.extend(["-i", os.path.abspath(subtitle_path)])
                    cmd_fb.extend([
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-c:s", "mov_text",
                        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0?",
                        "-metadata:s:s:0", "language=tur",
                        "-metadata:s:s:0", "title=Türkçe Altyazı",
                        "-disposition:s:0", "default"
                    ])
                else:
                    cmd_fb.extend([
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-map", "0:v:0", "-map", "1:a:0"
                    ])
                cmd_fb.extend([
                    "-movflags", "+faststart",
                    "-shortest", os.path.abspath(output_filepath)
                ])
                proc_fb = _run_subprocess(cmd_fb, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=creationflags, env=proc_env, timeout=600)
                if proc_fb.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
                    log(f"[+] Film sesli olarak başarıyla oluşturuldu (AAC encode): {os.path.basename(output_filepath)}")
                    return True
            except Exception:
                logger.debug("[engine.py:951] mux_video_and_audio() sessiz istisna yutuldu", exc_info=True)

            if proc:
                log(f"[HATA] FFmpeg Muxing Hatası: {proc.stderr[:300]}")
            else:
                log("[HATA] FFmpeg ses ve video birleştirme işlemi başarısız oldu.")

            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except OSError:
                    logger.debug("Failed mux output could not be removed", exc_info=True)
            return False

    def mux_multi_audio_and_video(self, v_concat_path, audio_concats, output_filepath, subtitle_path=None, log_callback=None, has_muxed_track0=False, track0_info=None):
        """
        FFmpeg ile saf video, birden çok ses kanalı ve altyazıyı çok kanallı MP4 dosyası olarak birleştirir.
        `has_muxed_track0=True` ise v_concat_path içindeki 0:a:0 ilk ses kanalı olarak kullanılır.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        out_dir = os.path.dirname(output_filepath)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise FFmpegNotFoundError("FFmpeg bulunamadığı için çoklu ses kanalları birleştirilemedi.")

        log("[FFmpeg] Çift Sesli (Dublaj + Orijinal) ve Altyazılı MP4 oluşturuluyor...")

        def _get_input_args(path):
            abs_p = os.path.abspath(path)
            if abs_p.lower().endswith(".txt"):
                return ["-f", "concat", "-safe", "0", "-i", abs_p]
            return ["-i", abs_p]

        cmd = [ffmpeg_bin, "-y", "-nostats", "-loglevel", "error"]
        cmd.extend(_get_input_args(v_concat_path))
        for a_c, _, _ in audio_concats:
            cmd.extend(_get_input_args(a_c))

        if subtitle_path and os.path.exists(subtitle_path):
            cmd.extend(["-i", os.path.abspath(subtitle_path)])

        # MP4 muxer AAC/ADTS donusumunu gerektiginde otomatik uygular. Filtreyi
        # tum ses stream'lerine zorlamak MP3 tasiyan Dizipal akisini reddeder ve
        # gereksiz tam AAC re-encode fallback'ine (dakikalarca) dusurur.
        cmd.extend(["-c:v", "copy", "-c:a", "copy"])
        if subtitle_path and os.path.exists(subtitle_path):
            cmd.extend(["-c:s", "mov_text"])

        cmd.extend(["-map", "0:v:0"])

        if has_muxed_track0:
            t0_name, t0_lang = track0_info if track0_info else ("Türkçe Dublaj", "tur")
            cmd.extend([
                "-map", "0:a:0",
                "-metadata:s:a:0", f"language={t0_lang}",
                "-metadata:s:a:0", f"title={t0_name}"
            ])
            for idx, (_, name, lang) in enumerate(audio_concats):
                cmd.extend([
                    "-map", f"{idx+1}:a:0",
                    f"-metadata:s:a:{idx+1}", f"language={lang}",
                    f"-metadata:s:a:{idx+1}", f"title={name}"
                ])
        else:
            for idx, (_, name, lang) in enumerate(audio_concats):
                cmd.extend([
                    "-map", f"{idx+1}:a:0",
                    f"-metadata:s:a:{idx}", f"language={lang}",
                    f"-metadata:s:a:{idx}", f"title={name}"
                ])

        if subtitle_path and os.path.exists(subtitle_path):
            sub_input_idx = 1 + len(audio_concats)
            cmd.extend([
                "-map", f"{sub_input_idx}:s:0?",
                "-metadata:s:s:0", "language=tur",
                "-metadata:s:s:0", "title=Türkçe Altyazı",
                "-disposition:s:0", "default"
            ])

        cmd.extend(["-movflags", "+faststart", "-shortest", os.path.abspath(output_filepath)])

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        proc_env = os.environ.copy()
        if sys.platform != "win32":
            ff_dir = os.path.dirname(ffmpeg_bin)
            proc_env["LD_LIBRARY_PATH"] = f"{ff_dir}:/data/local/tmp:/data/user/0/com.videodownloaderpro.videodownloaderpro/cache:/data/data/com.videodownloaderpro.videodownloaderpro/cache:" + proc_env.get("LD_LIBRARY_PATH", "")

        proc = None
        try:
            proc = _run_subprocess(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=creationflags, env=proc_env, timeout=600)
        except subprocess.TimeoutExpired as e_to:
            log(f"[!] FFmpeg çoklu ses birleştirme zaman aşımına uğradı (600 sn): {e_to}")
        except Exception as e_proc:
            log(f"[!] FFmpeg çalıştırma uyarısı: {e_proc}")

        if proc and proc.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
            log(f"[+] Film çift sesli olarak başarıyla oluşturuldu: {os.path.basename(output_filepath)}")
            return True
        else:
            # Fallback: re-encode audio to AAC
            try:
                cmd_fb = [ffmpeg_bin, "-y", "-nostats", "-loglevel", "error"]
                cmd_fb.extend(_get_input_args(v_concat_path))
                for a_c, _, _ in audio_concats:
                    cmd_fb.extend(_get_input_args(a_c))
                if subtitle_path and os.path.exists(subtitle_path):
                    cmd_fb.extend(["-i", os.path.abspath(subtitle_path)])
                cmd_fb.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])
                if subtitle_path and os.path.exists(subtitle_path):
                    cmd_fb.extend(["-c:s", "mov_text"])
                cmd_fb.extend(["-map", "0:v:0"])
                if has_muxed_track0:
                    t0_name, t0_lang = track0_info if track0_info else ("Türkçe Dublaj", "tur")
                    cmd_fb.extend([
                        "-map", "0:a:0",
                        "-metadata:s:a:0", f"language={t0_lang}",
                        "-metadata:s:a:0", f"title={t0_name}"
                    ])
                    for idx, (_, name, lang) in enumerate(audio_concats):
                        cmd_fb.extend([
                            "-map", f"{idx+1}:a:0",
                            f"-metadata:s:a:{idx+1}", f"language={lang}",
                            f"-metadata:s:a:{idx+1}", f"title={name}"
                        ])
                else:
                    for idx, (_, name, lang) in enumerate(audio_concats):
                        cmd_fb.extend([
                            "-map", f"{idx+1}:a:0",
                            f"-metadata:s:a:{idx}", f"language={lang}",
                            f"-metadata:s:a:{idx}", f"title={name}"
                        ])
                if subtitle_path and os.path.exists(subtitle_path):
                    sub_input_idx = 1 + len(audio_concats)
                    cmd_fb.extend([
                        "-map", f"{sub_input_idx}:s:0?",
                        "-metadata:s:s:0", "language=tur",
                        "-metadata:s:s:0", "title=Türkçe Altyazı",
                        "-disposition:s:0", "default"
                    ])
                cmd_fb.extend(["-movflags", "+faststart", "-shortest", os.path.abspath(output_filepath)])
                proc_fb = _run_subprocess(cmd_fb, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=creationflags, env=proc_env, timeout=600)
                if proc_fb.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
                    log(f"[+] Film çift sesli olarak başarıyla oluşturuldu (AAC encode): {os.path.basename(output_filepath)}")
                    return True
            except Exception:
                logger.debug("[engine.py:1070] mux_multi_audio_and_video() sessiz istisna yutuldu", exc_info=True)

            if proc:
                log(f"[HATA] FFmpeg Hatası: {proc.stderr[:300]}")
            else:
                log("[HATA] FFmpeg çoklu ses birleştirme işlemi başarısız oldu.")

            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except OSError:
                    logger.debug("Failed multi-audio output could not be removed", exc_info=True)
            return False



    def convert_media_to_audio(self, input_filepath, output_filepath, audio_format="mp3", bitrate="320k", log_callback=None):
        """
        FFmpeg ile herhangi bir video dosyasından sesi ayıklar ve MP3/WAV formatına dönüştürür.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise FFmpegNotFoundError("FFmpeg bulunamadı.")

        log(f"[FFmpeg] '{os.path.basename(input_filepath)}' dosyası {audio_format.upper()} formatına dönüştürülüyor...")

        cmd = [ffmpeg_bin, "-y", "-nostats", "-loglevel", "error", "-i", os.path.abspath(input_filepath)]
        if audio_format.lower() == "mp3":
            cmd += ["-vn", "-acodec", "libmp3lame", "-b:a", bitrate, os.path.abspath(output_filepath)]
        elif audio_format.lower() == "wav":
            cmd += ["-vn", "-acodec", "pcm_s16le", os.path.abspath(output_filepath)]
        else:
            cmd += ["-vn", os.path.abspath(output_filepath)]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        proc_env = os.environ.copy()
        if sys.platform != "win32":
            ff_dir = os.path.dirname(ffmpeg_bin)
            proc_env["LD_LIBRARY_PATH"] = f"{ff_dir}:/data/local/tmp:" + proc_env.get("LD_LIBRARY_PATH", "")
            proc_env["PATH"] = f"{ff_dir}:/data/local/tmp:" + proc_env.get("PATH", "")

        proc = None
        try:
            proc = _run_subprocess(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=creationflags, env=proc_env, timeout=300)
        except subprocess.TimeoutExpired as e_to:
            log(f"[!] FFmpeg ses dönüştürme zaman aşımına uğradı (300 sn): {e_to}")
            return False, "FFmpeg ses dönüştürme zaman aşımı"
        except Exception as e_proc:
            log(f"[!] FFmpeg çalıştırma uyarısı: {e_proc}")
            return False, str(e_proc)

        if proc and proc.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
            log(f"[+] Dönüştürme tamamlandı: {os.path.basename(output_filepath)}")
            return True, output_filepath
        else:
            err_msg = proc.stderr[:200] if proc else "Bilinmeyen FFmpeg hatası"
            log(f"[HATA] FFmpeg Hatası: {err_msg}")
            return False, err_msg



__all__ = [
    "vtt_to_srt",
    "decode_subtitle_bytes",
    "fetch_and_save_subtitle",
    "write_concat_file",
    "get_ffmpeg_path",
    "FFmpegMixin",
    "_run_subprocess",
]
