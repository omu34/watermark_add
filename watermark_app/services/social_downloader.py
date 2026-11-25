import ipaddress
import re
import socket
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import yt_dlp

from watermark_app.config import MAX_SOCIAL_BYTES

_ALLOWED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "facebook.com",
    "www.facebook.com",
    "fb.watch",
)
_FORMAT_ID = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class SocialDownloadError(RuntimeError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def validate_social_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise SocialDownloadError("The media link URL is invalid.", 400) from exc
    hostname = (parsed.hostname or "").rstrip(".").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise SocialDownloadError("The media link URL is invalid.", 400) from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or hostname not in _ALLOWED_HOSTS
    ):
        raise SocialDownloadError(
            "Enter a secure HTTPS link from YouTube, Instagram, TikTok, X, or Facebook.",
            400,
        )

    try:
        addresses = {
            ipaddress.ip_address(result[4][0].split("%")[0])
            for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise SocialDownloadError("The media link host could not be reached.", 422) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise SocialDownloadError("The media link host is not publicly routable.", 400)
    return url.strip()


def _youtube_dl_options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_SOCIAL_BYTES,
        "socket_timeout": 12,
        "retries": 1,
        "fragment_retries": 1,
        "ignoreerrors": False,
    }


def _extract_info(url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL(_youtube_dl_options()) as downloader:
            info = downloader.extract_info(url, download=False)
    except (
        yt_dlp.utils.DownloadError,
        yt_dlp.utils.ExtractorError,
        urllib.error.URLError,
        OSError,
        socket.timeout,
    ) as exc:
        detail = str(exc).lower()
        if "private" in detail or "login" in detail or "sign in" in detail:
            raise SocialDownloadError(
                "This media is private or requires an account login.", 403
            ) from exc
        if "429" in detail or "rate limit" in detail or "too many requests" in detail:
            raise SocialDownloadError(
                "The platform is rate limiting requests. Please try again later.", 429
            ) from exc
        raise SocialDownloadError(
            "The platform could not provide this media. Check the link and try again."
        ) from exc
    if not info or info.get("_type") == "playlist":
        raise SocialDownloadError("Playlists are not supported. Use a single-media link.", 400)
    return info


def _format_options(info: dict) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for media_format in info.get("formats") or []:
        format_id = str(media_format.get("format_id", ""))
        extension = str(media_format.get("ext", "")).lower()
        if (
            not format_id
            or not _FORMAT_ID.fullmatch(format_id)
            or format_id in seen
            or extension != "mp4"
            or media_format.get("vcodec") == "none"
        ):
            continue
        seen.add(format_id)
        resolution = media_format.get("resolution") or (
            f"{media_format.get('height')}p" if media_format.get("height") else "MP4"
        )
        options.append({"format_id": format_id, "label": f"MP4 - {resolution}"})
    options.sort(
        key=lambda option: next(
            (
                int(item.get("height") or 0)
                for item in info.get("formats") or []
                if str(item.get("format_id")) == option["format_id"]
            ),
            0,
        ),
        reverse=True,
    )
    if options:
        return options[:16]

    extension = str(info.get("ext", "")).lower()
    if extension in _IMAGE_EXTS:
        return [{"format_id": "__best__", "label": "Image"}]
    return [{"format_id": "__best__", "label": "Best available"}]


def _download_format(format_id: str, info: dict) -> str:
    if format_id == "__best__":
        return "best[ext=mp4]/best"
    selected = next(
        (
            media_format
            for media_format in info.get("formats") or []
            if str(media_format.get("format_id")) == format_id
        ),
        None,
    )
    if not selected:
        raise SocialDownloadError("Choose a media quality from the inspected options.", 400)
    if selected.get("acodec") == "none":
        return f"{format_id}+bestaudio/{format_id}"
    return format_id


def inspect_social_media(url: str) -> dict:
    safe_url = validate_social_url(url)
    info = _extract_info(safe_url)
    return {
        "title": str(info.get("title") or "Social media download")[:200],
        "formats": _format_options(info),
    }


def download_social_media(url: str, format_id: str) -> tuple[TemporaryDirectory, Path]:
    safe_url = validate_social_url(url)
    info = _extract_info(safe_url)
    valid_formats = {item["format_id"] for item in _format_options(info)}
    if format_id not in valid_formats:
        raise SocialDownloadError("Choose a media quality from the inspected options.", 400)
    if format_id != "__best__" and not _FORMAT_ID.fullmatch(format_id):
        raise SocialDownloadError("The selected media format is invalid.", 400)

    temporary_directory = TemporaryDirectory(prefix="watermark-social-")
    output_dir = Path(temporary_directory.name)
    options = _youtube_dl_options()
    options.update(
        {
            "format": _download_format(format_id, info),
            "merge_output_format": "mp4",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "overwrites": True,
        }
    )
    try:
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([safe_url])
        except (
            yt_dlp.utils.DownloadError,
            yt_dlp.utils.ExtractorError,
            urllib.error.URLError,
            OSError,
            socket.timeout,
        ) as exc:
            detail = str(exc).lower()
            if "429" in detail or "rate limit" in detail or "too many requests" in detail:
                raise SocialDownloadError(
                    "The platform is rate limiting requests. Please try again later.", 429
                ) from exc
            raise SocialDownloadError(
                "Media download failed. It may be private, unavailable, or too large."
            ) from exc

        candidates = sorted(path for path in output_dir.iterdir() if path.is_file())
        if len(candidates) != 1:
            raise SocialDownloadError("The platform did not return a downloadable media file.")
        if candidates[0].stat().st_size > MAX_SOCIAL_BYTES:
            raise SocialDownloadError(
                "The downloaded media exceeds the 64 MB size limit.", 413
            )
        return temporary_directory, candidates[0]
    except BaseException:
        temporary_directory.cleanup()
        raise
