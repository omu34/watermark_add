import re
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from watermark_app.config import ALLOWED_IMAGE_EXTS, ALLOWED_VIDEO_EXTS
from watermark_app.routes.common import temporary_download
from watermark_app.services.collage_engine import (
    MediaValidationError,
    compose_collage,
)
from watermark_app.services.media import VideoToolUnavailableError

collage = Blueprint("collage", __name__)
_CANVAS_PRESETS = {
    "landscape": (1280, 720),
    "square": (1080, 1080),
}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_IMAGE_EXTS = ALLOWED_IMAGE_EXTS
_VIDEO_EXTS = ALLOWED_VIDEO_EXTS


def _banner_options() -> dict:
    top_color = request.form.get("top_color", "#312e81")
    bottom_color = request.form.get("bottom_color", "#0f172a")
    if not _HEX_COLOR.fullmatch(top_color) or not _HEX_COLOR.fullmatch(bottom_color):
        raise MediaValidationError("Select valid colors for both banner bands.")
    return {
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "top_color": top_color,
        "top_opacity": request.form.get("top_opacity", 210),
        "bottom_color": bottom_color,
        "bottom_opacity": request.form.get("bottom_opacity", 220),
    }


@collage.post("/collage")
def create_collage():
    uploaded_files = [item for item in request.files.getlist("media") if item.filename]
    if not 1 <= len(uploaded_files) <= 4:
        return jsonify(error="Upload between one and four images or videos."), 400

    preset = request.form.get("canvas", "landscape")
    if preset not in _CANVAS_PRESETS:
        return jsonify(error="Choose a supported canvas preset."), 400
    width, height = _CANVAS_PRESETS[preset]

    file_extensions = [Path(item.filename).suffix.lower() for item in uploaded_files]
    if any(ext not in _IMAGE_EXTS | _VIDEO_EXTS for ext in file_extensions):
        return jsonify(error="Use JPG, PNG, WebP, MP4, MOV, or WebM files."), 400

    logo_upload = request.files.get("brand_logo")
    logo_ext = Path(logo_upload.filename).suffix.lower() if logo_upload and logo_upload.filename else ""
    if logo_ext and logo_ext not in _IMAGE_EXTS:
        return jsonify(error="The banner logo must be a JPG, PNG, or WebP image."), 400

    temporary_directory = TemporaryDirectory(prefix="watermark-collage-")
    output_dir = Path(temporary_directory.name)
    media_paths = []
    try:
        for index, (uploaded, extension) in enumerate(zip(uploaded_files, file_extensions)):
            safe_name = secure_filename(uploaded.filename) or f"media-{index}{extension}"
            media_path = output_dir / f"media-{index}{Path(safe_name).suffix.lower()}"
            uploaded.save(media_path)
            media_paths.append(media_path)

        logo_path = None
        if logo_ext:
            logo_path = output_dir / f"brand-logo{logo_ext}"
            logo_upload.save(logo_path)

        output_path = compose_collage(
            media_paths=media_paths,
            output_dir=output_dir,
            width=width,
            height=height,
            banner=_banner_options(),
            logo_path=logo_path,
        )
        output_mimetype = "video/mp4" if output_path.suffix.lower() == ".mp4" else "image/jpeg"
        return temporary_download(
            temporary_directory,
            output_path,
            f"watermark-collage{output_path.suffix.lower()}",
            output_mimetype,
        )
    except (MediaValidationError, VideoToolUnavailableError, ValueError, OSError) as exc:
        temporary_directory.cleanup()
        return jsonify(error=str(exc)), 400
    except Exception:
        temporary_directory.cleanup()
        raise
