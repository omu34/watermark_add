from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from watermark_app.routes.common import temporary_download
from watermark_app.services.social_downloader import (
    SocialDownloadError,
    download_social_media,
    inspect_social_media,
)

social = Blueprint("social", __name__, url_prefix="/social")


@social.post("/inspect")
def inspect():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="Provide a JSON object with a media URL."), 400
    url = payload.get("url", "")
    if not isinstance(url, str) or not url.strip():
        return jsonify(error="Paste a social media URL first."), 400
    try:
        return jsonify(inspect_social_media(url))
    except SocialDownloadError as exc:
        return jsonify(error=str(exc)), exc.status_code


@social.post("/download")
def download():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="Provide a JSON object with a URL and media quality."), 400
    url = payload.get("url", "")
    format_id = payload.get("format_id", "")
    if not isinstance(url, str) or not isinstance(format_id, str):
        return jsonify(error="Provide a valid URL and media quality."), 400
    try:
        temporary_directory, media_path = download_social_media(url, format_id)
        name = secure_filename(f"social-media{media_path.suffix.lower()}") or "social-media"
        return temporary_download(
            temporary_directory,
            media_path,
            name,
            mimetype=None,
        )
    except SocialDownloadError as exc:
        return jsonify(error=str(exc)), exc.status_code
