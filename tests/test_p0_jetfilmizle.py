"""P0 regressions for Jetfilmizle page access and source selection."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from extractors.platforms import jetfilmizle


class _BlockedSession:
    def get(self, url, headers, timeout):
        return SimpleNamespace(status_code=403, text="blocked")


class _ChromeClient:
    @staticmethod
    def get(url, headers, impersonate, timeout):
        assert impersonate == "chrome124"
        return SimpleNamespace(status_code=200, text="<html>player page</html>")


def test_jetfilmizle_page_fetch_uses_chrome_fallback_after_403() -> None:
    with patch.object(jetfilmizle, "c_requests", _ChromeClient):
        response = jetfilmizle._fetch_page(
            _BlockedSession(),
            "https://jetfilmizle.example/film/test",
            {"User-Agent": "VDP-Test"},
        )

    assert response.status_code == 200
    assert "player page" in response.text


def test_jetfilmizle_film_selects_one_supported_source_per_language() -> None:
    buttons = [
        ("0", "dublaj", "Vip"),
        ("3", "dublaj", "Moly"),
        ("8", "dublaj", "StreamHLS"),
        ("0", "altyazili", "Vip"),
        ("4", "altyazili", "Moly"),
        ("7", "altyazili", "StreamHLS"),
        ("0", "genel", "JetGlobal"),
    ]

    selected = jetfilmizle._select_preferred_film_sources(buttons)

    assert selected == [
        ("3", "dublaj", "Moly"),
        ("4", "altyazili", "Moly"),
    ]


def test_jetfilmizle_reads_original_language_from_movie_genres() -> None:
    page_html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Movie",
      "name": "Summer Meets God",
      "genre": ["Animasyon", "Anime", "Japonca"]
    }
    </script>
    """

    assert jetfilmizle._extract_original_audio_language(page_html) == (
        "jpn",
        "Japonca",
    )


def test_jetfilmizle_does_not_claim_english_when_original_language_is_unknown() -> None:
    page_html = """
    <script type="application/ld+json">
    {"@type": "Movie", "name": "Example", "genre": ["Aksiyon", "Dram"]}
    </script>
    """

    assert jetfilmizle._extract_original_audio_language(page_html) == (
        "und",
        "Orijinal Dil",
    )
