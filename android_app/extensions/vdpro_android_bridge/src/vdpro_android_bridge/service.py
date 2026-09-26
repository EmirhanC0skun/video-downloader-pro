from typing import Any

import flet as ft


@ft.control("AndroidMediaService")
class AndroidMediaService(ft.Service):
    """Native Android lifecycle, notification and gallery operations."""

    async def request_permissions(self) -> dict[str, Any] | None:
        return await self._invoke_method("request_permissions")

    async def http_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_timeout = float(request.get("timeout_seconds") or 15) + 10
        return await self._invoke_method(
            "http_request",
            request,
            timeout=request_timeout,
        )

    async def start_download(self, title: str) -> bool:
        return bool(
            await self._invoke_method("start_download", {"title": title})
        )

    async def update_download(
        self,
        title: str,
        progress: int,
        speed: str = "",
        eta: str = "",
    ) -> bool:
        return bool(
            await self._invoke_method(
                "update_download",
                {
                    "title": title,
                    "progress": max(0, min(100, int(progress))),
                    "speed": speed,
                    "eta": eta,
                },
            )
        )

    async def finish_download(
        self,
        title: str,
        success: bool,
        message: str = "",
    ) -> bool:
        return bool(
            await self._invoke_method(
                "finish_download",
                {"title": title, "success": success, "message": message},
            )
        )

    async def publish_video(
        self,
        path: str,
        album: str = "VideoDownloaderPro",
    ) -> bool:
        return bool(
            await self._invoke_method(
                "publish_video", {"path": path, "album": album}
            )
        )

    async def stop_download(self) -> bool:
        return bool(await self._invoke_method("stop_download"))

    async def open_file(self, path: str) -> bool:
        return bool(await self._invoke_method("open_file", {"path": path}))
