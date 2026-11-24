import uuid
from pathlib import Path

from flask import Blueprint, render_template, request, send_file

from watermark_app.config import WORK_DIR
from watermark_app.services.media import VideoToolUnavailableError, process_media
from watermark_app.services.watermark import WATERMARK_POSITIONS

main = Blueprint("main", __name__)


@main.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@main.route("/watermark", methods=["POST"])
def watermark_endpoint():
    media = request.files.get("media")
    if not media or not media.filename:
        return "No media uploaded", 400

    position = request.form.get("position", "top-right")
    if position not in WATERMARK_POSITIONS:
        return render_template(
            "index.html", error_message="Choose one of the available watermark positions."
        ), 400

    uid = uuid.uuid4().hex
    media_ext = Path(media.filename).suffix.lower()
    media_path = WORK_DIR / f"in_{uid}{media_ext}"
    media.save(media_path)

    logo_path = None
    logo = request.files.get("logo")
    if logo and logo.filename:
        logo_path = WORK_DIR / f"logo_{uid}{Path(logo.filename).suffix.lower()}"
        logo.save(logo_path)

    text = request.form.get("text", "© Watermark").strip() or "© Watermark"
    opacity = int(request.form.get("opacity", 180))
    try:
        output_path = process_media(media_path, text, logo_path, opacity, position)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"watermarked_{media.filename}",
        )
    except VideoToolUnavailableError as exc:
        return render_template("index.html", error_message=str(exc)), 400
    finally:
        media_path.unlink(missing_ok=True)
        if logo_path:
            logo_path.unlink(missing_ok=True)
