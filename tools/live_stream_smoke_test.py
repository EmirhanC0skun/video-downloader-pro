# -*- coding: utf-8 -*-
"""Manual, bounded live resolver and real-media smoke test.

This tool intentionally does not concatenate, mux, or retain full media files.
It resolves fifteen configured field URLs and downloads either a bounded media
segment sample or a bounded MiB budget. It is a manual operator tool, not a CI test.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import VideoDownloadEngine, extract_m3u8_info
from extractor import resolve_film_page


MAX_MEDIA_SEGMENTS = 12
MAX_TARGET_MIB = 100
DEFAULT_WORKERS = 4
DEFAULT_TIMEOUT = 20
TARGETS = [
    {"name": "Jetfilmizle", "url": "https://jetfilmizle.now/film/jester-2"},
    {"name": "Filmmodu", "url": "https://filmmodu.live/film/orumcek-adam-eve-donus-yok#player"},
    {"name": "Dizilla", "url": "https://dizilla.now/reacher-1-sezon-1-bolum-c06"},
    {"name": "RoketDizi", "url": "https://roketdizi.life/dizi/dark-matter-2024/sezon-2/bolum-2"},
    {"name": "Yabancidizi", "url": "https://yabancidizi.news/dizi/the-gentlemen-2024/sezon-2/bolum-1"},
    {"name": "Dizibox", "url": "https://www.dizibox.live/stranger-things-1-sezon-1-bolum-hd-izle/"},
    {"name": "SezonlukDizi", "url": "https://sezonlukdizi.cc/silo/3-sezon-10-bolum.html"},
    {"name": "Bicaps", "url": "https://www.bicaps.live/filmler/valhalla.html"},
    {"name": "FullHDFilmizlesene", "url": "https://www.fullhdfilmizlesene.now/film/baslangic/"},
    {"name": "FullHDFilmizle.mom", "url": "https://www.fullhdfilmizle.mom/drama-2026-izle/"},
    {"name": "Diziyou", "url": "https://www.diziyou.one/furious-1-sezon-3-bolum/"},
    {"name": "HDFilmcehennemi", "url": "https://www.hdfilmcehennemi.nl/1-labirent-son-isyan-hd-film-izle-hdf-hdf-7/"},
    {"name": "720pizle", "url": "https://720pizle.my/izle/the-banker"},
    {"name": "Dizitime", "url": "https://dizitime.news/fightland/1-sezon-6-bolum-izle"},
    {"name": "Dizipal", "url": "https://dizipal1579.com/bolum/game-of-thrones-5x6-c03"},
]


def sanitized_url(url: str) -> str:
    """Keep origin/path context while never reporting signed query values."""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def redacted_error(exc: BaseException) -> str:
    """Format an exception without retaining signed query or fragment values."""
    message = str(exc)
    message = re.sub(
        r"https?://[^\s'\"<>]+",
        lambda match: sanitized_url(match.group(0)),
        message,
    )
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded live resolver and HLS segment smoke test")
    parser.add_argument(
        "--segments",
        type=int,
        default=MAX_MEDIA_SEGMENTS,
        help=f"Media segments per rendition (1-{MAX_MEDIA_SEGMENTS}; default: {MAX_MEDIA_SEGMENTS})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Bounded segment workers per rendition (1-16; default: 4)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--target-mib",
        type=int,
        default=0,
        help=f"Approximate download budget per selected rendition (1-{MAX_TARGET_MIB} MiB)",
    )
    parser.add_argument(
        "--primary-only",
        action="store_true",
        help="Download one representative playable rendition per page",
    )
    parser.add_argument("--site", help="Run only a matching target name or hostname")
    parser.add_argument("--keep-samples", action="store_true")
    parser.add_argument("--report", type=Path, help="Write a redacted JSON report")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.segments <= MAX_MEDIA_SEGMENTS:
        parser.error(f"--segments must be between 1 and {MAX_MEDIA_SEGMENTS}")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not 0 <= args.target_mib <= MAX_TARGET_MIB:
        parser.error(f"--target-mib must be between 1 and {MAX_TARGET_MIB}")
    return args


def _safe_headers(result: dict[str, Any]) -> dict[str, str]:
    headers = dict(result.get("video_headers") or result.get("custom_headers") or {})
    headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    return headers


def _transport_headers(headers: dict[str, Any]) -> dict[str, str]:
    clean = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() in {"aes_key", "aes_iv"}:
            continue
        if isinstance(value, (str, int, float)):
            clean[str(key)] = str(value)
    return clean


def _looks_like_init_segment(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".init", ".init.mp4", ".cmfv", ".cmfa")) or "/init." in path


def select_sample_urls(segment_urls: list[str], media_count: int) -> tuple[list[str], bool, int]:
    """Return an optional initialization object plus up to media_count media entries."""
    if not segment_urls:
        return [], False, 0
    has_init = len(segment_urls) > 1 and _looks_like_init_segment(segment_urls[0])
    media_urls = segment_urls[1:] if has_init else segment_urls
    selected_media = media_urls[:media_count]
    selected = ([segment_urls[0]] if has_init else []) + selected_media
    return selected, has_init, len(selected_media)


def _resolve_segment_urls(source_url: str, headers: dict[str, str], supplied: list[str] | None) -> list[str]:
    if supplied:
        return list(supplied)
    if not source_url:
        return []
    return list(extract_m3u8_info(source_url, custom_headers=headers) or [])


def _source_key(source_url: str, segments: list[str] | None) -> str:
    if source_url:
        return source_url
    return segments[0] if segments else ""


def _source_keys(source_url: str, segments: list[str] | None) -> set[str]:
    keys = set()
    if source_url:
        keys.add(source_url)
    if segments:
        keys.add(segments[0])
    return keys


def primary_video_is_distinct(
    video_url: str,
    video_segments: list[str] | None,
    audio_tracks: list[dict[str, Any]],
) -> bool:
    """Return whether video represents a source not already exposed as a muxed track."""
    video_keys = _source_keys(video_url, video_segments)
    if not video_keys:
        return False
    audio_keys = set()
    for track in audio_tracks:
        audio_keys.update(_source_keys(
            track.get("sample_segment_url") or track.get("url") or "",
            track.get("segments"),
        ))
        audio_keys.update(_source_keys(
            track.get("video_url") or "",
            track.get("video_segments"),
        ))
    return video_keys.isdisjoint(audio_keys)


def _stream_sample(
    engine: VideoDownloadEngine,
    label: str,
    segment_urls: list[str],
    headers: dict[str, str],
    sample_dir: Path,
    media_count: int,
    workers: int,
    target_bytes: int = 0,
) -> dict[str, Any]:
    if target_bytes:
        has_init = len(segment_urls) > 1 and _looks_like_init_segment(segment_urls[0])
        selected_urls = list(segment_urls)
        requested_media = 0
    else:
        selected_urls, has_init, requested_media = select_sample_urls(segment_urls, media_count)
    result: dict[str, Any] = {
        "label": label,
        "kind": "hls",
        "source": sanitized_url(segment_urls[0]) if segment_urls else "",
        "initialization_entry": has_init,
        "requested_media_segments": requested_media,
        "downloaded_entries": 0,
        "downloaded_bytes": 0,
        "target_bytes": target_bytes,
        "elapsed_seconds": 0.0,
        "mib_per_second": 0.0,
        "ok": False,
        "error": "",
    }
    if not selected_urls:
        result["error"] = "No media segments were available"
        return result

    rendition_dir = sample_dir / label
    rendition_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        (index, segment_url, str(rendition_dir / f"segment_{index:03d}.sample"))
        for index, segment_url in enumerate(selected_urls)
    ]
    started = time.monotonic()
    attempted_tasks = []
    failed_indices = []
    completed = 0
    if target_bytes:
        downloaded_so_far = 0
        media_downloaded = 0
        for task in tasks:
            attempted_tasks.append(task)
            task_completed, _task_bytes, task_failures = engine.download_stream_segments(
                [task],
                headers=headers,
                thread_count=1,
            )
            completed += task_completed
            failed_indices.extend(task_failures)
            path = Path(task[2])
            if path.is_file() and path.stat().st_size > 0:
                downloaded_so_far += path.stat().st_size
                if not (has_init and task[0] == 0):
                    media_downloaded += 1
            if task_failures:
                break
            if media_downloaded and downloaded_so_far >= target_bytes:
                break
        requested_media = media_downloaded
    else:
        attempted_tasks = tasks
        completed, _downloaded_bytes, failed_indices = engine.download_stream_segments(
            tasks,
            headers=headers,
            thread_count=workers,
        )
    elapsed = max(time.monotonic() - started, 0.001)
    valid_files = [
        Path(path)
        for _, _, path in attempted_tasks
        if Path(path).is_file() and Path(path).stat().st_size > 0
    ]
    bytes_on_disk = sum(path.stat().st_size for path in valid_files)
    result.update({
        "downloaded_entries": len(valid_files),
        "downloaded_bytes": bytes_on_disk,
        "elapsed_seconds": round(elapsed, 3),
        "mib_per_second": round(bytes_on_disk / elapsed / (1024 * 1024), 3),
        "requested_media_segments": requested_media,
    })
    if (
        completed == len(attempted_tasks)
        and not failed_indices
        and len(valid_files) == len(attempted_tasks)
        and (not target_bytes or requested_media > 0)
    ):
        result["ok"] = True
    else:
        result["error"] = (
            f"Incomplete sample: {len(valid_files)}/{len(attempted_tasks)} entries; "
            f"failed={failed_indices}"
        )
    return result


def _direct_range_probe(
    url: str,
    headers: dict[str, str],
    timeout: int,
    target_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    probe_headers = _transport_headers(headers)
    result: dict[str, Any] = {
        "label": "video",
        "kind": "direct",
        "source": sanitized_url(url),
        "requested_media_segments": 0,
        "downloaded_entries": 0,
        "downloaded_bytes": 0,
        "target_bytes": target_bytes,
        "elapsed_seconds": 0.0,
        "mib_per_second": 0.0,
        "ok": False,
        "error": "",
    }
    started = time.monotonic()
    try:
        downloaded = 0
        total_size = None
        while downloaded < target_bytes:
            range_end = target_bytes - 1
            probe_headers["Range"] = f"bytes={downloaded}-{range_end}"
            with requests.get(url, headers=probe_headers, timeout=timeout, stream=True) as response:
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range, re.IGNORECASE)
                if response.status_code != 206 or not match or int(match.group(1)) != downloaded:
                    result["error"] = (
                        f"Range not honored: HTTP {response.status_code}, "
                        f"Content-Range={content_range!r}"
                    )
                    return result
                response_end = int(match.group(2))
                total_size = int(match.group(3)) if match.group(3) != "*" else None
                before = downloaded
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        downloaded += len(chunk)
                    if downloaded >= target_bytes:
                        break
                if downloaded == before:
                    result["error"] = "Range response had no body"
                    return result
                if total_size is not None and downloaded >= total_size:
                    break
                if downloaded <= response_end:
                    result["error"] = "Range response ended before its declared Content-Range"
                    return result
        elapsed = max(time.monotonic() - started, 0.001)
        expected_bytes = min(target_bytes, total_size) if total_size is not None else target_bytes
        result.update({
            "downloaded_entries": 1,
            "downloaded_bytes": downloaded,
            "elapsed_seconds": round(elapsed, 3),
            "mib_per_second": round(downloaded / elapsed / (1024 * 1024), 3),
            "ok": downloaded >= expected_bytes,
        })
        if not result["ok"]:
            result["error"] = "Range response had no body"
    except requests.RequestException as exc:
        result["error"] = redacted_error(exc)
    return result


def _probe_subtitles(
    subtitles: list[dict[str, Any]],
    default_headers: dict[str, str],
    timeout: int,
) -> list[dict[str, Any]]:
    probes = []
    for index, subtitle in enumerate(subtitles):
        subtitle_url = subtitle.get("url") if isinstance(subtitle, dict) else ""
        if not subtitle_url:
            continue
        headers = _transport_headers(default_headers)
        headers.update(_transport_headers(subtitle.get("headers") or {}))
        probe: dict[str, Any] = {
            "name": subtitle.get("name") or subtitle.get("label") or f"subtitle-{index + 1}",
            "language": subtitle.get("lang") or "",
            "source": sanitized_url(subtitle_url),
            "status": None,
            "content_type": "",
            "ok": False,
        }
        try:
            with requests.get(subtitle_url, headers=headers, timeout=timeout, stream=True) as response:
                probe["status"] = response.status_code
                probe["content_type"] = response.headers.get("Content-Type", "")
                probe["ok"] = response.status_code == 200
        except requests.RequestException as exc:
            probe["error"] = redacted_error(exc)
        probes.append(probe)
    return probes


def run_target(target: dict[str, str], args: argparse.Namespace, base_dir: Path) -> dict[str, Any]:
    name = target["name"]
    result: dict[str, Any] = {
        "name": name,
        "page": sanitized_url(target["url"]),
        "resolve_ok": False,
        "audio_tracks": [],
        "subtitles": [],
        "renditions": [],
        "error": "",
    }
    try:
        resolved = resolve_film_page(target["url"])
    except Exception as exc:
        result["error"] = f"Resolve {redacted_error(exc)}"
        return result
    if not resolved or not resolved.get("success"):
        result["error"] = (resolved or {}).get("error_message") or "Resolver returned no playable result"
        return result

    result["resolve_ok"] = True
    headers = _safe_headers(resolved)
    audio_tracks = resolved.get("audio_tracks") or []
    result["audio_tracks"] = [
        {
            "name": track.get("name") or "Audio",
            "language": track.get("lang") or track.get("language") or "",
        }
        for track in audio_tracks
    ]
    result["subtitles"] = _probe_subtitles(
        resolved.get("subtitles") or [],
        headers,
        args.timeout,
    )

    safe_name = "".join(char if char.isalnum() else "_" for char in name).strip("_")
    sample_dir = base_dir / safe_name
    engine = VideoDownloadEngine()
    video_url = resolved.get("video_url") or ""
    direct_file = bool(resolved.get("direct_file")) or (
        video_url.lower().split("?", 1)[0].endswith((".mp4", ".mkv"))
    )
    supplied_video_segments = resolved.get("video_segments")
    target_bytes = args.target_mib * 1024 * 1024
    if direct_file:
        result["renditions"].append(
            _direct_range_probe(video_url, headers, args.timeout, target_bytes or 1024 * 1024)
        )
    elif primary_video_is_distinct(video_url, supplied_video_segments, audio_tracks):
        try:
            video_segments = _resolve_segment_urls(
                video_url,
                headers,
                supplied_video_segments,
            )
            result["renditions"].append(
                _stream_sample(
                    engine,
                    "video",
                    video_segments,
                    headers,
                    sample_dir,
                    args.segments,
                    args.workers,
                    target_bytes,
                )
            )
        except Exception as exc:
            result["renditions"].append({
                "label": "video",
                "ok": False,
                "error": f"Video sample {redacted_error(exc)}",
            })

    seen_audio_sources = set()
    for index, track in enumerate(audio_tracks):
        if args.primary_only and result["renditions"]:
            break
        track_headers = dict(headers)
        track_headers.update(track.get("headers") or {})
        source_url = track.get("sample_segment_url") or track.get("url") or ""
        source_key = source_url or "\n".join(track.get("segments") or [])
        if not source_key or source_key in seen_audio_sources:
            continue
        seen_audio_sources.add(source_key)
        label = f"audio_{index + 1}_{track.get('lang') or 'und'}"
        try:
            audio_segments = _resolve_segment_urls(
                source_url,
                track_headers,
                track.get("segments"),
            )
            result["renditions"].append(
                _stream_sample(
                    engine,
                    label,
                    audio_segments,
                    track_headers,
                    sample_dir,
                    args.segments,
                    args.workers,
                    target_bytes,
                )
            )
        except Exception as exc:
            result["renditions"].append({
                "label": label,
                "ok": False,
                "error": f"Audio sample {redacted_error(exc)}",
            })

    if not args.keep_samples:
        shutil.rmtree(sample_dir, ignore_errors=True)
    return result


def result_is_success(result: dict[str, Any]) -> bool:
    renditions = result.get("renditions") or []
    subtitles = result.get("subtitles") or []
    return bool(
        result.get("resolve_ok")
        and renditions
        and all(item.get("ok") for item in renditions)
        and all(item.get("ok") for item in subtitles)
    )


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\nPlatform               Resolve  Renditions  Subtitles  Result")
    print("-" * 78)
    for result in results:
        renditions = result.get("renditions") or []
        subtitle_results = result.get("subtitles") or []
        rendition_state = f"{sum(bool(item.get('ok')) for item in renditions)}/{len(renditions)}"
        subtitle_state = f"{sum(bool(item.get('ok')) for item in subtitle_results)}/{len(subtitle_results)}"
        status = "OK" if result_is_success(result) else "FAIL"
        details = [item.get("error", "") for item in renditions if item.get("error")]
        details.extend(
            f"subtitle {item.get('name')}: HTTP {item.get('status')} {item.get('error', '')}".strip()
            for item in subtitle_results
            if not item.get("ok")
        )
        detail = result.get("error") or "; ".join(details)
        resolve_state = "OK" if result.get("resolve_ok") else "FAIL"
        print(
            f"{result['name']:<22} {resolve_state:<8} {rendition_state:<11} "
            f"{subtitle_state:<10} {status} {detail[:80]}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.list:
        for index, target in enumerate(TARGETS, start=1):
            print(f"{index:2d}. {target['name']}: {sanitized_url(target['url'])}")
        return 0

    targets = TARGETS
    if args.site:
        query = args.site.lower()
        targets = [
            target
            for target in TARGETS
            if query in target["name"].lower() or query in target["url"].lower()
        ]
        if not targets:
            print(f"No configured target matches {args.site!r}", file=sys.stderr)
            return 2

    sample_root = PROJECT_ROOT / "temp_smoke_test"
    sample_root.mkdir(exist_ok=True)
    results = [run_target(target, args, sample_root) for target in targets]
    print_summary(results)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not args.keep_samples and sample_root.exists() and not any(sample_root.iterdir()):
        sample_root.rmdir()
    all_ok = all(result_is_success(result) for result in results)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
