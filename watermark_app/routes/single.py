import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Blueprint, render_template, request
from werkzeug.utils import secure_filename

from watermark_app.config import ALLOWED_MEDIA_EXTS
from watermark_app.routes.common import temporary_download
from watermark_app.services.media import VideoToolUnavailableError, process_media
from watermark_app.services.watermark import WATERMARK_POSITIONS

single = Blueprint("single", __name__)


@single.get("/")
def index():
    return render_template("index.html")


@single.route("/watermark", methods=["POST"])
def watermark_endpoint():
    media = request.files.get("media")
    if not media or not media.filename:
        return "No media uploaded", 400

    media_ext = Path(media.filename).suffix.lower()
    if media_ext not in ALLOWED_MEDIA_EXTS:
        return render_template("index.html", error_message="Unsupported media file type."), 400

    position = request.form.get("position", "top-right")
    if position not in WATERMARK_POSITIONS:
        return render_template(
            "index.html", error_message="Choose one of the available watermark positions."
        ), 400

    temporary_directory = TemporaryDirectory(prefix="watermark-single-")
    directory = Path(temporary_directory.name)
    media_path = directory / f"input{media_ext}"
    logo_path = None

    try:
        media.save(media_path)
        logo = request.files.get("logo")
        if logo and logo.filename:
            logo_ext = Path(logo.filename).suffix.lower()
            if logo_ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                temporary_directory.cleanup()
                return render_template(
                    "index.html", error_message="Unsupported logo file type."
                ), 400
            logo_path = directory / f"logo{logo_ext}"
            logo.save(logo_path)

        text = request.form.get("text", "© Watermark").strip() or "© Watermark"
        opacity = min(255, max(40, int(request.form.get("opacity", 180))))
        output_path = process_media(
            media_path, text, logo_path, opacity, directory, position
        )
        download_name = secure_filename(f"watermarked_{media.filename}") or "watermarked-media"
        return temporary_download(temporary_directory, output_path, download_name)
    except VideoToolUnavailableError as exc:
        temporary_directory.cleanup()
        return render_template("index.html", error_message=str(exc)), 400
    except (ValueError, OSError) as exc:
        temporary_directory.cleanup()
        return render_template("index.html", error_message=str(exc)), 400
    except subprocess.SubprocessError:
        temporary_directory.cleanup()
        return render_template(
            "index.html",
            error_message="Could not process this video. Check that the file is valid.",
        ), 400
    except Exception:
        temporary_directory.cleanup()
        raise

