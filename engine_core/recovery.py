# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Session Crash Recovery & Stale Temp Disk Hygiene.
Provides state persistence (.vdp_state.json), startup incomplete download scanning,
and garbage collection of orphaned/stale temporary download directories.
"""

import os
import json
import time
import tempfile
from typing import List, Dict, Any, Optional, Tuple

try:
    from logger import get_logger
except ImportError:
    try:
        from core.logger import get_logger
    except ImportError:
        import logging
        def get_logger(name):
            return logging.getLogger(name)

from engine_core.utils import cleanup_filesystem_path, is_valid_segment_file

logger = get_logger("engine_core.recovery")

STATE_FILENAME = ".vdp_state.json"


def get_base_temp_dir() -> str:
    """Returns the primary base temp directory for VideoDownloaderPro."""
    base_dir = os.path.join(tempfile.gettempdir(), ".vdp_temp")
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def write_recovery_state(temp_dir: str, state: Dict[str, Any]) -> bool:
    """
    Writes session download state atomically into the target temp directory.
    Ensures safe JSON dumping using a temporary part file before replacement.
    """
    if not temp_dir or not os.path.isdir(temp_dir):
        return False
    
    state_copy = dict(state)
    if "timestamp" not in state_copy:
        state_copy["timestamp"] = time.time()
    
    target_path = os.path.join(temp_dir, STATE_FILENAME)
    part_path = target_path + ".tmp"
    try:
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump(state_copy, f, ensure_ascii=False, indent=2)
        os.replace(part_path, target_path)
        return True
    except Exception as e:
        logger.debug(f"write_recovery_state error: {e}", exc_info=True)
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                logger.debug("Recovery state part file could not be removed", exc_info=True)
        return False


def update_recovery_progress(temp_dir: str, downloaded_segments: int) -> bool:
    """Updates only the downloaded_segments counter and timestamp in .vdp_state.json."""
    if not temp_dir or not os.path.isdir(temp_dir):
        return False
    state = read_recovery_state(temp_dir)
    if not state:
        return False
    state["downloaded_segments"] = downloaded_segments
    state["timestamp"] = time.time()
    return write_recovery_state(temp_dir, state)


def read_recovery_state(temp_dir: str) -> Optional[Dict[str, Any]]:
    """Reads and parses .vdp_state.json from the specified temp directory."""
    if not temp_dir or not os.path.isdir(temp_dir):
        return None
    state_path = os.path.join(temp_dir, STATE_FILENAME)
    if not os.path.isfile(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug(f"read_recovery_state failed on {state_path}: {e}")
    return None


def delete_recovery_state(temp_dir: str) -> bool:
    """Deletes .vdp_state.json from the temp directory."""
    if not temp_dir:
        return False
    state_path = os.path.join(temp_dir, STATE_FILENAME)
    if os.path.exists(state_path):
        try:
            os.remove(state_path)
            return True
        except OSError:
            return False
    return True


def scan_incomplete_downloads(base_dirs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Scans base temp directories for incomplete download sessions.
    Returns a list of candidate dictionaries containing state and file metrics.
    """
    if base_dirs is None:
        base_dirs = [get_base_temp_dir()]
        # Proje yerel temp/ dizini varsa onu da dahil et
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_temp = os.path.join(proj_root, "temp")
        if os.path.isdir(local_temp) and local_temp not in base_dirs:
            base_dirs.append(local_temp)

    candidates = []
    for b_dir in base_dirs:
        if not os.path.isdir(b_dir):
            continue
        try:
            subdirs = os.listdir(b_dir)
        except OSError:
            continue

        for sub in subdirs:
            full_sub = os.path.join(b_dir, sub)
            if not os.path.isdir(full_sub):
                continue

            state = read_recovery_state(full_sub)
            if not state:
                continue

            # Disk ve segment metriklerini hesapla
            valid_segs = 0
            total_bytes = 0
            try:
                for fname in os.listdir(full_sub):
                    fpath = os.path.join(full_sub, fname)
                    if os.path.isfile(fpath):
                        f_size = os.path.getsize(fpath)
                        total_bytes += f_size
                        if (fname.startswith(("seg_", "v_seg_", "a", "part_")) and 
                                fname.endswith((".tmp", ".ts")) and 
                                is_valid_segment_file(fpath)):
                            valid_segs += 1
            except OSError:
                logger.debug("Recovery directory scan entry could not be read", exc_info=True)

            # Eğer hiç parça inmemişse ve klasör bozuksa atlayabiliriz
            tot_segs = state.get("total_segments", 0)
            rec_downloaded = max(valid_segs, state.get("downloaded_segments", 0))

            out_path = state.get("output_filepath") or ""
            # Eğer nihai çıktı dosyası zaten başarıyla oluşturulmuşsa bu indirme bitmiştir
            if out_path and os.path.exists(out_path) and os.path.getsize(out_path) > 1024 * 1024:
                # Klasör temizlenmeden kalmış olabilir
                continue

            candidates.append({
                "temp_dir": full_sub,
                "title": state.get("title") or sub,
                "url": state.get("url") or "",
                "raw_url": state.get("raw_url") or state.get("url") or "",
                "output_filepath": out_path,
                "total_segments": tot_segs,
                "downloaded_segments": rec_downloaded,
                "bytes_on_disk": total_bytes,
                "size_mb": total_bytes / (1024 * 1024),
                "timestamp": state.get("timestamp", 0),
                "custom_headers": state.get("custom_headers", {}),
                "is_multi_audio": state.get("is_multi_audio", False),
                "audio_tracks": state.get("audio_tracks", []),
                "subtitles": state.get("subtitles", []),
            })

    # En yeni indirmeler en üstte gelsin
    candidates.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return candidates


def cleanup_stale_temp_dirs(base_dirs: Optional[List[str]] = None, max_age_hours: float = 48.0) -> Tuple[int, int]:
    """
    Cleans up stale orphaned temp directories.
    - Directories without .vdp_state.json older than 2 hours are purged.
    - Incomplete downloads with .vdp_state.json older than max_age_hours (default: 48h) are purged.
    Returns (cleaned_count, freed_bytes).
    """
    if base_dirs is None:
        base_dirs = [get_base_temp_dir()]
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_temp = os.path.join(proj_root, "temp")
        if os.path.isdir(local_temp) and local_temp not in base_dirs:
            base_dirs.append(local_temp)

    now = time.time()
    cleaned_count = 0
    freed_bytes = 0

    for b_dir in base_dirs:
        if not os.path.isdir(b_dir):
            continue
        try:
            subdirs = os.listdir(b_dir)
        except OSError:
            continue

        for sub in subdirs:
            full_sub = os.path.join(b_dir, sub)
            if not os.path.isdir(full_sub):
                continue

            try:
                mtime = os.path.getmtime(full_sub)
            except OSError:
                mtime = now

            state = read_recovery_state(full_sub)
            should_clean = False

            if state is None:
                # Durum dosyası olmayan yetim klasörler (2 saatten eskiyse temizle)
                if (now - mtime) > 7200:
                    should_clean = True
            else:
                # Durum dosyası olan ama 48 saatten eski kalmış yetimler
                state_ts = state.get("timestamp", mtime)
                if (now - state_ts) > (max_age_hours * 3600):
                    should_clean = True

            if should_clean:
                # Klasör boyutunu hesapla
                d_size = 0
                try:
                    for root, _, files in os.walk(full_sub):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                d_size += os.path.getsize(fp)
                            except OSError:
                                logger.debug("Stale recovery file size could not be read", exc_info=True)
                except OSError:
                    logger.debug("Stale recovery directory size scan failed", exc_info=True)

                ok = cleanup_filesystem_path(full_sub)
                if ok:
                    cleaned_count += 1
                    freed_bytes += d_size
                    logger.info(f"Stale temp dir purged: {full_sub} ({d_size / (1024*1024):.2f} MB)")

    return cleaned_count, freed_bytes


__all__ = [
    "STATE_FILENAME",
    "get_base_temp_dir",
    "write_recovery_state",
    "update_recovery_progress",
    "read_recovery_state",
    "delete_recovery_state",
    "scan_incomplete_downloads",
    "cleanup_stale_temp_dirs",
]
