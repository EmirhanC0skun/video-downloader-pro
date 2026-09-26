# -*- coding: utf-8 -*-
"""
Video Downloader Pro — UI Controllers Package.
"""
from ui.controllers.download import DownloadControllerMixin
from ui.controllers.resolve import ResolveControllerMixin
from ui.controllers.social import SocialControllerMixin
from ui.controllers.queue import QueueControllerMixin
from ui.controllers.history import HistoryControllerMixin
from ui.controllers.converter import ConverterControllerMixin
from ui.controllers.dpi import DPIControllerMixin
from ui.controllers.recovery import RecoveryControllerMixin
from ui.controllers.system import SystemControllerMixin

__all__ = [
    "DownloadControllerMixin",
    "ResolveControllerMixin",
    "SocialControllerMixin",
    "QueueControllerMixin",
    "HistoryControllerMixin",
    "ConverterControllerMixin",
    "DPIControllerMixin",
    "RecoveryControllerMixin",
    "SystemControllerMixin",
]
