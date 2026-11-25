import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image

from watermark_app.services.watermark import build_watermark_png

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_IMAGE_PIXELS = 12_000_000


class VideoToolUnavailableError(RuntimeError):
    pass


def require_video_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        raise VideoToolUnavailableError(
            "Video processing requires FFmpeg. Install FFmpeg, make sure ffmpeg and "
            "ffprobe are on your PATH, then restart the app."
        )


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Probes exact video width and height via ffprobe."""
    require_video_tool("ffprobe")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(video_path),
    ]
    out = subprocess.check_output(cmd).decode().strip()
    w, h = map(int, out.split("x"))
    return w, h


def process_media(
    media_path: Path,
    text: str,
    logo_path: Path | None,
    opacity: int,
    output_dir: Path,
    position: str = "top-right",
) -> Path:
    ext = media_path.suffix.lower()
    out_path = output_dir / f"out_{uuid.uuid4().hex}{ext}"

    if ext in IMAGE_EXTS:
        with Image.open(media_path) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds the supported 12-megapixel resolution.")
            base = source.convert("RGBA")
        wm_path = build_watermark_png(
            base.width, base.height, text, logo_path, opacity, output_dir, position
        )
        wm = Image.open(wm_path)
        merged = Image.alpha_composite(base, wm)
        if ext in {".jpg", ".jpeg"}:
            merged = merged.convert("RGB")
        merged.save(out_path, quality=95)
        wm_path.unlink(missing_ok=True)
        return out_path

    if ext in VIDEO_EXTS:
        w, h = get_video_dimensions(media_path)
        require_video_tool("ffmpeg")
        wm_path = build_watermark_png(w, h, text, logo_path, opacity, output_dir, position)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(media_path),
            "-i",
            str(wm_path),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0",
            "-c:a",
            "copy",
            "-preset",
            "fast",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wm_path.unlink(missing_ok=True)
        return out_path

    raise ValueError("Unsupported file format.")
