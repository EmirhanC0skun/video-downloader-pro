from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import base64
import inspect
import json
import subprocess
import sys
import threading
from urllib.parse import urlparse
from unittest.mock import MagicMock

import engine_core.downloader as downloader_module
import engine_core.ffmpeg as ffmpeg_module
import engine_core.pipeline as pipeline_module
import extractors.platforms.dizibox as dizibox_module
import extractors.platforms.dizipal as dizipal_module
import extractors.platforms.dizitime as dizitime_module
import extractors.platforms.filmmodu as filmmodu_module
import extractors.platforms.jetfilmizle as jetfilmizle_module
import extractors.platforms.sezonlukdizi as sezonlukdizi_module
import extractors.embeds.players as players_module
import extractors.variants as variants_module
import extractors.series_film as series_film_module
import extractors.universal as universal_module
import extractor as extractor_facade
from exceptions import ExtractorError
from engine_core.pipeline import VideoDownloadEngine
from extractors.base import BaseExtractor, ExtractorResult
from extractors.embeds.players import resolve_rapidvid_embed
from extractors.platforms.dizibox import DiziboxExtractor
from extractors.platforms.dizitime import DizitimeExtractor
from extractors.platforms.dizipal import _classify_standalone_stream
from extractors.platforms.fullhd import FullHDFilmizleMomExtractor
from extractors.series_film import SeriesFilmExtractor
from extractors.universal import UniversalYtDlpExtractor
from extractors.registry import ExtractorRegistry
from extractors.platforms.yabancidizi import YabancidiziExtractor
from ui.controllers.download import DownloadControllerMixin
from ui.controllers.resolve import ResolveControllerMixin


TS_PACKET = b"\x47" + (b"\x00" * 187)


class _Response:
    def __init__(self, text: str, status_code: int = 200, url: str = ""):
        self.text = text
        self.status_code = status_code
        self.headers = {}
        self.url = url


class _BinaryResponse:
    def __init__(self, content: bytes, content_type: str):
        self.content = content
        self.status_code = 200
        self.headers = {"Content-Type": content_type}


class _JsonResponse(_Response):
    def __init__(self, payload: dict, url: str = ""):
        super().__init__("", status_code=200, url=url)
        self.payload = payload

    def json(self):
        return self.payload


class _RouteSession:
    def __init__(self, routes: dict[str, _Response]):
        self.routes = routes

    def get(self, url, **_kwargs):
        return self.routes[url]


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_media_playlist_entries_preserve_extinf_timeline_and_init_alignment() -> None:
    playlist_url = "https://cdn.test/audio/index.m3u8"
    playlist = """#EXTM3U
#EXT-X-MAP:URI="init.mp4"
#EXTINF:3.008,
segment-000.m4s
#EXTINF:2.992,
segment-001.m4s
"""

    segment_urls, segment_durations = variants_module.extract_media_playlist_timeline(
        playlist_url,
        playlist,
    )

    assert segment_urls == [
        "https://cdn.test/audio/init.mp4",
        "https://cdn.test/audio/segment-000.m4s",
        "https://cdn.test/audio/segment-001.m4s",
    ]
    assert segment_durations == [None, 3.008, 2.992]


def test_encrypted_hls_uses_media_sequence_for_implicit_iv(monkeypatch, tmp_path) -> None:
    crypto = __import__("Crypto.Cipher", fromlist=["AES"])
    manifest_url = "https://cdn.test/hls/index.m3u8"
    key_url = "https://cdn.test/hls/key.bin"
    segment_url = "https://cdn.test/hls/segment-100.ts"
    key = b"0123456789abcdef"
    plaintext = TS_PACKET
    padding = 16 - (len(plaintext) % 16)
    ciphertext = crypto.AES.new(
        key,
        crypto.AES.MODE_CBC,
        (100).to_bytes(16, "big"),
    ).encrypt(plaintext + bytes([padding]) * padding)

    manifest_response = _Response(
        "#EXTM3U\n"
        "#EXT-X-MEDIA-SEQUENCE:100\n"
        "#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\"\n"
        "#EXTINF:6.0,\n"
        "segment-100.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    key_response = _BinaryResponse(key, "application/octet-stream")

    def get_manifest_resource(url, **_kwargs):
        return {
            manifest_url: manifest_response,
            key_url: key_response,
        }[url]

    monkeypatch.setattr(pipeline_module.requests, "get", get_manifest_resource)
    headers = {"Referer": "https://player.test/embed"}

    segments = pipeline_module.extract_m3u8_info(manifest_url, headers)

    assert segments == [segment_url]
    assert headers["aes_key"] == key
    assert headers["aes_media_sequence"] == 100
    assert headers.get("aes_iv") is None

    response = _BinaryResponse(ciphertext, "video/mp2t")
    session = SimpleNamespace(get=lambda *_args, **_kwargs: response)
    engine = VideoDownloadEngine()
    monkeypatch.setattr(engine, "_get_session", lambda: session)
    target = tmp_path / "segment.tmp"

    ok, written = engine.download_segment_file(
        segment_url,
        headers,
        str(target),
        max_retries=1,
        segment_index=0,
    )

    assert ok is True
    assert written == len(plaintext)
    assert target.read_bytes() == plaintext


def test_segment_download_closes_completed_http_response(monkeypatch, tmp_path) -> None:
    response = _BinaryResponse(TS_PACKET, "video/mp2t")
    response.close = MagicMock()
    session = SimpleNamespace(get=lambda *_args, **_kwargs: response)
    engine = VideoDownloadEngine()
    monkeypatch.setattr(engine, "_get_session", lambda: session)

    ok, written = engine.download_segment_file(
        "https://cdn.test/segment.ts",
        {"Referer": "https://player.test/embed"},
        str(tmp_path / "segment.tmp"),
        max_retries=1,
        segment_index=0,
    )

    assert ok is True
    assert written == len(TS_PACKET)
    response.close.assert_called_once_with()


def test_pichive_audio_tracks_keep_extinf_timeline(monkeypatch) -> None:
    embed_url = "https://four.pichive.test/iframe.php?v=episode"
    api_url = "https://four.pichive.test/source2.php?v=" + ("A" * 48)
    master_url = "https://cdn.test/master.m3u8"
    audio_url = "https://cdn.test/audio/tr.m3u8"
    video_url = "https://cdn.test/video/high.m3u8"
    session = _RouteSession({
        embed_url: _Response(f"<script>openPlayer('{('A' * 48)}');</script>"),
        api_url: _JsonResponse({"playlist": [{"sources": [{"file": master_url}]}]}),
        master_url: _Response(
            '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,NAME="Turkish",URI="audio/tr.m3u8"\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080\nvideo/high.m3u8\n'
        ),
        audio_url: _Response(
            "#EXTM3U\n#EXTINF:3.008,\naudio-000.m4s\n#EXTINF:2.992,\naudio-001.m4s\n"
        ),
        video_url: _Response("#EXTM3U\n#EXTINF:6.0,\nvideo-000.m4s\n"),
    })
    monkeypatch.setattr(players_module, "c_requests", None)

    result = players_module.resolve_pichive_embed(embed_url, session=session)

    assert result is not None
    assert result["audio_tracks"][0]["durations"] == [3.008, 2.992]


def test_filmmodu_audio_tracks_keep_extinf_timeline(monkeypatch) -> None:
    page_url = "https://filmmodu.test/movie"
    player_url = "https://play2.pilavyerplay.top/assets/js/s.php?s=movie-token"
    master_url = "https://cdn.test/master.m3u8"
    audio_url = "https://cdn.test/audio/tr.m3u8"
    video_url = "https://cdn.test/video/high.m3u8"
    player_data = {
        "stream": master_url,
        "title": "Movie",
        "audios": [{"name": "tr", "label": "Turkce Dublaj", "lang": "tr"}],
        "subs": [],
    }
    session = _RouteSession({
        page_url: _Response('<title>Movie izle</title><div data-pv="movie-token"></div>'),
        player_url: _Response(f"window.__PLAYER__ = {json.dumps(player_data)};"),
        master_url: _Response(
            '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,NAME="tr",LANGUAGE="tr",URI="audio/tr.m3u8"\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080\nvideo/high.m3u8\n'
        ),
        audio_url: _Response(
            "#EXTM3U\n#EXTINF:6.006,\naudio-000.aac\n#EXTINF:5.994,\naudio-001.aac\n"
        ),
        video_url: _Response("#EXTM3U\n#EXTINF:6.0,\nvideo-000.ts\n"),
    })
    monkeypatch.setattr(filmmodu_module, "c_requests", None)

    result = filmmodu_module.FilmmoduExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.audio_tracks[0]["durations"] == [6.006, 5.994]


def test_jetfilmizle_standalone_tracks_keep_extinf_timeline(monkeypatch) -> None:
    page_url = "https://jetfilmizle.test/film/example"
    embed_url = "https://vidmoly.biz/embed-example.html"
    master_url = "https://cdn.test/master.m3u8"
    media_url = "https://cdn.test/high.m3u8"

    class Session(_RouteSession):
        def post(self, _url, **_kwargs):
            return _Response(f'<iframe src="{embed_url}"></iframe>')

    session = Session({
        page_url: _Response(
            '<title>Example izle</title><input name="film_id" value="42">'
            '<button class="player-source-btn" data-source-index="1" '
            'data-player-type="dublaj">Moly</button>'
        ),
        master_url: _Response(
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080\nhigh.m3u8\n"
        ),
        media_url: _Response(
            "#EXTM3U\n#EXTINF:6.006,\nsegment-0.ts\n#EXTINF:5.994,\nsegment-1.ts\n"
        ),
        embed_url: _Response("<html></html>"),
    })
    monkeypatch.setattr(jetfilmizle_module, "c_requests", None)
    monkeypatch.setattr(jetfilmizle_module, "resolve_vidmoly_embed", lambda *_args, **_kwargs: master_url)

    result = jetfilmizle_module.JetfilmizleExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.audio_tracks[0]["durations"] == [6.006, 5.994]


def test_sezonlukdizi_standalone_tracks_keep_extinf_timeline(monkeypatch) -> None:
    page_url = "https://sezonlukdizi.test/example/episode.html"
    embeds = {
        0: "https://vidmoly.biz/embed-dubbed.html",
        1: "https://vidmoly.biz/embed-original.html",
    }
    masters = {
        embeds[0]: "https://cdn.test/dub/master.m3u8",
        embeds[1]: "https://cdn.test/original/master.m3u8",
    }

    class Session(_RouteSession):
        def post(self, url, data=None, **_kwargs):
            if "dataAlternatif22" in url:
                return _JsonResponse({"status": "success", "data": [{"id": int(data["dil"])}]})
            return _Response(f'<iframe src="{embeds[int(data["id"])]}"></iframe>')

    routes = {page_url: _Response('<title>Silo izle</title><div data-id="42"></div>')}
    for dil, embed_url in embeds.items():
        master_url = masters[embed_url]
        media_url = master_url.replace("master.m3u8", "high.m3u8")
        low_url = master_url.replace("master.m3u8", "low.m3u8")
        routes[master_url] = _Response(
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080\n"
            "high.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n"
            "low.m3u8\n"
        )
        routes[media_url] = _Response(
            f"#EXTM3U\n#EXTINF:{6.006 if dil == 0 else 5.994},\nsegment-0.ts\n"
        )
        routes[low_url] = _Response("#EXTM3U\n#EXTINF:6.0,\nlow-segment-0.ts\n")
    session = Session(routes)
    monkeypatch.setattr(sezonlukdizi_module, "c_requests", None)
    monkeypatch.setattr(
        sezonlukdizi_module,
        "resolve_vidmoly_embed",
        lambda embed_url, **_kwargs: masters[embed_url],
    )

    result = sezonlukdizi_module.SezonlukdiziExtractor().extract(page_url, session=session)

    assert result is not None
    assert [track["durations"] for track in result.audio_tracks] == [[6.006], [5.994]]
    assert all(track["video_url"].endswith("high.m3u8") for track in result.audio_tracks)


def test_sezonlukdizi_prioritizes_vidmoly_over_streamruby() -> None:
    alternatives = [
        {"id": 10, "baslik": "Pixel", "kalite": 4},
        {"id": 11, "baslik": "Streamruby", "kalite": 4},
        {"id": 12, "baslik": "VidMoly", "kalite": 3},
        {"id": 13, "baslik": "Sibnet", "kalite": 3},
    ]

    ordered = sezonlukdizi_module._prioritize_alternatives(alternatives)

    assert [item["id"] for item in ordered] == [12, 11, 13, 10]


def test_yabancidizi_preserves_primary_video_segments() -> None:
    page_url = "https://yabancidizi.test/episode"
    embed_url = "https://vidmoly.biz/embed-abcdefgh.html"
    master_url = "https://cdn.test/master.m3u8"
    media_url = "https://cdn.test/high.m3u8"
    session = _RouteSession({
        page_url: _Response(
            '<h1 class="page-title">Episode</h1>'
            '<a href="https://vidmoly.biz/dl/abcdefgh">Altyazılı</a>'
        ),
        embed_url: _Response(f'sources: [{{file: "{master_url}"}}]'),
        master_url: _Response("#EXTM3U\nhigh.m3u8\n"),
        media_url: _Response("#EXTM3U\nseg-1.ts\nseg-2.ts\n"),
    })

    result = YabancidiziExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_segments == [
        "https://cdn.test/seg-1.ts",
        "https://cdn.test/seg-2.ts",
    ]


def test_dizibox_preserves_muxed_video_segments(monkeypatch) -> None:
    page_url = "https://dizibox.test/episode"
    player_url = "https://dizibox.test/king.php?id=1"
    embed_url = "https://vidmoly.biz/embed-abcdefgh.html"
    master_url = "https://cdn.test/master.m3u8"
    media_url = "https://cdn.test/high.m3u8"
    session = _RouteSession({
        page_url: _Response(f'<title>Episode izle</title><iframe src="{player_url}"></iframe>'),
        player_url: _Response(f'<iframe src="{embed_url}"></iframe>'),
        embed_url: _Response('CryptoJS.AES.decrypt("cipher", "key")'),
        master_url: _Response("#EXTM3U\nhigh.m3u8\n"),
        media_url: _Response(
            "#EXTM3U\nhttps://cdn.test/sheila_000.png\n"
            "https://cdn.test/sheila_001.png\n"
        ),
    })
    monkeypatch.setattr(
        dizibox_module,
        "decrypt_cryptojs_aes",
        lambda _cipher, _key: f'file: "{master_url}"',
    )

    result = DiziboxExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_segments == [
        "https://cdn.test/sheila_000.png",
        "https://cdn.test/sheila_001.png",
    ]
    assert result.audio_tracks[0]["is_standalone_stream"] is True


def test_dizibox_retries_page_with_impersonated_client_after_http_403(monkeypatch) -> None:
    page_url = "https://dizibox.test/episode"
    player_url = "https://dizibox.test/king.php?id=1"
    embed_url = "https://vidmoly.biz/embed-abcdefgh.html"
    master_url = "https://cdn.test/master.m3u8"
    media_url = "https://cdn.test/high.m3u8"
    session = _RouteSession({
        page_url: _Response("blocked", status_code=403),
        player_url: _Response(f'<iframe src="{embed_url}"></iframe>'),
        embed_url: _Response('CryptoJS.AES.decrypt("cipher", "key")'),
        master_url: _Response("#EXTM3U\nhigh.m3u8\n"),
        media_url: _Response("#EXTM3U\nhttps://cdn.test/sheila_000.png\n"),
    })
    impersonated_page = _Response(
        f'<title>Episode izle</title><iframe src="{player_url}"></iframe>',
        url=page_url,
    )
    monkeypatch.setattr(
        dizibox_module,
        "c_requests",
        SimpleNamespace(get=lambda *_args, **_kwargs: impersonated_page),
    )
    monkeypatch.setattr(
        dizibox_module,
        "decrypt_cryptojs_aes",
        lambda _cipher, _key: f'file: "{master_url}"',
    )

    result = DiziboxExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_segments == ["https://cdn.test/sheila_000.png"]


def test_dizipal_falls_back_to_requests_when_impersonated_master_fetch_fails(monkeypatch) -> None:
    page_url = "https://dizipal.test/episode"
    embed_url = "https://four.dplayer.test/iframe.php?v=episode"
    master_url = "https://cdn.test/master.m3u8"
    encrypted = base64.b64encode(b"ciphertext").decode("ascii")
    page_html = (
        '<title>Episode - Dizipal</title>'
        f'<div data-rm-k>{{"salt":"aa","iv":"00112233445566778899aabbccddeeff",'
        f'"ciphertext":"{encrypted}"}}</div>'
    )
    session = _RouteSession({
        page_url: _Response(page_html),
        master_url: _Response("#EXTM3U\n#EXTINF:6.0,\nseg-000.ts\n"),
    })
    cipher = MagicMock()
    cipher.decrypt.return_value = embed_url.encode("utf-8") + (b"\x05" * 5)
    aes = MagicMock()
    aes.MODE_CBC = object()
    aes.new.return_value = cipher
    monkeypatch.setattr(dizipal_module, "AES", aes)
    monkeypatch.setattr(
        dizipal_module,
        "resolve_dplayer_embed",
        lambda *_args, **_kwargs: {
            "streams": [{"title": "Türkçe Dublaj", "url": master_url}],
            "subtitles": [],
        },
    )

    class FailingImpersonatedRequests:
        @staticmethod
        def get(*_args, **_kwargs):
            raise RuntimeError("curl: (77) error setting certificate verify locations")

    monkeypatch.setattr(dizipal_module, "c_requests", FailingImpersonatedRequests())

    result = dizipal_module.resolve_dizipal_page(page_url, session=session)

    assert result is not None
    assert result["video_segments"] == ["https://cdn.test/seg-000.ts"]


def test_dizipal_resolves_modern_one_time_player_config(monkeypatch) -> None:
    page_url = "https://dizipal2134.test/bolum/house-of-the-dragon-1-sezon-1-bolum"
    config_url = "https://dizipal2134.test/ajax-player-config"
    embed_url = "https://formationfeed.test/embed-episode.html"
    master_url = "https://cdn.test/master.m3u8"
    video_url = "https://cdn.test/1080/video.m3u8"
    turkish_audio_url = "https://cdn.test/audio/tr.m3u8"
    english_audio_url = "https://cdn.test/audio/en.m3u8"
    page_html = (
        "<html><head><title>House of the Dragon 1. Sezon 1. Bölüm izle | Dizipal</title></head>"
        '<div id="videoContainer" data-cfg="one-time-token"></div></html>'
    )
    encrypted_config = {
        "success": True,
        "config": {"v": "", "t": "embed", "p": "https://cdn.test/poster.jpg"},
        "enc": {
            "c": "fcrVgeiCEWE6BIF8gbdLY/XEI1d4SSErOon6PV3MKVXOmGTRp9RucvMBs5OmQd3B",
            "iv": "AAECAwQFBgcICQoLDA0ODw==",
            "k1": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            "k2": "//79/Pv6+fj39vX08/Lx8O/u7ezr6uno5+bl5OPi4eA=",
        },
    }
    embed_html = (
        '<script>jwplayer("vplayer").setup({'
        f'sources: [{{file:"{master_url}"}}],'
        'tracks: [{file:"https://cdn.test/subtitles/tr.vtt",label:"Turkish",kind:"captions"}]'
        '});</script>'
    )
    master_text = (
        '#EXTM3U\n'
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio0",NAME="Türkçe",LANGUAGE="tr",URI="{turkish_audio_url}"\n'
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio0",NAME="English",LANGUAGE="en",URI="{english_audio_url}"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,AUDIO="audio0"\n'
        f'{video_url}\n'
    )

    class ModernDizipalSession(_RouteSession):
        def __init__(self):
            super().__init__({
                page_url: _Response(page_html, url=page_url),
                embed_url: _Response(embed_html, url=embed_url),
                master_url: _Response(master_text, url=master_url),
                video_url: _Response("#EXTM3U\n#EXTINF:6.0,\nvideo-001.ts\n"),
                turkish_audio_url: _Response("#EXTM3U\n#EXTINF:6.0,\ntr-001.aac\n"),
                english_audio_url: _Response("#EXTM3U\n#EXTINF:6.0,\nen-001.aac\n"),
            })
            self.post_calls = []

        def post(self, url, **kwargs):
            self.post_calls.append((url, kwargs))
            assert url == config_url
            assert kwargs["data"] == {"cfg": "one-time-token"}
            return _JsonResponse(encrypted_config, url=config_url)

    session = ModernDizipalSession()
    monkeypatch.setattr(dizipal_module, "c_requests", None)

    result = dizipal_module.resolve_dizipal_page(page_url, session=session)

    assert result is not None
    assert result["title"] == "House of the Dragon 1. Sezon 1. Bölüm"
    assert result["video_url"] == video_url
    assert result["video_segments"] == ["https://cdn.test/1080/video-001.ts"]
    assert [(track["lang"], track["segments"]) for track in result["audio_tracks"]] == [
        ("tr", ["https://cdn.test/audio/tr-001.aac"]),
        ("en", ["https://cdn.test/audio/en-001.aac"]),
    ]
    assert result["subtitles"][0]["url"] == "https://cdn.test/subtitles/tr.vtt"
    assert len(session.post_calls) == 1


def test_dizitime_wrapper_preserves_nested_video_segments(monkeypatch) -> None:
    expected = ["https://cdn.test/segment-1.ts", "https://cdn.test/segment-2.ts"]
    monkeypatch.setattr(
        dizitime_module,
        "resolve_dizitime_page",
        lambda *_args, **_kwargs: {
            "success": True,
            "title": "Episode",
            "video_url": expected[0],
            "video_segments": expected,
            "audio_tracks": [],
            "subtitles": [],
        },
    )

    result = DizitimeExtractor().extract("https://dizitime.test/episode")

    assert result is not None
    assert result.video_segments == expected


def test_desktop_routes_same_muxed_url_to_single_stream(tmp_path) -> None:
    calls: list[tuple[str, str]] = []
    manifest = "https://cdn.test/index-v1-a1.m3u8"
    controller = SimpleNamespace(
        is_paused=False,
        is_downloading=False,
        entry_output=_Value(str(tmp_path / "episode.mp4")),
        slider_threads=_Value("16"),
        opt_audio_track=_Value("Generic Akışı"),
        resolved_film_data={
            "video_url": manifest,
            "video_headers": {"Referer": "https://dizitime.test/"},
            "video_segments": None,
            "total_segments": 0,
            "audio_tracks": [{
                "name": "Generic Akışı",
                "lang": "tur",
                "url": manifest,
                "segments": None,
            }],
            "subtitles": [],
        },
        _start_single_stream=lambda url, *_args, **_kwargs: calls.append(("single", url)),
        _start_multi_audio_stream=lambda **kwargs: calls.append(("multi", kwargs["video_url"])),
    )

    DownloadControllerMixin._start_film_download_threaded(controller)

    assert calls == [("single", manifest)]


def test_numbered_manifest_is_resolved_before_segment_template(monkeypatch, tmp_path) -> None:
    manifest = "https://cdn.test/index-v1-a1.m3u8"
    resolved_segments = ["https://cdn.test/seg-1.ts", "https://cdn.test/seg-2.ts"]
    engine = VideoDownloadEngine()
    calls = []
    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        pipeline_module,
        "extract_m3u8_info",
        lambda *_args, **kwargs: (
            (resolved_segments, [6.0, 6.0])
            if kwargs.get("return_timeline")
            else resolved_segments
        ),
    )
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, **_kwargs):
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_video_and_audio", lambda **_kwargs: False)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", lambda **_kwargs: False)
    monkeypatch.setattr(
        engine,
        "run_download",
        lambda **kwargs: calls.append(kwargs) or (True, kwargs["output_filepath"]),
    )

    success, _ = engine.run_multi_audio_download(
        video_url=manifest,
        audio_tracks=[{"name": "Muxed", "lang": "tur", "url": manifest}],
        output_filepath=str(tmp_path / "episode.mp4"),
        total_segments=1,
    )

    assert success is True
    assert calls[0]["segment_urls"] == resolved_segments


def test_multi_host_async_engine_remains_explicit_opt_in(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    async_calls = []
    monkeypatch.delenv("VDP_USE_CURL_ASYNC", raising=False)
    monkeypatch.setattr(downloader_module, "c_AsyncSession", object())
    monkeypatch.setattr(
        engine,
        "_download_stream_curl_async",
        lambda **_kwargs: async_calls.append(True) or (0, 0, []),
    )

    def download(_url, _headers, output_path, **_kwargs):
        Path(output_path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", download)
    tasks = [
        (index, f"https://cdn-{index}.test/seg.ts", str(tmp_path / f"seg-{index}.ts"))
        for index in range(6)
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=4,
    )

    assert async_calls == []
    assert completed == len(tasks)
    assert failed == []


def test_sharded_cdn_segment_recovers_via_sibling_host(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()

    class Response:
        headers = {"Content-Type": "video/mp2t"}

        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content

    class Session:
        def get(self, url, **_kwargs):
            if ".dead-shard-" in url:
                return Response(503)
            return Response(200, TS_PACKET)

    monkeypatch.setattr(engine, "_get_session", lambda: Session())
    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)
    tasks = [
        (0, "https://lkm-token.dead-shard-a.cfd/media/segment-0.jpg", str(tmp_path / "0.tmp")),
        (1, "https://lkm-token.dead-shard-b.cfd/media/segment-1.jpg", str(tmp_path / "1.tmp")),
        (2, "https://lkm-token.live-shard.cfd/media/segment-2.jpg", str(tmp_path / "2.tmp")),
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=3,
        fallback_hosts=(
            "lkm-token.dead-shard-a.cfd",
            "lkm-token.dead-shard-b.cfd",
            "lkm-token.live-shard.cfd",
        ),
    )

    assert completed == 3
    assert failed == []
    assert (tmp_path / "0.tmp").read_bytes() == TS_PACKET


def test_multi_audio_does_not_rewrite_host_bound_cdn_urls(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    captured: list[tuple[str, ...]] = []
    video_segments = [
        "https://srv12.cdnimages100.shop/video/000.ts",
        "https://srv12.cdnimages200.shop/video/001.ts",
    ]
    audio_segments = [
        "https://srv12.cdnimages300.shop/audio/000.ts",
        "https://srv12.cdnimages300.shop/audio/001.ts",
    ]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, **_kwargs):
        captured.append(tuple(engine.shared_fallback_hosts))
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(**kwargs):
        Path(kwargs["output_filepath"]).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=[{
            "name": "Turkish",
            "lang": "tur",
            "segments": audio_segments,
        }],
        output_filepath=str(tmp_path / "output.mp4"),
        total_segments=len(video_segments),
        thread_count=8,
    )

    assert success is True
    assert len(captured) == 2
    assert all(hosts == () for hosts in captured)


def test_dynamic_host_retry_stays_on_the_manifest_authority(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    attempts: dict[str, int] = {}
    requested: list[tuple[str, str]] = []
    recovery_logs: list[str] = []

    class Response:
        headers = {"Content-Type": "video/mp2t"}

        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content

        def close(self):
            return None

    class Session:
        def get(self, url, **_kwargs):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            index = parsed.path.rsplit("/", 1)[-1].split(".", 1)[0]
            expected_host = f"lkm-token.dynamic-{index}.cfd"
            requested.append((expected_host, parsed.netloc))
            if parsed.netloc != expected_host:
                return Response(403)
            attempts[url] = attempts.get(url, 0) + 1
            if attempts[url] == 1:
                return Response(503)
            return Response(200, TS_PACKET)

    monkeypatch.setattr(engine, "_get_session", lambda: Session())
    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)
    tasks = [
        (
            index,
            f"https://lkm-token.dynamic-{index}.cfd/media/{index}.aac",
            str(tmp_path / f"{index}.tmp"),
        )
        for index in range(40)
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=8,
        log_callback=recovery_logs.append,
    )

    assert completed == len(tasks)
    assert failed == []
    assert all(expected == actual for expected, actual in requested)
    assert not any("kurtarma turu" in message for message in recovery_logs)


def test_segment_recovery_has_bounded_low_concurrency_final_sweep(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    attempts: dict[int, int] = {}
    observed_retries: list[int] = []
    paths = [tmp_path / f"{index}.tmp" for index in range(3)]

    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)

    def download(_url, _headers, path, max_retries=1, segment_index=None, **_kwargs):
        observed_retries.append(max_retries)
        attempts[segment_index] = attempts.get(segment_index, 0) + 1
        # CDN tail failures may survive the main pass and first recovery pass;
        # the bounded final pass must complete them without an endless loop.
        if segment_index == 1 and attempts[segment_index] < 3:
            return False, 0
        Path(path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", download)
    tasks = [
        (index, f"https://lkm-token.shard-{index}.cfd/media/{index}.ts", str(paths[index]))
        for index in range(3)
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=3,
    )

    assert completed == 3
    assert failed == []
    assert attempts[1] == 3
    assert observed_retries[-1] == 4


def test_subprocess_text_capture_preserves_undecodable_ffmpeg_stderr() -> None:
    proc = ffmpeg_module._run_subprocess(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.buffer.write(bytes([0x8e]))",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert proc.stderr
    assert "\ufffd" in proc.stderr


def test_dynamic_signed_shards_preserve_manifest_hosts_on_the_main_pass(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    requested_hosts: list[tuple[int, str]] = []

    def download(url, _headers, path, segment_index=None, **_kwargs):
        from urllib.parse import urlparse

        host = urlparse(url).netloc
        requested_hosts.append((segment_index, host))
        if host != f"lkm-token.dynamic-{segment_index}.cfd":
            return False, 0
        Path(path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", download)
    tasks = [
        (
            index,
            f"https://lkm-token.dynamic-{index}.cfd/media/{index}.aac",
            str(tmp_path / f"{index}.tmp"),
        )
        for index in range(80)
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=8,
        fallback_hosts=(
            "lkm-token.video-a.cfd",
            "lkm-token.video-b.cfd",
        ),
    )

    assert completed == len(tasks)
    assert failed == []
    assert len(requested_hosts) == len(tasks)
    assert all(host == f"lkm-token.dynamic-{index}.cfd" for index, host in requested_hosts)


def test_resume_progress_is_normalized_for_unequal_stream_segment_counts(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    video_segments = [f"https://video.test/{index}.ts" for index in range(2)]
    audio_segments = [f"https://audio.test/{index}.aac" for index in range(6)]
    progress_events: list[tuple[int, int]] = []
    temp_dir = tmp_path / ".vdp_temp" / ".temp_output"
    temp_dir.mkdir(parents=True)
    for index in range(2):
        (temp_dir / f"v_seg_{index:07d}.tmp").write_bytes(TS_PACKET)
    for index in range(6):
        (temp_dir / f"a0_seg_{index:07d}.tmp").write_bytes(TS_PACKET)

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def mux(**kwargs):
        Path(kwargs["output_filepath"]).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=[{"name": "Audio", "lang": "eng", "segments": audio_segments}],
        output_filepath=str(tmp_path / "output.mp4"),
        progress_callback=lambda completed, total, *_args: progress_events.append((completed, total)),
    )

    assert success is True
    assert progress_events
    assert all(0 <= completed <= total for completed, total in progress_events)


def test_dynamic_shard_main_pass_starts_with_original_segment_host(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    target_index = 40
    seen_target_hosts: list[str] = []

    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)

    def download(url, _headers, path, segment_index=None, **_kwargs):
        from urllib.parse import urlparse

        host = urlparse(url).netloc
        if segment_index == target_index:
            seen_target_hosts.append(host)
            if host != f"lkm-token.dynamic-{target_index}.cfd":
                return False, 0
        Path(path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", download)
    tasks = [
        (
            index,
            f"https://lkm-token.dynamic-{index}.cfd/media/{index}.aac",
            str(tmp_path / f"{index}.tmp"),
        )
        for index in range(80)
    ]

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=8,
    )

    assert completed == len(tasks)
    assert failed == []
    assert seen_target_hosts == [f"lkm-token.dynamic-{target_index}.cfd"]


def test_massive_alphanumeric_cfd_shards_use_bounded_verified_family_pool(monkeypatch, tmp_path) -> None:
    """Wildcard CDN playlists must reuse a bounded host pool without changing signed paths."""
    engine = VideoDownloadEngine()
    requested: list[tuple[int, str, str]] = []
    request_lock = threading.Lock()

    def fake_download(url, _headers, target_path, **kwargs):
        with request_lock:
            requested.append((kwargs["segment_index"], url, target_path))
        Path(target_path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", fake_download)
    tasks = [
        (
            index,
            f"https://lkm-token.{index:010x}.cfd/media/{index}.aac?signature=signed-{index}",
            str(tmp_path / f"{index}.tmp"),
        )
        for index in range(80)
    ]

    completed, _total_bytes, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=8,
    )

    assert completed == 80
    assert failed == []
    assert len({urlparse(url).netloc for _, url, _ in requested}) == 64
    for index, requested_url, _target_path in requested:
        parsed = urlparse(requested_url)
        assert parsed.path == f"/media/{index}.aac"
        assert parsed.query == f"signature=signed-{index}"


def test_cdnimages_stream_worker_caps_follow_origin_cardinality(monkeypatch, tmp_path) -> None:
    """A one-origin audio stream must not be turbo-expanded past its safe CDN limit."""
    engine = VideoDownloadEngine()
    seen_executors: list[int] = []
    real_executor = downloader_module.ThreadPoolExecutor

    class RecordingExecutor(real_executor):
        def __init__(self, max_workers, *args, **kwargs):
            seen_executors.append(max_workers)
            super().__init__(max_workers=max_workers, *args, **kwargs)

    def fake_download(_url, _headers, target_path, **_kwargs):
        Path(target_path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(downloader_module, "ThreadPoolExecutor", RecordingExecutor)
    monkeypatch.setattr(engine, "download_segment_file", fake_download)
    engine.enable_turbo_boost(extra_workers=32)
    tasks = [
        (
            index,
            f"https://srv12.cdnimages210.shop/audio/{index}.aac",
            str(tmp_path / f"audio-{index}.tmp"),
        )
        for index in range(12)
    ]

    completed, _total_bytes, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=16,
    )

    assert completed == 12
    assert failed == []
    assert seen_executors[0] == 2


def test_small_recovery_tail_gets_one_bounded_serial_verification(monkeypatch, tmp_path) -> None:
    """A tiny tail surviving two sweeps gets one final serial chance, never a loop."""
    engine = VideoDownloadEngine()
    invocations = 0
    observed_retries: list[int] = []
    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)

    def flaky_download(_url, _headers, target_path, max_retries=1, **_kwargs):
        nonlocal invocations
        invocations += 1
        observed_retries.append(max_retries)
        if invocations < 4:
            return False, 0
        Path(target_path).write_bytes(TS_PACKET)
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", flaky_download)
    target = tmp_path / "tail.tmp"

    completed, _total_bytes, failed = engine.download_stream_segments(
        [(0, "https://srv12.cdnimages210.shop/audio/0.aac", str(target))],
        headers={},
        thread_count=8,
    )

    assert completed == 1
    assert failed == []
    assert invocations == 4
    assert observed_retries == [4, 2, 4, 6]


def test_segment_atomic_publish_failure_is_never_reported_as_success(monkeypatch, tmp_path) -> None:
    """A downloaded .part that cannot be published must remain a failed segment."""
    engine = VideoDownloadEngine()

    class Response:
        status_code = 200
        content = TS_PACKET
        headers = {"Content-Type": "video/mp2t"}

        def close(self):
            return None

    class Session:
        def get(self, *_args, **_kwargs):
            return Response()

    def fail_publish(*_args, **_kwargs):
        raise OSError("target is locked")

    monkeypatch.setattr(engine, "_get_session", lambda: Session())
    monkeypatch.setattr(downloader_module.os, "replace", fail_publish)
    monkeypatch.setattr(downloader_module.os, "rename", fail_publish)
    target = tmp_path / "locked.tmp"

    success, downloaded = engine.download_segment_file(
        "https://cdn.test/segment.ts",
        {},
        str(target),
        max_retries=1,
        segment_index=0,
    )

    assert success is False
    assert downloaded == 0
    assert not target.exists()


def test_multi_audio_stream_copy_does_not_force_aac_filter_on_mp3(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    video_concat = tmp_path / "video.txt"
    audio_concat = tmp_path / "audio.txt"
    output = tmp_path / "output.mp4"
    video_concat.write_text("ffconcat version 1.0\n", encoding="utf-8")
    audio_concat.write_text("ffconcat version 1.0\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(ffmpeg_module, "get_ffmpeg_path", lambda: "ffmpeg-test")

    subprocess_kwargs: list[dict] = []

    def run(command, **kwargs):
        commands.append(command)
        subprocess_kwargs.append(kwargs)
        if "-bsf:a" in command:
            return SimpleNamespace(returncode=1, stderr="Codec mp3 is not supported")
        Path(command[-1]).write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(ffmpeg_module, "_run_subprocess", run)

    success = engine.mux_multi_audio_and_video(
        v_concat_path=str(video_concat),
        audio_concats=[(str(audio_concat), "Original", "eng")],
        output_filepath=str(output),
        has_muxed_track0=True,
        track0_info=("Turkish", "tur"),
    )

    assert success is True
    assert len(commands) == 1
    assert "-bsf:a" not in commands[0]
    assert commands[0][1:5] == ["-y", "-nostats", "-loglevel", "error"]
    assert subprocess_kwargs[0]["stdout"] is subprocess.DEVNULL
    assert subprocess_kwargs[0]["stderr"] is subprocess.PIPE
    assert "capture_output" not in subprocess_kwargs[0]


def test_async_segment_windows_are_not_materialized_for_the_whole_stream() -> None:
    source = inspect.getsource(downloader_module.SegmentDownloaderMixin._download_stream_curl_async)

    assert "batches = [" not in source
    assert "batch_tasks = [" not in source
    assert "for batch_start in range(" in source


def test_turbo_handoff_adds_released_workers_to_slow_stream(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    active = 0
    peak_active = 0
    lock = threading.Lock()

    def download(_url, _headers, _path, **_kwargs):
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        threading.Event().wait(0.04)
        with lock:
            active -= 1
        return True, len(TS_PACKET)

    monkeypatch.setattr(engine, "download_segment_file", download)
    tasks = [
        (index, f"https://audio.test/{index}.aac", str(tmp_path / f"{index}.tmp"))
        for index in range(12)
    ]
    engine.enable_turbo_boost(extra_workers=6)

    completed, _downloaded, failed = engine.download_stream_segments(
        tasks,
        headers={},
        thread_count=2,
    )

    assert completed == len(tasks)
    assert failed == []
    assert peak_active >= 6


def test_multi_audio_uses_global_worker_budget_and_concat_lists(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    worker_allocations: list[int] = []
    captured: dict[str, object] = {}
    video_segments = [f"https://video.test/{index}.ts" for index in range(301)]
    extra_audio = [f"https://audio.test/{index}.ts" for index in range(301)]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, thread_count=1, **_kwargs):
        worker_allocations.append(thread_count)
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(v_concat_path, audio_concats, output_filepath, **kwargs):
        captured["video_path"] = v_concat_path
        captured["audio_paths"] = [item[0] for item in audio_concats]
        captured["video_list"] = Path(v_concat_path).read_text(encoding="utf-8")
        captured["audio_lists"] = [Path(item[0]).read_text(encoding="utf-8") for item in audio_concats]
        captured["has_muxed_track0"] = kwargs["has_muxed_track0"]
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=[
            {"name": "Original", "lang": "eng", "segments": video_segments},
            {"name": "Dubbed", "lang": "tur", "segments": extra_audio},
        ],
        output_filepath=str(tmp_path / "output.mp4"),
        total_segments=len(video_segments),
        thread_count=32,
    )

    assert success is True
    assert sum(worker_allocations) <= 32
    assert str(captured["video_path"]).endswith("concat_video.txt")
    assert all(str(path).endswith(".txt") for path in captured["audio_paths"])
    assert captured["has_muxed_track0"] is True
    assert str(captured["video_list"]).count("file '") == len(video_segments)
    assert str(captured["audio_lists"][0]).count("file '") == len(extra_audio)


def test_single_selected_external_audio_is_not_replaced_by_video_embedded_audio(
    monkeypatch,
    tmp_path,
) -> None:
    engine = VideoDownloadEngine()
    video_segments = [f"https://cdn.test/video-{index}.ts" for index in range(2)]
    english_segments = [f"https://cdn.test/audio-en-{index}.aac" for index in range(2)]
    downloaded_urls: list[str] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)
    monkeypatch.setattr(
        engine,
        "run_download",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("external audio selection incorrectly used the muxed-video fast path")
        ),
    )

    def download(tasks, _headers=None, **_kwargs):
        for _index, url, path in tasks:
            downloaded_urls.append(url)
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(v_concat_path, audio_concats, output_filepath, **kwargs):
        captured["audio_concats"] = audio_concats
        captured["has_muxed_track0"] = kwargs["has_muxed_track0"]
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _result = engine.run_multi_audio_download(
        video_url="https://cdn.test/index-v1-a1.m3u8",
        video_segments=video_segments,
        video_durations=[6.0, 6.0],
        audio_tracks=[{
            "name": "English (Original)",
            "lang": "en",
            "url": "https://cdn.test/index-a2.m3u8",
            "segments": english_segments,
            "durations": [6.0, 6.0],
            "video_url": "https://cdn.test/index-v1-a1.m3u8",
            "video_segments": video_segments,
            "video_durations": [6.0, 6.0],
        }],
        output_filepath=str(tmp_path / "original-audio.mp4"),
        total_segments=len(video_segments),
        thread_count=4,
    )

    assert success is True
    assert set(english_segments).issubset(downloaded_urls)
    assert captured["has_muxed_track0"] is False
    assert len(captured["audio_concats"]) == 1


def test_cdnimages_multi_audio_caps_aggregate_workers(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    worker_allocations: list[int] = []
    video_segments = [f"https://srv12.cdnimages1778.shop/video/{index}.ts" for index in range(3)]
    audio_tracks = [
        {
            "name": "Turkish",
            "lang": "tur",
            "segments": [f"https://srv12.cdnimages210.shop/tr/{index}.aac" for index in range(3)],
        },
        {
            "name": "Original",
            "lang": "eng",
            "segments": [f"https://srv12.cdnimages210.shop/en/{index}.aac" for index in range(3)],
        },
    ]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, thread_count=1, **_kwargs):
        worker_allocations.append(thread_count)
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(**kwargs):
        Path(kwargs["output_filepath"]).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=audio_tracks,
        output_filepath=str(tmp_path / "cdn-output.mp4"),
        total_segments=len(video_segments),
        thread_count=32,
    )

    assert success is True
    assert sorted(worker_allocations) == [4, 4, 8]


def test_rapidrame_multi_audio_caps_aggregate_workers(monkeypatch, tmp_path) -> None:
    """Rapidrame rate limits must not leave a large audio recovery tail."""
    engine = VideoDownloadEngine()
    worker_allocations: list[int] = []
    video_segments = [
        f"https://s427.rapidrame.com/hls/movie/seg-{index}-video.ts"
        for index in range(3)
    ]
    audio_tracks = [
        {
            "name": "Turkish",
            "lang": "tur",
            "segments": [
                f"https://s427.rapidrame.com/hls/movie/seg-{index}-audio-tr.ts"
                for index in range(3)
            ],
        },
        {
            "name": "Original",
            "lang": "eng",
            "segments": [
                f"https://s427.rapidrame.com/hls/movie/seg-{index}-audio-en.ts"
                for index in range(3)
            ],
        },
    ]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, thread_count=1, **_kwargs):
        worker_allocations.append(thread_count)
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(**kwargs):
        Path(kwargs["output_filepath"]).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=audio_tracks,
        output_filepath=str(tmp_path / "rapidrame-output.mp4"),
        total_segments=len(video_segments),
        thread_count=32,
    )

    assert success is True
    assert sorted(worker_allocations) == [2, 2, 4]


def test_multi_audio_concat_preserves_audio_playlist_timeline(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    captured_video_list = []
    captured_audio_list = []
    video_segments = ["https://video.test/000.ts", "https://video.test/001.ts"]
    audio_segments = ["https://audio.test/000.aac", "https://audio.test/001.aac"]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, **_kwargs):
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(v_concat_path, audio_concats, output_filepath, **_kwargs):
        assert Path(v_concat_path).exists()
        captured_video_list.append(Path(v_concat_path).read_text(encoding="utf-8"))
        captured_audio_list.append(Path(audio_concats[0][0]).read_text(encoding="utf-8"))
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        video_durations=[3.008, 2.992],
        audio_tracks=[{
            "name": "Turkish",
            "lang": "tur",
            "segments": audio_segments,
            "durations": [3.008, 2.992],
        }],
        output_filepath=str(tmp_path / "timeline.mp4"),
        total_segments=len(video_segments),
        thread_count=4,
    )

    assert success is True
    assert "duration 3.008\n" in captured_video_list[0]
    assert "duration 2.992\n" in captured_video_list[0]
    assert "duration 3.008\n" in captured_audio_list[0]
    assert "duration 2.992\n" in captured_audio_list[0]


def test_separate_audio_timeline_is_never_reused_as_unknown_video_timeline(
    monkeypatch,
    tmp_path,
) -> None:
    engine = VideoDownloadEngine()
    captured_video_list = []
    video_segments = ["https://video.test/000.ts", "https://video.test/001.ts"]
    audio_segments = ["https://audio.test/000.aac", "https://audio.test/001.aac"]
    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, **_kwargs):
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(v_concat_path, output_filepath, **_kwargs):
        captured_video_list.append(Path(v_concat_path).read_text(encoding="utf-8"))
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=[{
            "name": "Turkish",
            "lang": "tur",
            "segments": audio_segments,
            "durations": [9.0, 9.0],
        }],
        output_filepath=str(tmp_path / "unknown-video-timeline.mp4"),
        thread_count=2,
    )

    assert success is True
    assert "duration " not in captured_video_list[0]


def test_dual_stream_facade_forwards_video_and_audio_timelines(monkeypatch) -> None:
    engine = VideoDownloadEngine()
    captured = {}
    monkeypatch.setattr(
        engine,
        "run_multi_audio_download",
        lambda **kwargs: captured.update(kwargs) or (True, kwargs["output_filepath"]),
    )

    success, _ = engine.run_dual_stream_download(
        video_url="https://video.test/manifest.m3u8",
        audio_url="https://audio.test/manifest.m3u8",
        output_filepath="output.mp4",
        video_segments=["https://video.test/0.ts"],
        audio_segments=["https://audio.test/0.aac"],
        video_durations=[6.0],
        audio_durations=[6.0],
    )

    assert success is True
    assert captured["video_durations"] == [6.0]
    assert captured["audio_tracks"][0]["durations"] == [6.0]


def test_muxed_primary_track_preserves_video_playlist_timeline(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    captured_video_list = []
    video_segments = ["https://video.test/000.ts", "https://video.test/001.ts"]
    extra_audio = ["https://audio.test/000.aac", "https://audio.test/001.aac"]

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, **_kwargs):
        for _index, _url, path in tasks:
            Path(path).write_bytes(TS_PACKET)
        return len(tasks), len(tasks) * len(TS_PACKET), []

    def mux(v_concat_path, audio_concats, output_filepath, **_kwargs):
        assert audio_concats
        captured_video_list.append(Path(v_concat_path).read_text(encoding="utf-8"))
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _ = engine.run_multi_audio_download(
        video_url=video_segments[0],
        video_segments=video_segments,
        audio_tracks=[
            {
                "name": "Turkish",
                "lang": "tur",
                "segments": video_segments,
                "durations": [6.006, 5.994],
            },
            {
                "name": "English",
                "lang": "eng",
                "segments": extra_audio,
                "durations": [6.006, 5.994],
            },
        ],
        output_filepath=str(tmp_path / "muxed-timeline.mp4"),
        total_segments=len(video_segments),
        thread_count=4,
    )

    assert success is True
    assert "duration 6.006\n" in captured_video_list[0]
    assert "duration 5.994\n" in captured_video_list[0]


def test_concat_demuxer_escapes_windows_apostrophe_path(tmp_path) -> None:
    concat_path = tmp_path / "concat_video.txt"
    segment_paths = [
        r"C:\Video Folder\segment 01.ts",
        r"C:\Video Folder\o'brien.ts",
    ]

    ffmpeg_module.write_concat_file(str(concat_path), segment_paths)

    assert concat_path.read_text(encoding="utf-8") == (
        "ffconcat version 1.0\n"
        "file 'C:\\Video Folder\\segment 01.ts'\n"
        "file 'C:\\Video Folder\\o'\\''brien.ts'\n"
    )


def test_concat_demuxer_preserves_hls_timeline_durations(tmp_path) -> None:
    concat_path = tmp_path / "concat_audio.txt"
    segment_paths = [tmp_path / "audio-000.m4s", tmp_path / "audio-001.m4s"]

    ffmpeg_module.write_concat_file(
        str(concat_path),
        segment_paths,
        segment_durations=[3.008, 2.992],
    )

    rendered = concat_path.read_text(encoding="utf-8")
    assert "duration 3.008\n" in rendered
    assert "duration 2.992\n" in rendered


def test_hls_timeline_validation_rejects_material_audio_duration_mismatch() -> None:
    assert pipeline_module._hls_timelines_aligned(
        [10.0, 10.0, 10.0],
        [3.0] * 10,
    ) is True
    assert pipeline_module._hls_timelines_aligned(
        [10.0, 10.0, 10.0],
        [3.0] * 9,
    ) is False
    assert pipeline_module._hls_timelines_aligned(None, [3.0] * 10) is True


def test_hls_timeline_accepts_only_final_audio_tail_when_segment_starts_stay_aligned() -> None:
    assert pipeline_module._hls_timelines_aligned(
        [10.0, 2.25, 9.68],
        [10.0, 2.26, 28.99],
    ) is True
    assert pipeline_module._hls_timelines_aligned(
        [10.0, 2.25, 9.68],
        [10.6, 2.85, 28.99],
    ) is False


def test_download_workers_do_not_share_requests_session() -> None:
    engine = VideoDownloadEngine()
    sessions = [engine._get_session()]

    worker = threading.Thread(target=lambda: sessions.append(engine._get_session()))
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert sessions[0] is not sessions[1]
    assert sessions[0].get_adapter("https://").max_retries.total == 0
    assert sessions[1].get_adapter("https://").max_retries.total == 0


def test_download_worker_keeps_healthy_session_beyond_fixed_request_count() -> None:
    """A healthy worker must retain keep-alive instead of reconnecting in lockstep."""
    engine = VideoDownloadEngine()
    sessions = [engine._get_session() for _ in range(64)]

    assert len({id(session) for session in sessions}) == 1


def test_single_stream_does_not_restart_exhausted_segment_recovery(monkeypatch, tmp_path) -> None:
    """A permanent failure must stop after two sweeps and one bounded tail check."""
    engine = VideoDownloadEngine()
    failed_attempts = 0

    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(downloader_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)

    def download(_url, _headers, output_path, **kwargs):
        nonlocal failed_attempts
        if kwargs.get("segment_index") == 0:
            Path(output_path).write_bytes(TS_PACKET)
            return True, len(TS_PACKET)
        failed_attempts += kwargs.get("max_retries", 1)
        return False, 0

    monkeypatch.setattr(engine, "download_segment_file", download)

    success, message = engine.run_download(
        sample_url="https://cdn.test/segment-0.ts",
        segment_urls=[
            "https://cdn.test/segment-0.ts",
            "https://cdn.test/segment-1.ts",
        ],
        output_filepath=str(tmp_path / "bounded-recovery.mp4"),
        thread_count=2,
    )

    assert success is False
    assert "1 parça eksik" in message
    assert failed_attempts == 16


def test_bicaps_collects_dubbed_and_subtitled_player_sources(monkeypatch) -> None:
    page_url = "https://www.bicaps.live/filmler/example.html"
    dubbed_embed = "https://www.bicaps.live/biplayer/vid/dubbed"
    subtitled_embed = "https://www.bicaps.live/biplayer/vid/subtitled"
    html = (
        '<title>Example</title>'
        '<span class="dil" dil="trd">CapsPlayer</span>'
        f"<!--baslik:CapsPlayer,trd--><iframe src=\"{dubbed_embed}\"></iframe>"
        '<span class="dil" dil="tra">CapsPlayer</span>'
        f"<!--baslik:CapsPlayer,tra--><iframe src=\"{subtitled_embed}\"></iframe>"
    )
    session = _RouteSession({page_url: _Response(html)})

    def resolve(embed_url, **_kwargs):
        suffix = "dub" if embed_url == dubbed_embed else "sub"
        return {
            "url": f"https://cdn.test/{suffix}/master.m3u8",
            "video_segments": [f"https://cdn.test/{suffix}/segment-1.ts"],
            "durations": [6.006 if suffix == "dub" else 5.994],
            "headers": {"Referer": embed_url},
            "subtitles": [],
        }

    monkeypatch.setattr(players_module, "resolve_biplayer_embed", resolve)

    result = SeriesFilmExtractor().extract(page_url, session=session)

    assert result is not None
    assert [track["lang"] for track in result.audio_tracks] == ["tur", "eng"]
    assert all(track["is_standalone_stream"] for track in result.audio_tracks)
    assert result.audio_tracks[0]["segments"] != result.audio_tracks[1]["segments"]
    assert [track["durations"] for track in result.audio_tracks] == [[6.006], [5.994]]
    assert result.video_segments == result.audio_tracks[0]["segments"]


def test_popcorn_playlist_exposes_extinf_timeline(monkeypatch) -> None:
    playlist_url = "https://cdn.test/media.m3u8"
    session = _RouteSession({
        playlist_url: _Response(
            "#EXTM3U\n#EXTINF:6.006,\nsegment-0.ts\n#EXTINF:5.994,\nsegment-1.ts\n"
        ),
    })
    monkeypatch.setattr(players_module, "c_requests", None)

    result = players_module.resolve_popcornvakti_embed(
        playlist_url,
        session=session,
        return_meta=True,
    )

    assert result is not None
    assert result["durations"] == [6.006, 5.994]


def test_rapidvid_selects_highest_bandwidth_variant(monkeypatch) -> None:
    embed_url = "https://rapidvid.test/vod/example"
    master_url = "https://cdn.test/master.m3u8"
    high_url = "https://cdn.test/high.m3u8"
    low_url = "https://cdn.test/low.m3u8"
    session = _RouteSession({
        embed_url: _Response('av("encoded-value-placeholder")'),
        master_url: _Response(
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x800\n'
            "high.m3u8\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x266\n'
            "low.m3u8\n"
        ),
        high_url: _Response("#EXTM3U\nhigh-1.ts\nhigh-2.ts\n"),
        low_url: _Response("#EXTM3U\nlow-1.ts\n"),
    })
    monkeypatch.setattr(players_module, "decode_rapidvid", lambda _encoded: master_url)

    result = resolve_rapidvid_embed(embed_url, session=session)

    assert result is not None
    assert result["video_segments"] == [
        "https://cdn.test/high-1.ts",
        "https://cdn.test/high-2.ts",
    ]


def test_dizipal_turkish_subtitle_label_is_not_classified_as_dubbed() -> None:
    assert _classify_standalone_stream("T\u00fcrk\u00e7e Dublaj") == (
        "\U0001f1f9\U0001f1f7 T\u00fcrk\u00e7e Dublaj",
        "tur",
    )
    assert _classify_standalone_stream("T\u00fcrk\u00e7e Altyaz\u0131") == (
        "\U0001f1ec\U0001f1e7 Orijinal / T\u00fcrk\u00e7e Altyaz\u0131l\u0131",
        "eng",
    )


def test_ts_segment_is_accepted_when_cdn_mislabels_content_type(monkeypatch, tmp_path) -> None:
    engine = VideoDownloadEngine()
    response = _BinaryResponse(TS_PACKET * 4, "application/x-mpegURL")
    monkeypatch.setattr(
        engine,
        "_get_session",
        lambda: SimpleNamespace(get=lambda *_args, **_kwargs: response),
    )
    output = tmp_path / "segment.ts"

    success, downloaded = engine.download_segment_file(
        "https://cdn.test/segment.png",
        {"Referer": "https://player.test/"},
        str(output),
    )

    assert success is True
    assert downloaded == len(TS_PACKET * 4)
    assert output.read_bytes() == TS_PACKET * 4


def test_universal_fallback_rejects_embedded_youtube_trailer(monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {
                "url": "https://youtube.test/trailer.mp4",
                "title": "Official Trailer",
                "extractor_key": "Youtube",
                "http_headers": {},
            }

    monkeypatch.setattr(
        universal_module,
        "yt_dlp",
        SimpleNamespace(YoutubeDL=FakeYoutubeDL),
    )

    result = UniversalYtDlpExtractor().extract(
        "https://www.bicaps.live/filmler/example.html"
    )

    assert result is None


def test_universal_hls_result_does_not_claim_manifest_is_one_segment(monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {
                "url": "https://cdn.test/index-v1-a1.m3u8",
                "title": "Episode",
                "extractor_key": "Generic",
                "http_headers": {"Referer": "https://player.test/"},
            }

    monkeypatch.setattr(
        universal_module,
        "yt_dlp",
        SimpleNamespace(YoutubeDL=FakeYoutubeDL),
    )

    result = UniversalYtDlpExtractor().extract("https://player.test/embed/episode")

    assert result is not None
    assert result.direct_file is False
    assert result.total_segments == 0
    assert result.audio_tracks[0]["count"] == 0


class _InlineMediaResponse(_Response):
    def __init__(
        self,
        text: str = "",
        status_code: int = 200,
        url: str = "",
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ):
        super().__init__(text, status_code=status_code, url=url)
        self.headers = headers or {}
        self._content = content
        self.closed = False

    def iter_content(self, chunk_size=8192):
        del chunk_size
        yield self._content

    def close(self):
        self.closed = True


class _InlineMediaSession:
    def __init__(self, page_url: str, html: str, media_routes: dict[str, _InlineMediaResponse]):
        self.page_url = page_url
        self.html = html
        self.media_routes = media_routes
        self.probed_urls: list[str] = []
        self.headers = {}
        self.cookies = SimpleNamespace(get_dict=lambda: {"session": "abc123"})

    def get(self, url, **kwargs):
        if url == self.page_url:
            return _InlineMediaResponse(self.html, url=url)
        self.probed_urls.append(url)
        assert kwargs["headers"]["Range"] == "bytes=0-1023"
        return self.media_routes[url]


def _force_yt_dlp_failure(monkeypatch) -> None:
    class FailingYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            raise RuntimeError("generic extractor could not parse this page")

    monkeypatch.setattr(
        universal_module,
        "yt_dlp",
        SimpleNamespace(YoutubeDL=FailingYoutubeDL),
    )


def test_universal_inline_kvs_selects_highest_main_video_and_preserves_headers(monkeypatch) -> None:
    _force_yt_dlp_failure(monkeypatch)
    page_url = "https://example.test/videos/episode/"
    url_360 = "https://cdn.test/8940e0e2cc25377d/504000/504113_360p.mp4/?token=base"
    url_720 = "https://cdn.test/97350a7fab79609f/504000/504113_720p.mp4/?token=low"
    url_1440 = "https://cdn.test/79c31f2e6e0df7d4170e/504000/504113_1440p.mp4/?token=high&amp;x=1"
    html = f"""
        <html><head><title>Inline Movie</title></head><body>
        <script>
        var flashvars = {{
            video_url: '{url_360}',
            video_url_text: '360p',
            video_alt_url2: '{url_720}',
            video_alt_url2_text: '720p',
            video_alt_url4: '{url_1440}',
            video_alt_url4_text: '1440p'
        }};
        var preview = 'https://ads.test/preview_2160p.mp4';
        </script></body></html>
    """
    decoded_1440 = url_1440.replace("&amp;", "&")
    session = _InlineMediaSession(
        page_url,
        html,
        {
            decoded_1440: _InlineMediaResponse(
                status_code=206,
                url="https://edge.test/remote_control.php",
                headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-1023/12345"},
                content=b"\x00\x00\x00\x18ftypisom",
            ),
            url_720: _InlineMediaResponse(
                status_code=206,
                url=url_720,
                headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-1023/8000"},
            ),
            url_360: _InlineMediaResponse(
                status_code=206,
                url=url_360,
                headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-1023/4000"},
            ),
        },
    )

    result = UniversalYtDlpExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_url == decoded_1440
    assert result.title == "Inline Movie"
    assert result.direct_file is True
    assert result.total_segments == 1
    assert result.is_yt_dlp is False
    assert result.video_headers["Referer"] == page_url
    assert result.video_headers["Origin"] == "https://example.test"
    assert result.video_headers["Cookie"] == "session=abc123"
    assert result.to_dict().get("qualities") == [
        {
            "label": "🎬 1440p",
            "resolution": "1440p",
            "bandwidth": 0,
            "url": decoded_1440,
            "direct_file": True,
        },
        {
            "label": "🎬 720p",
            "resolution": "720p",
            "bandwidth": 0,
            "url": url_720,
            "direct_file": True,
        },
        {
            "label": "🎬 360p",
            "resolution": "360p",
            "bandwidth": 0,
            "url": url_360,
            "direct_file": True,
        },
    ]
    assert session.probed_urls == [decoded_1440, url_720, url_360]


def test_direct_mp4_quality_selection_updates_the_download_url_without_manifest_fetch(monkeypatch) -> None:
    class NeverRunThread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr("ui.controllers.resolve.threading.Thread", NeverRunThread)
    controller = SimpleNamespace(
        resolved_film_data={
            "title": "Inline Movie",
            "video_url": "https://cdn.test/movie_1440p.mp4?token=high",
            "video_segments": None,
            "total_segments": 1,
            "direct_file": True,
            "qualities": [
                {
                    "label": "🎬 1440p",
                    "resolution": "1440p",
                    "url": "https://cdn.test/movie_1440p.mp4?token=high",
                    "direct_file": True,
                },
                {
                    "label": "🎬 720p",
                    "resolution": "720p",
                    "url": "https://cdn.test/movie_720p.mp4?token=low",
                    "direct_file": True,
                },
            ],
            "video_headers": {"Referer": "https://example.test/watch"},
        },
        _log=lambda _message: None,
    )

    ResolveControllerMixin._on_quality_changed(controller, "🎬 720p")

    assert controller.resolved_film_data["video_url"] == "https://cdn.test/movie_720p.mp4?token=low"
    assert controller.resolved_film_data["video_segments"] is None
    assert controller.resolved_film_data["total_segments"] == 1
    assert controller.resolved_film_data["direct_file"] is True


def test_resolve_worker_never_applies_tk_updates_when_main_loop_rejects_callback(
    monkeypatch,
) -> None:
    button_updates = []
    scheduled_callbacks = []

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    def reject_after(_delay, callback):
        scheduled_callbacks.append(callback)
        raise RuntimeError("Tk root was destroyed")

    monkeypatch.setattr("ui.controllers.resolve.threading.Thread", ImmediateThread)
    monkeypatch.setattr(
        "ui.controllers.resolve.resolve_film_page",
        lambda *_args, **_kwargs: {
            "success": True,
            "title": "Resolved",
            "video_url": "https://cdn.test/video.mp4",
            "direct_file": True,
        },
    )
    controller = SimpleNamespace(
        entry_film_page=SimpleNamespace(get=lambda: "https://page.test/movie"),
        btn_resolve=SimpleNamespace(
            configure=lambda **kwargs: button_updates.append(kwargs),
        ),
        custom_headers={},
        resolved_film_data=None,
        after=reject_after,
        _log=lambda *_args: None,
        _set_status=lambda *_args, **_kwargs: None,
    )

    ResolveControllerMixin._resolve_film_threaded(controller)

    assert len(scheduled_callbacks) == 1
    assert controller.resolved_film_data is None
    assert button_updates == [{"state": "disabled", "text": "Çözülüyor..."}]


def test_universal_inline_media_falls_back_to_next_working_quality(monkeypatch) -> None:
    _force_yt_dlp_failure(monkeypatch)
    page_url = "https://example.test/watch"
    url_1080 = "https://cdn.test/movie_1080p.mp4?token=ok"
    url_1440 = "https://cdn.test/movie_1440p.mp4?token=expired"
    html = f"""
        <title>Fallback Movie</title>
        <script>player({{
            video_alt_url3: '{url_1080}', video_alt_url3_text: '1080p',
            video_alt_url4: '{url_1440}', video_alt_url4_text: '1440p'
        }});</script>
    """
    session = _InlineMediaSession(
        page_url,
        html,
        {
            url_1440: _InlineMediaResponse(status_code=403, url=url_1440),
            url_1080: _InlineMediaResponse(
                status_code=206,
                url=url_1080,
                headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-15/9999"},
                content=b"\x00\x00\x00\x18ftypisom",
            ),
        },
    )

    result = UniversalYtDlpExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_url == url_1080
    assert session.probed_urls == [url_1440, url_1080]


def test_universal_inline_media_joins_relative_html5_source(monkeypatch) -> None:
    _force_yt_dlp_failure(monkeypatch)
    page_url = "https://example.test/watch/episode"
    media_url = "https://example.test/media/main-1080p.mp4?sig=1"
    html = '<title>HTML5 Movie</title><video><source src="/media/main-1080p.mp4?sig=1"></video>'
    session = _InlineMediaSession(
        page_url,
        html,
        {
            media_url: _InlineMediaResponse(
                status_code=200,
                url=media_url,
                headers={"Content-Type": "video/mp4"},
                content=b"\x00\x00\x00\x18ftypisom",
            ),
        },
    )

    result = UniversalYtDlpExtractor().extract(page_url, session=session)

    assert result is not None
    assert result.video_url == media_url


def test_universal_inline_media_ignores_unscoped_preview_mp4_strings(monkeypatch) -> None:
    _force_yt_dlp_failure(monkeypatch)
    page_url = "https://example.test/watch"
    html = """
        <title>No Main Video</title>
        <script>
        var recommendation = 'https://cdn.test/recommendation_2160p.mp4';
        var preview = 'https://cdn.test/preview.mp4';
        </script>
    """
    session = _InlineMediaSession(page_url, html, {})

    result = UniversalYtDlpExtractor().extract(page_url, session=session)

    assert result is None
    assert session.probed_urls == []


def test_registry_delegates_unknown_parent_iframe_to_registered_embed_extractor() -> None:
    page_url = "https://unknown-parent.test/watch/movie"
    embed_url = "https://known-player.test/player?id=42"

    class KnownEmbedExtractor(BaseExtractor):
        @property
        def name(self) -> str:
            return "Known Embed"

        def can_handle(self, url: str) -> bool:
            return "known-player.test" in url

        def extract(self, url: str, session=None, log_callback=None):
            del session, log_callback
            if not self.can_handle(url):
                return None
            return ExtractorResult(
                success=True,
                title="Embed Placeholder",
                video_url="https://cdn.test/movie.mp4",
                direct_file=True,
                total_segments=1,
                raw_url=url,
            )

    registry = ExtractorRegistry()
    registry._extractors = [KnownEmbedExtractor()]
    session = _InlineMediaSession(
        page_url,
        f'<html><head><title>Outer Movie</title></head><body><iframe src="{embed_url}"></iframe></body></html>',
        {},
    )

    try:
        result = registry.resolve(page_url, session=session)
    except ExtractorError:
        result = None

    assert result is not None
    assert result["title"] == "Outer Movie"
    assert result["video_url"] == "https://cdn.test/movie.mp4"
    assert result["raw_url"] == page_url


def test_fullhd_mom_master_parser_selects_highest_bandwidth_not_last_variant() -> None:
    master_url = "https://cdn.test/manifests/master.m3u8"
    high_url = "https://cdn.test/manifests/high.m3u8"
    low_url = "https://cdn.test/manifests/low.m3u8"
    master = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
high.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
"""
    session = _RouteSession({
        high_url: _Response(
            "#EXTM3U\n#EXTINF:6.0,\nhigh-000.ts\n#EXTINF:6.0,\nhigh-001.ts\n",
            url=high_url,
        ),
        low_url: _Response(
            "#EXTM3U\n#EXTINF:6.0,\nlow-000.ts\n#EXTINF:6.0,\nlow-001.ts\n",
            url=low_url,
        ),
    })

    segments = FullHDFilmizleMomExtractor()._parse_m3u8(
        session,
        master_url,
        master,
        {"Referer": "https://player.test/"},
    )

    assert segments == [
        "https://cdn.test/manifests/high-000.ts",
        "https://cdn.test/manifests/high-001.ts",
    ]


def test_fullhd_mom_fastplay_selects_highest_bandwidth_variant() -> None:
    fastplay_url = "https://fastplay.test/embed/movie"
    master_url = "https://fastplay.test/manifests/master.m3u8"
    low_url = "https://fastplay.test/manifests/low.m3u8"
    high_url = "https://fastplay.test/manifests/high.m3u8"
    master = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
high.m3u8
"""
    session = _RouteSession({
        fastplay_url: _Response(
            'window.FSP = {stream: "/manifests/master.m3u8"};',
            url=fastplay_url,
        ),
        master_url: _Response(master, url=master_url),
        low_url: _Response(
            "#EXTM3U\n#EXTINF:6.0,\nlow-000.ts\n#EXTINF:6.0,\nlow-001.ts\n",
            url=low_url,
        ),
        high_url: _Response(
            "#EXTM3U\n#EXTINF:6.0,\nhigh-000.ts\n#EXTINF:6.0,\nhigh-001.ts\n",
            url=high_url,
        ),
    })

    result = FullHDFilmizleMomExtractor()._resolve_fastplay(
        session,
        fastplay_url,
        "https://setplay.test/player/",
        "Movie",
        {"User-Agent": "Regression Test"},
    )

    assert result is not None
    assert result.video_segments == [
        "https://fastplay.test/manifests/high-000.ts",
        "https://fastplay.test/manifests/high-001.ts",
    ]
    assert result.video_durations == [6.0, 6.0]


def test_fullhd_mom_parser_treats_txt_stream_variant_as_child_playlist() -> None:
    master_url = "https://fastplay.test/manifests/master.txt"
    child_url = "https://fastplay.test/manifests/video~video.txt"
    master = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video~video.txt
"""
    session = _RouteSession({
        child_url: _Response(
            "#EXTM3U\n#EXTINF:6.0,\nvideo-000.ts\n#EXTINF:6.0,\nvideo-001.ts\n",
            url=child_url,
        ),
    })

    segments = FullHDFilmizleMomExtractor()._parse_m3u8(
        session,
        master_url,
        master,
        {"Referer": "https://fastplay.test/"},
    )

    assert segments == [
        "https://fastplay.test/manifests/video-000.ts",
        "https://fastplay.test/manifests/video-001.ts",
    ]


def test_dizitime_falls_back_when_curl_session_cannot_load_ca_file(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    api_url = "https://dizitime.test/getvideo/645154_t"
    embed_url = "https://vidmoly.test/embed-episode.html"
    encoded_api = base64.b64encode(json.dumps({
        "status": "success",
        "url": embed_url,
    }).encode("utf-8")).decode("ascii")
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="645154" data-name="Moly">Moly</option>'
        ),
        api_url: _Response(encoded_api),
    })

    class FailingCurlSession:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("curl: (77) error setting certificate verify locations")

    monkeypatch.setattr(
        extractor_facade,
        "c_requests",
        SimpleNamespace(Session=lambda **_kwargs: FailingCurlSession()),
    )
    monkeypatch.setattr(
        extractor_facade,
        "resolve_film_page",
        lambda *_args, **_kwargs: {
            "success": True,
            "title": "Nested",
            "video_url": "https://cdn.test/index.m3u8",
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        },
    )

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert result["title"] == "Episode"
    assert result["video_url"] == "https://cdn.test/index.m3u8"


def test_dizitime_resolves_redirected_getvideo_bridge_before_registering_audio_track(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    api_url = "https://dizitime.test/getvideo/645154_t"
    bridge_url = "https://dizitime-mirror.test/getvideo/645154_t"
    embed_url = "https://dtm.molystream.org/embed/original-source"
    manifest_url = "https://cdn.test/original.m3u8"
    encoded_bridge = base64.b64encode(json.dumps({
        "status": "success",
        "url": embed_url,
    }).encode("utf-8")).decode("ascii")
    redirect_response = _Response("", status_code=302, url=api_url)
    redirect_response.headers["Location"] = bridge_url
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="645154" data-name="DTime">Original</option>'
        ),
        api_url: redirect_response,
        bridge_url: _Response(encoded_bridge, url=bridge_url),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)

    def resolve_embed(url, **_kwargs):
        if url != embed_url:
            return None
        return {
            "success": True,
            "title": "Original",
            "video_url": manifest_url,
            "video_headers": {"Referer": embed_url},
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        }

    monkeypatch.setattr(extractor_facade, "resolve_film_page", resolve_embed)

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert result["video_url"] == manifest_url
    assert result["audio_tracks"][0]["url"] == manifest_url


def test_dizitime_uses_impersonated_session_for_redirected_getvideo_bridge(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    api_url = "https://dizitime.test/getvideo/645154_t"
    bridge_url = "https://dizitime-mirror.test/getvideo/645154_t"
    embed_url = "https://dtm.molystream.org/embed/original-source"
    manifest_url = "https://cdn.test/original.m3u8"
    encoded_bridge = base64.b64encode(json.dumps({
        "status": "success",
        "url": embed_url,
    }).encode("utf-8")).decode("ascii")
    redirect_response = _Response("", status_code=302, url=api_url)
    redirect_response.headers["Location"] = bridge_url
    page_response = _Response(
        '<title>Episode - Dizitime</title>'
        '<option value="645154" data-name="DTime">Original</option>',
        url=page_url,
    )
    curl_session = _RouteSession({
        page_url: page_response,
        api_url: redirect_response,
        bridge_url: _Response(encoded_bridge, url=bridge_url),
    })
    requests_session = _RouteSession({
        page_url: page_response,
        bridge_url: _Response("blocked", status_code=403, url=bridge_url),
    })
    monkeypatch.setattr(
        extractor_facade,
        "c_requests",
        SimpleNamespace(Session=lambda **_kwargs: curl_session),
    )
    monkeypatch.setattr(
        extractor_facade,
        "resolve_film_page",
        lambda url, **_kwargs: ({
            "success": True,
            "title": "Original",
            "video_url": manifest_url,
            "video_headers": {"Referer": embed_url},
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        } if url == embed_url else None),
    )

    result = dizitime_module.resolve_dizitime_page(page_url, session=requests_session)

    assert result is not None
    assert result["video_url"] == manifest_url


def test_dizitime_does_not_register_empty_getvideo_bridge_as_media(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    api_url = "https://dizitime.test/getvideo/645154_t"
    bridge_url = "https://dizitime-mirror.test/getvideo/645154_t"
    redirect_response = _Response("", status_code=302, url=api_url)
    redirect_response.headers["Location"] = bridge_url
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="645154" data-name="Play">Original</option>'
        ),
        api_url: redirect_response,
        bridge_url: _Response("", status_code=200, url=bridge_url),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)
    monkeypatch.setattr(
        extractor_facade,
        "resolve_film_page",
        lambda *_args, **_kwargs: {
            "success": True,
            "video_url": bridge_url,
            "video_segments": [],
        },
    )

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is None


def test_dizitime_without_watch_type_tabs_keeps_one_original_source(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    tr_embed = "https://vidmoly.test/embed-tr.html"
    tr_duplicate_embed = "https://vidmoly.test/embed-tr-mirror.html"
    en_embed = "https://vidmoly.test/embed-en.html"

    def encoded_url(url):
        return base64.b64encode(json.dumps({
            "status": "success",
            "url": url,
        }).encode("utf-8")).decode("ascii")

    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="10101" data-name="Moly">Turkish</option>'
            '<option value="30303" data-name="Moly">Turkish mirror</option>'
            '<option value="20202" data-name="Moly">Original</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(encoded_url(tr_embed)),
        "https://dizitime.test/getvideo/30303_t": _Response(encoded_url(tr_duplicate_embed)),
        "https://dizitime.test/getvideo/20202_t": _Response(encoded_url(en_embed)),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)

    def resolve_embed(url, **_kwargs):
        is_turkish = url != en_embed
        if url == tr_duplicate_embed:
            manifest = "https://cdn.test/tr.m3u8?token=second"
        elif is_turkish:
            manifest = "https://cdn.test/tr.m3u8?token=first"
        else:
            manifest = "https://cdn.test/en.m3u8"
        return {
            "success": True,
            "title": "Episode tr" if is_turkish else "Episode ing",
            "video_url": manifest,
            "video_headers": {"Referer": url},
            "video_segments": [],
            "audio_tracks": [{
                "name": "Generic Ak\u0131\u015f\u0131",
                "lang": "tur",
                "url": manifest,
                "count": 0,
            }],
            "total_segments": 0,
            "direct_file": False,
        }

    monkeypatch.setattr(extractor_facade, "resolve_film_page", resolve_embed)

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert [track["lang"] for track in result["audio_tracks"]] == ["eng"]
    assert all(track["is_standalone_stream"] for track in result["audio_tracks"])
    assert [track["url"] for track in result["audio_tracks"]] == [
        "https://cdn.test/tr.m3u8?token=first",
    ]


def test_dizitime_combines_subtitled_and_dubbed_watch_type_pages(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"
    dubbed_url = "https://dizitime.test/episode-turkce-dublaj-izle"
    subtitle_embed = "https://vidmoly.test/embed-subtitle.html"
    dubbed_embed = "https://dtm.molystream.test/embed-dubbed.html"

    def encoded_url(url):
        return base64.b64encode(json.dumps({
            "status": "success",
            "url": url,
        }).encode("utf-8")).decode("ascii")

    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            f'<a href="{page_url}" class="btn-watchType btn-purple">T\u00fcrk\u00e7e Altyaz\u0131l\u0131</a>'
            f'<a href="{dubbed_url}" class="btn-watchType">T\u00fcrk\u00e7e Dublaj</a>'
            '<option value="10101" data-name="DTime" '
            'data-content="<img src=\'images/TR.png\' /> Kaynak 1">Kaynak</option>'
        ),
        dubbed_url: _Response(
            '<title>Episode - Dizitime</title>'
            f'<a href="{page_url}" class="btn-watchType">T\u00fcrk\u00e7e Altyaz\u0131l\u0131</a>'
            f'<a href="{dubbed_url}" class="btn-watchType btn-purple">T\u00fcrk\u00e7e Dublaj</a>'
            '<option value="20202" data-name="DTime">Kaynak</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(encoded_url(subtitle_embed)),
        "https://dizitime.test/getvideo/20202_t": _Response(encoded_url(dubbed_embed)),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)

    def resolve_embed(url, **_kwargs):
        suffix = "dubbed" if url == dubbed_embed else "subtitled"
        return {
            "success": True,
            "title": "Misleading title ing",
            "video_url": f"https://cdn.test/{suffix}.m3u8",
            "video_headers": {"Referer": url},
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        }

    monkeypatch.setattr(extractor_facade, "resolve_film_page", resolve_embed)

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert [track["lang"] for track in result["audio_tracks"]] == ["tur", "eng"]
    assert [track["url"] for track in result["audio_tracks"]] == [
        "https://cdn.test/dubbed.m3u8",
        "https://cdn.test/subtitled.m3u8",
    ]


def test_dizitime_falls_back_to_working_dubbed_tab_when_original_source_is_dead(
    monkeypatch,
) -> None:
    page_url = "https://dizitime.test/episode"
    dubbed_url = "https://dizitime.test/episode-turkce-dublaj-izle"
    dead_embed = "https://vidmoly.test/dead-original.html"
    dubbed_embed = "https://dtm.molystream.test/working-dubbed.html"

    def encoded_url(url):
        return base64.b64encode(json.dumps({
            "status": "success",
            "url": url,
        }).encode("utf-8")).decode("ascii")

    watch_tabs = (
        f'<a href="{page_url}" class="btn-watchType">T\u00fcrk\u00e7e Altyaz\u0131l\u0131</a>'
        f'<a href="{dubbed_url}" class="btn-watchType">T\u00fcrk\u00e7e Dublaj</a>'
    )
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            + watch_tabs
            + '<option value="10101" data-name="Moly">Original</option>'
        ),
        dubbed_url: _Response(
            '<title>Episode - Dizitime</title>'
            + watch_tabs
            + '<option value="20202" data-name="DTime">Dublaj</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(encoded_url(dead_embed)),
        "https://dizitime.test/getvideo/20202_t": _Response(encoded_url(dubbed_embed)),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)

    def resolve_embed(url, **_kwargs):
        if url == dead_embed:
            return None
        return {
            "success": True,
            "title": "Episode dubbed",
            "video_url": "https://cdn.test/dubbed.m3u8",
            "video_headers": {"Referer": url},
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        }

    monkeypatch.setattr(extractor_facade, "resolve_film_page", resolve_embed)

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert result["video_url"] == "https://cdn.test/dubbed.m3u8"
    assert [(track["lang"], track["url"]) for track in result["audio_tracks"]] == [
        ("tur", "https://cdn.test/dubbed.m3u8"),
    ]


def test_dizitime_resolves_encrypted_dtime_turkish_source(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode-turkce-dublaj-izle"
    embed_url = "https://dtm.molystream.org/embed/turkish-source"
    manifest_url = "https://dbx.molystream.org/embed/sheila/turkish-source"
    encoded_api = base64.b64encode(json.dumps({
        "status": "success",
        "url": embed_url,
    }).encode("utf-8")).decode("ascii")
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="10101" data-name="DTime" '
            'data-content="<img src=\'images/TR.png\' /> Kaynak 1">TR</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(encoded_api),
        embed_url: _Response('CryptoJS.AES.decrypt("cipher", "key")'),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)
    monkeypatch.setattr(extractor_facade, "resolve_film_page", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        dizitime_module,
        "decrypt_cryptojs_aes",
        lambda _cipher, _key: f"file: '{manifest_url}'",
        raising=False,
    )

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert result["video_url"] == manifest_url
    assert [(track["name"], track["lang"]) for track in result["audio_tracks"]] == [
        ("T\u00fcrk\u00e7e Dublaj", "tur"),
    ]


def test_dizitime_resolves_encrypted_sheila_dubbed_source(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode-turkce-dublaj-izle"
    embed_url = "https://ydt.sheila.stream/embed/dubbed-source"
    manifest_url = "https://yd.sheila.stream/embed/sheila/dubbed-source"
    encoded_api = base64.b64encode(json.dumps({
        "status": "success",
        "url": embed_url,
    }).encode("utf-8")).decode("ascii")
    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="10101" data-name="DTime">Dublaj</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(encoded_api),
        embed_url: _Response('CryptoJS.AES.decrypt("cipher", "key")'),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)
    monkeypatch.setattr(extractor_facade, "resolve_film_page", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        dizitime_module,
        "decrypt_cryptojs_aes",
        lambda _cipher, _key: f"file: '{manifest_url}'",
    )

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert result["video_url"] == manifest_url
    assert [track["lang"] for track in result["audio_tracks"]] == ["tur"]


def test_dizitime_does_not_offer_dual_audio_for_two_english_mirrors(monkeypatch) -> None:
    page_url = "https://dizitime.test/episode"

    def encoded_url(url):
        return base64.b64encode(json.dumps({
            "status": "success",
            "url": url,
        }).encode("utf-8")).decode("ascii")

    session = _RouteSession({
        page_url: _Response(
            '<title>Episode - Dizitime</title>'
            '<option value="10101" data-name="Moly" '
            'data-content="<img src=\'images/EN.png\' /> Kaynak 1">EN 1</option>'
            '<option value="20202" data-name="Moly" '
            'data-content="<img src=\'images/EN.png\' /> Kaynak 2">EN 2</option>'
        ),
        "https://dizitime.test/getvideo/10101_t": _Response(
            encoded_url("https://vidmoly.test/embed-en-1.html")
        ),
        "https://dizitime.test/getvideo/20202_t": _Response(
            encoded_url("https://vidmoly.test/embed-en-2.html")
        ),
    })
    monkeypatch.setattr(extractor_facade, "c_requests", None)

    def resolve_embed(url, **_kwargs):
        suffix = "one" if "en-1" in url else "two"
        return {
            "success": True,
            "title": "Episode ing",
            "video_url": f"https://cdn.test/{suffix}.m3u8",
            "video_headers": {"Referer": url},
            "video_segments": [],
            "audio_tracks": [],
            "total_segments": 0,
            "direct_file": False,
        }

    monkeypatch.setattr(extractor_facade, "resolve_film_page", resolve_embed)

    result = dizitime_module.resolve_dizitime_page(page_url, session=session)

    assert result is not None
    assert [(track["name"], track["lang"]) for track in result["audio_tracks"]] == [
        ("Orijinal / T\u00fcrk\u00e7e Altyaz\u0131l\u0131", "eng"),
    ]


def test_multi_audio_resolves_extensionless_hls_before_segment_detection(
    monkeypatch,
    tmp_path,
) -> None:
    video_manifest = "https://dbx.test/embed/sheila/24347-source"
    audio_manifest = "https://dbx.test/embed/original/644758-source"
    manifests = {
        video_manifest: [
            "https://dbx.test/video-000.ts",
            "https://dbx.test/video-001.ts",
            "https://dbx.test/video-002.ts",
        ],
        audio_manifest: [
            "https://dbx.test/audio-000.ts",
            "https://dbx.test/audio-001.ts",
            "https://dbx.test/audio-002.ts",
        ],
    }
    task_counts = []
    progress_events = []
    engine = VideoDownloadEngine()
    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        pipeline_module,
        "extract_m3u8_info",
        lambda url, _headers=None, **kwargs: (
            (manifests.get(url, []), [None] * len(manifests.get(url, [])))
            if kwargs.get("return_timeline")
            else manifests.get(url, [])
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_segment_range",
        lambda *_args, **_kwargs: (0, 0),
    )
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)

    def download(tasks, _headers=None, progress_callback=None, **_kwargs):
        task_counts.append(len(tasks))
        downloaded = 0
        for completed, (_index, _url, path) in enumerate(tasks, start=1):
            Path(path).write_bytes(TS_PACKET)
            downloaded += len(TS_PACKET)
            if progress_callback:
                progress_callback(completed, len(tasks), downloaded)
        return len(tasks), downloaded, []

    def mux(v_concat_path, audio_concats, output_filepath, **_kwargs):
        assert Path(v_concat_path).is_file()
        assert len(audio_concats) == 1
        Path(output_filepath).write_bytes(b"mp4")
        return True

    monkeypatch.setattr(engine, "download_stream_segments", download)
    monkeypatch.setattr(engine, "mux_multi_audio_and_video", mux)

    success, _result = engine.run_multi_audio_download(
        video_url=video_manifest,
        video_headers={"Referer": "https://dtm.test/embed"},
        audio_tracks=[
            {
                "name": "T\u00fcrk\u00e7e Dublaj",
                "lang": "tur",
                "url": video_manifest,
                "headers": {"Referer": "https://dtm.test/embed"},
            },
            {
                "name": "Orijinal",
                "lang": "eng",
                "url": audio_manifest,
                "headers": {"Referer": "https://vidmoly.test/embed"},
            },
        ],
        output_filepath=str(tmp_path / "episode.mp4"),
        total_segments=0,
        thread_count=4,
        progress_callback=lambda *args: progress_events.append(args),
    )

    assert success is True
    assert sorted(task_counts) == [3, 3]
    assert any(completed > 0 and total == 3 for completed, total, *_ in progress_events)


def test_single_stream_resolves_extensionless_hls_before_numeric_segment_detection(
    monkeypatch,
    tmp_path,
) -> None:
    manifest = "https://yd.test/embed/moly/26357-source"
    segments = [
        "https://cdn.test/seg-000.ts",
        "https://cdn.test/seg-001.ts",
    ]
    engine = VideoDownloadEngine()
    monkeypatch.setattr(pipeline_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        pipeline_module,
        "extract_m3u8_info",
        lambda url, _headers=None, **_kwargs: segments if url == manifest else [],
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_segment_range",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("numeric probe used")),
    )
    monkeypatch.setattr(pipeline_module, "fetch_and_save_subtitle", lambda **_kwargs: None)
    monkeypatch.setattr(pipeline_module, "get_ffmpeg_path", lambda: None)

    def download(tasks, _headers=None, progress_callback=None, **_kwargs):
        for completed, (_index, _url, path) in enumerate(tasks, start=1):
            Path(path).write_bytes(TS_PACKET)
            if progress_callback:
                progress_callback(completed, len(tasks), completed * len(TS_PACKET))
        return len(tasks), len(tasks) * len(TS_PACKET), []

    monkeypatch.setattr(engine, "download_stream_segments", download)

    success, _result = engine.run_download(
        sample_url=manifest,
        output_filepath=str(tmp_path / "episode.mp4"),
        thread_count=4,
    )

    assert success is True
