# -*- coding: utf-8 -*-
"""
Video Downloader Pro — Extractor Registry and Dispatcher.
Enforces default SSL verification on all sessions and granular error typing.
"""

import html
import re
from typing import List, Dict, Any
from urllib.parse import urljoin, urlsplit
import requests
from extractors.base import DEFAULT_HEADERS, BaseExtractor
from extractors.direct import DirectMediaExtractor
from extractors.embeds.vidmoly import VidmolyExtractor
from extractors.embeds.voe import VoeExtractor
from extractors.embeds.streamwish import StreamwishExtractor
from extractors.embeds.sibnet import SibnetExtractor
from extractors.embeds.closeload import CloseloadExtractor
from extractors.embeds.dplayer import DPlayerExtractor
from extractors.embeds.mailru import MailruExtractor
from extractors.embeds.players import PichiveExtractor, VideoparkExtractor, BiplayerExtractor, CanlitvnewsExtractor, RapidvidExtractor
from extractors.platforms.dizipal import DizipalExtractor
from extractors.platforms.dizitime import DizitimeExtractor
from extractors.platforms.filmmodu import FilmmoduExtractor
from extractors.platforms.dizilla import DizillaExtractor
from extractors.platforms.jetfilmizle import JetfilmizleExtractor
from extractors.platforms.sezonlukdizi import SezonlukdiziExtractor
from extractors.platforms.yabancidizi import YabancidiziExtractor
from extractors.platforms.hdfilmcehennemi import HDFilmcehennemiExtractor
from extractors.platforms.diziyou import DiziyouExtractor
from extractors.platforms.dizibox import DiziboxExtractor
from extractors.platforms.anime import AnimeExtractor
from extractors.platforms.fullhd import FullHDFilmizleseneExtractor, FullHDFilmizleMomExtractor
from extractors.platforms.seven20p import Seven20pExtractor
from extractors.dailymotion import DailymotionExtractor
from extractors.series_film import SeriesFilmExtractor
from extractors.universal import UniversalYtDlpExtractor
from exceptions import ExtractorError, DecryptionError
from logger import get_logger

logger = get_logger("extractors.registry")


def _safe_failure_context(url: str, error: Exception):
    """Return diagnostic context without exposing signed URL query values."""
    try:
        host = urlsplit(str(url)).netloc or "unknown-host"
    except ValueError:
        host = "invalid-host"
    message = re.sub(
        r"(https?://[^\s?'\"<>]+)\?[^\s'\"<>]+",
        r"\1?<redacted>",
        str(error),
        flags=re.IGNORECASE,
    )
    return host, message


class ExtractorRegistry:
    """Manages registered extractors and dispatches resolution requests."""

    def __init__(self):
        self._extractors: List[BaseExtractor] = []
        self._register_default_extractors()

    def _register_default_extractors(self):
        """Registers core platform extractors in priority order."""
        # 1. Direct Media Files & Playlists
        self.register(DirectMediaExtractor())

        # 2. Embed Players
        self.register(VidmolyExtractor())
        self.register(VoeExtractor())
        self.register(StreamwishExtractor())
        self.register(SibnetExtractor())
        self.register(CloseloadExtractor())
        self.register(DPlayerExtractor())
        self.register(MailruExtractor())
        self.register(PichiveExtractor())
        self.register(VideoparkExtractor())
        self.register(BiplayerExtractor())
        self.register(CanlitvnewsExtractor())
        self.register(RapidvidExtractor())

        # 3. Dedicated Platform Extractors
        self.register(DizipalExtractor())
        self.register(DizitimeExtractor())
        self.register(FilmmoduExtractor())
        self.register(DizillaExtractor())
        self.register(JetfilmizleExtractor())
        self.register(SezonlukdiziExtractor())
        self.register(YabancidiziExtractor())
        self.register(HDFilmcehennemiExtractor())
        self.register(DiziyouExtractor())
        self.register(DiziboxExtractor())
        self.register(AnimeExtractor())
        self.register(FullHDFilmizleseneExtractor())
        self.register(FullHDFilmizleMomExtractor())
        self.register(Seven20pExtractor())

        # 4. Multi-Mirror Series & Film Scrapers
        self.register(DailymotionExtractor())
        self.register(SeriesFilmExtractor())

        # 5. Universal Fallback
        self.register(UniversalYtDlpExtractor())

    def register(self, extractor: BaseExtractor):
        """Registers a new extractor into the registry."""
        if extractor not in self._extractors:
            self._extractors.append(extractor)
            logger.debug(f"Registered extractor: {extractor.name}")

    def _resolve_registered_iframe(self, url, session, log_callback=None):
        """Delegate explicit iframes on an unknown page only to registered non-universal extractors."""
        response = None
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = url
        try:
            response = session.get(url, headers=headers, timeout=12, allow_redirects=True)
            if response.status_code != 200:
                return None

            final_url = getattr(response, "url", "") or url
            title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
            title = " ".join(html.unescape(title_match.group(1)).split()) if title_match else "Medya"
            iframe_urls = re.findall(
                r"<iframe[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']",
                response.text,
                re.IGNORECASE,
            )
            seen = set()
            for iframe_url in iframe_urls:
                absolute_url = urljoin(final_url, html.unescape(iframe_url.strip()))
                if absolute_url in seen or not absolute_url.lower().startswith(("http://", "https://")):
                    continue
                seen.add(absolute_url)
                for extractor in self._extractors:
                    if isinstance(extractor, UniversalYtDlpExtractor):
                        continue
                    try:
                        if not extractor.can_handle(absolute_url):
                            continue
                        result = extractor.extract(
                            absolute_url,
                            session=session,
                            log_callback=log_callback,
                        )
                        if result and result.success:
                            result.title = title
                            result.raw_url = url
                            logger.info(
                                "Resolved parent iframe with '%s': %s",
                                extractor.name,
                                title,
                            )
                            return result.to_dict()
                    except (ExtractorError, DecryptionError, requests.RequestException) as domain_err:
                        source_host, safe_message = _safe_failure_context(absolute_url, domain_err)
                        logger.info(
                            "Iframe extractor '%s' domain failure on %s (%s): %s",
                            extractor.name,
                            source_host,
                            type(domain_err).__name__,
                            safe_message,
                        )
                    except Exception as unexpected_err:
                        logger.warning(
                            "Unexpected iframe extractor error in '%s' on URL %s: %s",
                            extractor.name,
                            absolute_url,
                            unexpected_err,
                            exc_info=True,
                        )
            return None
        except requests.RequestException as request_err:
            logger.debug("Generic iframe page request failed for %s: %s", url, request_err)
            return None
        except Exception as unexpected_err:
            logger.warning(
                "Unexpected generic iframe resolution error on URL %s: %s",
                url,
                unexpected_err,
                exc_info=True,
            )
            return None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    logger.debug("Generic iframe page response could not close", exc_info=True)

    def resolve(self, url: str, session=None, log_callback=None, allow_insecure_ssl: bool = False) -> Dict[str, Any]:
        """
        Iterates through registered extractors and resolves media.
        Enforces SSL certificate verification on all sessions by default.
        """
        if session is None:
            session = requests.Session()
        
        # Always enforce SSL policy uniformly across internal or caller-supplied sessions
        session.verify = not allow_insecure_ssl

        for ext in self._extractors:
            try:
                if ext.can_handle(url):
                    logger.debug(f"Attempting extraction with '{ext.name}' for {url}")
                    result = ext.extract(url, session=session, log_callback=log_callback)
                    if result and result.success:
                        logger.info(f"Successfully resolved with '{ext.name}': {result.title}")
                        return result.to_dict()
            except (ExtractorError, DecryptionError, requests.RequestException) as domain_err:
                # Expected domain-level extractor failures (including ISPBlockError): log and continue to next fallback
                source_host, safe_message = _safe_failure_context(url, domain_err)
                logger.info(
                    "Extractor '%s' domain failure on %s (%s): %s",
                    ext.name,
                    source_host,
                    type(domain_err).__name__,
                    safe_message,
                )
            except RuntimeError:
                raise
            except Exception as unexpected_err:
                # Unexpected developer/programmer bugs (TypeError, AttributeError, etc.): log full warning with traceback
                logger.warning(
                    f"Unexpected runtime error in extractor '{ext.name}' on URL {url}: {unexpected_err}",
                    exc_info=True
                )

        iframe_result = self._resolve_registered_iframe(
            url,
            session=session,
            log_callback=log_callback,
        )
        if iframe_result:
            return iframe_result

        raise ExtractorError("Sayfada oynatıcı veya medya bağlantısı bulunamadı.")


# Global default registry instance
default_registry = ExtractorRegistry()
