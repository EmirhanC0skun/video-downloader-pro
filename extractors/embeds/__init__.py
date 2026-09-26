# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Modular Embed Extractors Package.
"""

from extractors.embeds.vidmoly import VidmolyExtractor, resolve_vidmoly_embed
from extractors.embeds.voe import VoeExtractor, resolve_voe_embed
from extractors.embeds.streamwish import StreamwishExtractor, resolve_streamwish_embed
from extractors.embeds.sibnet import SibnetExtractor, resolve_sibnet_embed
from extractors.embeds.closeload import CloseloadExtractor, decrypt_closeload_python, resolve_closeload_embed
from extractors.embeds.dplayer import DPlayerExtractor, resolve_dplayer_embed
from extractors.embeds.mailru import MailruExtractor, resolve_mailru_embed
from extractors.embeds.players import (
    resolve_vidsrc_embed,
    resolve_pichive_embed,
    resolve_popcornvakti_embed,
    resolve_biplayer_embed,
    resolve_videopark_embed,
    resolve_canlitvnews_embed,
    PichiveExtractor,
    VideoparkExtractor,
    BiplayerExtractor,
    CanlitvnewsExtractor,
)

__all__ = [
    "VidmolyExtractor",
    "resolve_vidmoly_embed",
    "VoeExtractor",
    "resolve_voe_embed",
    "StreamwishExtractor",
    "resolve_streamwish_embed",
    "SibnetExtractor",
    "resolve_sibnet_embed",
    "CloseloadExtractor",
    "decrypt_closeload_python",
    "resolve_closeload_embed",
    "DPlayerExtractor",
    "resolve_dplayer_embed",
    "MailruExtractor",
    "resolve_mailru_embed",
    "resolve_vidsrc_embed",
    "resolve_pichive_embed",
    "resolve_popcornvakti_embed",
    "resolve_biplayer_embed",
    "resolve_videopark_embed",
    "resolve_canlitvnews_embed",
    "PichiveExtractor",
    "VideoparkExtractor",
    "BiplayerExtractor",
    "CanlitvnewsExtractor",
]
