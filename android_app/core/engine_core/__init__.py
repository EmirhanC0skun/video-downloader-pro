# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Core Engine Package.
Exposes all submodules, mixins, cryptographic routines, and VideoDownloadEngine.
"""

from engine_core.crypto import (
    derive_hls_iv,
    decrypt_hls_segment,
    AES,
)

from engine_core.utils import (
    _remove_readonly,
    cleanup_filesystem_path,
    sanitize_filename,
    format_human_duration,
    format_human_filesize,
    parse_curl_command,
    parse_segment_url,
    build_segment_url,
    probe_url,
    _close_owned,
    is_valid_segment_file,
    _fast_v4_create_conn,
)

from engine_core.ffmpeg import (
    vtt_to_srt,
    decode_subtitle_bytes,
    fetch_and_save_subtitle,
    get_ffmpeg_path,
    FFmpegMixin,
    _run_subprocess,
)

from engine_core.downloader import (
    SegmentDownloaderMixin,
)

from engine_core.pipeline import (
    extract_m3u8_info,
    detect_segment_range,
    normalize_media_url_for_ytdlp,
    VideoDownloadEngine,
)

from engine_core.recovery import (
    STATE_FILENAME,
    get_base_temp_dir,
    write_recovery_state,
    update_recovery_progress,
    read_recovery_state,
    delete_recovery_state,
    scan_incomplete_downloads,
    cleanup_stale_temp_dirs,
)

__all__ = [
    "derive_hls_iv",
    "decrypt_hls_segment",
    "AES",
    "_remove_readonly",
    "cleanup_filesystem_path",
    "sanitize_filename",
    "format_human_duration",
    "format_human_filesize",
    "parse_curl_command",
    "parse_segment_url",
    "build_segment_url",
    "probe_url",
    "_close_owned",
    "is_valid_segment_file",
    "_fast_v4_create_conn",
    "vtt_to_srt",
    "decode_subtitle_bytes",
    "fetch_and_save_subtitle",
    "get_ffmpeg_path",
    "FFmpegMixin",
    "_run_subprocess",
    "SegmentDownloaderMixin",
    "extract_m3u8_info",
    "detect_segment_range",
    "normalize_media_url_for_ytdlp",
    "VideoDownloadEngine",
    "STATE_FILENAME",
    "get_base_temp_dir",
    "write_recovery_state",
    "update_recovery_progress",
    "read_recovery_state",
    "delete_recovery_state",
    "scan_incomplete_downloads",
    "cleanup_stale_temp_dirs",
]
