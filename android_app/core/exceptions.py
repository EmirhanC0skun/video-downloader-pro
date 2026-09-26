# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Exception Hierarchy.
Provides structured and domain-specific exceptions for robust error handling.
"""

class VideoDownloaderError(Exception):
    """Base class for all exceptions in Video Downloader Pro."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ExtractorError(VideoDownloaderError, RuntimeError):
    """Raised when parsing or extracting media streams fails."""
    pass


class ISPBlockError(ExtractorError):
    """Raised when a website is blocked by ISP / DNS censorship."""
    pass


class DecryptionError(ExtractorError):
    """Raised when JavaScript or AES stream decryption fails."""
    pass


class DownloadError(VideoDownloaderError):
    """Raised when a segment or direct file download fails."""
    pass


class SegmentDownloadError(DownloadError):
    """Raised when one or more HLS segments cannot be retrieved."""
    def __init__(self, message: str, failed_indices: list = None):
        super().__init__(message, details={"failed_indices": failed_indices or []})
        self.failed_indices = failed_indices or []


class MuxingError(VideoDownloaderError):
    """Raised when FFmpeg muxing, audio merging, or converting fails."""
    pass


class FFmpegNotFoundError(MuxingError):
    """Raised when the FFmpeg binary is missing from the system."""
    pass


class CancelledError(VideoDownloaderError):
    """Raised when an operation is cancelled by the user."""
    pass
