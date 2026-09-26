# -*- coding: utf-8 -*-
"""
Video Downloader Pro — UI Views Package.
"""
from ui.views.shell import ShellViewMixin
from ui.views.film import FilmViewMixin
from ui.views.social import SocialViewMixin
from ui.views.queue import QueueViewMixin
from ui.views.library import LibraryViewMixin
from ui.views.converter import ConverterViewMixin
from ui.views.settings import SettingsViewMixin
from ui.views.modals import ModalsMixin

__all__ = [
    "ShellViewMixin",
    "FilmViewMixin",
    "SocialViewMixin",
    "QueueViewMixin",
    "LibraryViewMixin",
    "ConverterViewMixin",
    "SettingsViewMixin",
    "ModalsMixin",
]
