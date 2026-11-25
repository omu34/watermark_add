import json
import math
import subprocess
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from watermark_app.config import (
    ALLOWED_IMAGE_EXTS,
    ALLOWED_VIDEO_EXTS,
    FFMPEG_TIMEOUT_SECONDS,
    MAX_CANVAS_HEIGHT,
    MAX_CANVAS_WIDTH,
    VIDEO_FPS,
    VIDEO_MAX_SECONDS,
)
from watermark_app.services.banner_overlay import build_banner_overlay
from watermark_app.services.media import VideoToolUnavailableError, require_video_tool

MAX_IMAGE_PIXELS = 12_000_000
MAX_VIDEO_WIDTH = 1920
MAX_VIDEO_HEIGHT = 1080
COLLAGE_BORDER_WIDTH = 2
COLLAGE_BORDER_COLOR = (255, 255, 255)
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class MediaValidationError(ValueError):
    pass


def layout_boxes(count: int, width: int, height: int) -> list[tuple[int, int, int, int]]:
    if count < 1 or count > 4:
        raise MediaValidationError("Select between one and four media files.")
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise MediaValidationError("Canvas dimensions must be positive even numbers.")

    half_width = width // 2
    half_height = height // 2
    layouts = {
        1: [(0, 0, width, height)],
        2: [(0, 0, half_width, height), (half_width, 0, half_width, height)],
        3: [
            (0, 0, half_width, half_height),
            (half_width, 0, half_width, half_height),
            (0, half_height, width, half_height),
        ],
        4: [
            (0, 0, half_width, half_height),
            (half_width, 0, half_width, half_height),
            (0, half_height, half_width, half_height),
            (half_width, half_height, half_width, half_height),
        ],
    }
    return layouts[count]


def _validate_images(media_paths: list[Path]) -> None:
    for path in media_paths:
        if path.suffix.lower() not in ALLOWED_IMAGE_EXTS:
            continue
        try:
            with Image.open(path) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise MediaValidationError(
                        f"{path.name} exceeds the supported image resolution."
                    )
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise MediaValidationError(f"{path.name} is not a valid image.") from exc


def _banner_path(
    width: int,
    height: int,
    output_dir: Path,
    banner: dict[str, Any],
    logo_path: Path | None,
) -> Path:
    try:
        top_opacity = int(banner.get("top_opacity", 210))
        bottom_opacity = int(banner.get("bottom_opacity", 220))
    except (TypeError, ValueError) as exc:
        raise MediaValidationError("Banner opacity must be a number from 0 to 255.") from exc
    if not 0 <= top_opacity <= 255 or not 0 <= bottom_opacity <= 255:
        raise MediaValidationError("Banner opacity must be between 0 and 255.")

    return build_banner_overlay(
        width=width,
        height=height,
        output_dir=output_dir,
        title=str(banner.get("title", ""))[:300],
        description=str(banner.get("description", ""))[:500],
        top_color=str(banner.get("top_color", "#312e81")),
        top_opacity=top_opacity,
        bottom_color=str(banner.get("bottom_color", "#0f172a")),
        bottom_opacity=bottom_opacity,
        logo_path=logo_path,
    )


def _compose_still_images(
    media_paths: list[Path],
    output_dir: Path,
    width: int,
    height: int,
    banner_path: Path,
) -> Path:
    canvas = Image.new("RGB", (width, height), "#111827")
    for media_path, (x, y, slot_width, slot_height) in zip(
        media_paths, layout_boxes(len(media_paths), width, height)
    ):
        try:
            with Image.open(media_path) as source:
                tile = ImageOps.fit(
                    source.convert("RGB"),
                    (slot_width, slot_height),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
            ImageDraw.Draw(tile).rectangle(
                (0, 0, slot_width - 1, slot_height - 1),
                outline=COLLAGE_BORDER_COLOR,
                width=COLLAGE_BORDER_WIDTH,
            )
            canvas.paste(tile, (x, y))
        except (UnidentifiedImageError, OSError) as exc:
            raise MediaValidationError(f"{media_path.name} is not a valid image.") from exc

    with Image.open(banner_path) as overlay:
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay.convert("RGBA"))
    output_path = output_dir / f"collage_{uuid.uuid4().hex}.jpg"
    canvas.convert("RGB").save(output_path, "JPEG", quality=88, optimize=True)
    return output_path


def _probe_duration(video_path: Path) -> float:
    require_video_tool("ffprobe")
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MediaValidationError(
            f"Could not read the duration of {video_path.name}."
        ) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise MediaValidationError(f"{video_path.name} has an invalid video duration.")
    return duration


def _validate_video_dimensions(video_path: Path) -> None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        stream = json.loads(result.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise MediaValidationError(f"Could not read the dimensions of {video_path.name}.") from exc
    if (
        width <= 0
        or height <= 0
        or width > MAX_VIDEO_WIDTH
        or height > MAX_VIDEO_HEIGHT
        or width * height > MAX_VIDEO_WIDTH * MAX_VIDEO_HEIGHT
    ):
        raise MediaValidationError(
            f"{video_path.name} exceeds the supported 1920 × 1080 input resolution."
        )


def _compose_video(
    media_paths: list[Path],
    output_dir: Path,
    width: int,
    height: int,
    banner_path: Path,
) -> Path:
    require_video_tool("ffmpeg")
    video_indices = [
        index for index, path in enumerate(media_paths) if path.suffix.lower() in ALLOWED_VIDEO_EXTS
    ]
    durations = [
        _probe_duration(media_paths[index])
        for index in video_indices
    ]
    for index in video_indices:
        _validate_video_dimensions(media_paths[index])
    duration = min(max(durations), VIDEO_MAX_SECONDS)
    boxes = layout_boxes(len(media_paths), width, height)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for media_path in media_paths:
        if media_path.suffix.lower() in ALLOWED_IMAGE_EXTS:
            command.extend(["-loop", "1", "-framerate", str(VIDEO_FPS)])
        else:
            command.extend(["-threads", "1"])
        command.extend(["-i", str(media_path)])
    banner_input_index = len(media_paths)
    command.extend(["-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(banner_path)])

    filters: list[str] = []
    labels = []
    for index, (x, y, slot_width, slot_height) in enumerate(boxes):
        label = f"tile{index}"
        filters.append(
            f"[{index}:v]fps={VIDEO_FPS},scale={slot_width}:{slot_height}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={slot_width}:{slot_height},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t={COLLAGE_BORDER_WIDTH},"
            f"setsar=1,"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={duration:.3f}[{label}]"
        )
        labels.append(f"[{label}]")

    if len(media_paths) == 1:
        x, y, _, _ = boxes[0]
        filters.append(
            f"{labels[0]}pad={width}:{height}:{x}:{y}:color=black[grid]"
        )
    else:
        stack_layout = "|".join(f"{x}_{y}" for x, y, _, _ in boxes)
        filters.append(
            f"{''.join(labels)}xstack=inputs={len(labels)}:layout={stack_layout}:"
            "fill=black[grid]"
        )

    filters.append(
        f"[grid][{banner_input_index}:v]overlay=0:0:shortest=1[outv]"
    )
    output_path = output_dir / f"collage_{uuid.uuid4().hex}.mp4"
    primary_video_index = video_indices[0]
    command.extend(
        [
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outv]",
            "-map",
            f"{primary_video_index}:a?",
            "-t",
            f"{duration:.3f}",
            "-r",
            str(VIDEO_FPS),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaValidationError("Video collage exceeded the 150-second processing limit.") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaValidationError("FFmpeg could not process one or more uploaded videos.") from exc
    return output_path


def compose_collage(
    media_paths: list[Path],
    output_dir: Path,
    width: int,
    height: int,
    banner: dict[str, Any],
    logo_path: Path | None = None,
) -> Path:
    if not 1 <= len(media_paths) <= 4:
        raise MediaValidationError("Upload between one and four images or videos.")
    if width > MAX_CANVAS_WIDTH or height > MAX_CANVAS_HEIGHT:
        raise MediaValidationError("Canvas dimensions exceed the supported resolution.")

    for path in media_paths:
        if path.suffix.lower() not in ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS:
            raise MediaValidationError(f"{path.name} has an unsupported media type.")
    _validate_images(media_paths)

    overlay_path = _banner_path(width, height, output_dir, banner, logo_path)
    if all(path.suffix.lower() in ALLOWED_IMAGE_EXTS for path in media_paths):
        return _compose_still_images(
            media_paths, output_dir, width, height, overlay_path
        )
    return _compose_video(media_paths, output_dir, width, height, overlay_path)
