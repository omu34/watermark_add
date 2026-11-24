import os
import subprocess
import uuid
from pathlib import Path
from flask import Flask, request, send_file, render_template_string
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
WORK_DIR = Path("watermark_workspace")
WORK_DIR.mkdir(exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def build_watermark_png(w: int, h: int, text: str, logo_path: Path | None, opacity: int) -> Path:
    """Generates a transparent full-frame RGBA overlay PNG with text or logo at top-right."""
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pad = max(16, w // 50)

    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        target_w = max(64, w // 7)
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.Resampling.LANCZOS)

        # Apply global alpha opacity to logo
        alpha = logo.getchannel("A").point(lambda p: int(p * (opacity / 255)))
        logo.putalpha(alpha)

        x = w - logo.width - pad
        y = pad
        overlay.paste(logo, (x, y), logo)
    else:
        draw = ImageDraw.Draw(overlay)
        font_size = max(20, w // 26)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = w - text_w - pad
        y = pad

        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, opacity))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))

    wm_path = WORK_DIR / f"wm_{uuid.uuid4().hex}.png"
    overlay.save(wm_path, "PNG")
    return wm_path


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Probes exact video width and height via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(video_path)
    ]
    out = subprocess.check_output(cmd).decode().strip()
    w, h = map(int, out.split("x"))
    return w, h


def process_media(media_path: Path, text: str, logo_path: Path | None, opacity: int) -> Path:
    ext = media_path.suffix.lower()
    out_path = WORK_DIR / f"out_{uuid.uuid4().hex}{ext}"

    if ext in IMAGE_EXTS:
        base = Image.open(media_path).convert("RGBA")
        wm_path = build_watermark_png(base.width, base.height, text, logo_path, opacity)
        wm = Image.open(wm_path)
        merged = Image.alpha_composite(base, wm)
        if ext in {".jpg", ".jpeg"}:
            merged = merged.convert("RGB")
        merged.save(out_path, quality=95)
        wm_path.unlink(missing_ok=True)
        return out_path

    if ext in VIDEO_EXTS:
        w, h = get_video_dimensions(media_path)
        wm_path = build_watermark_png(w, h, text, logo_path, opacity)
        cmd = [
            "ffmpeg", "-y", "-i", str(media_path), "-i", str(wm_path),
            "-filter_complex", "[0:v][1:v]overlay=0:0",
            "-c:a", "copy", "-preset", "fast", str(out_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wm_path.unlink(missing_ok=True)
        return out_path

    raise ValueError("Unsupported file format.")


HTML_UI = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Pro Media Watermarker</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-6">
  <form action="/watermark" method="post" enctype="multipart/form-data"
        class="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-5 shadow-2xl">
    <h1 class="text-2xl font-bold tracking-tight">Media Watermark Studio</h1>
    <p class="text-sm text-slate-400">Upload any image or video. Stamps your text or logo at the top-right.</p>

    <div>
      <label class="block text-xs font-semibold uppercase text-slate-400 mb-1">1. Image or Video File *</label>
      <input type="file" name="media" accept="image/*,video/*" required
             class="w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:text-white hover:file:bg-indigo-500">
    </div>

    <div>
      <label class="block text-xs font-semibold uppercase text-slate-400 mb-1">2A. Custom Watermark Text</label>
      <input type="text" name="text" value="© Brand Name"
             class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500">
    </div>

    <div>
      <label class="block text-xs font-semibold uppercase text-slate-400 mb-1">2B. Or Upload Logo PNG (Overrides Text)</label>
      <input type="file" name="logo" accept="image/*"
             class="w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-slate-700 file:text-white hover:file:bg-slate-600">
    </div>

    <div>
      <label class="block text-xs font-semibold uppercase text-slate-400 mb-1">Opacity (40 – 255)</label>
      <input type="range" name="opacity" min="40" max="255" value="180" class="w-full accent-indigo-500">
    </div>

    <button type="submit"
            class="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-semibold text-sm transition">
      Apply Top-Right Watermark & Download
    </button>
  </form>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_UI)


@app.route("/watermark", methods=["POST"])
def watermark_endpoint():
    media = request.files.get("media")
    if not media or not media.filename:
        return "No media uploaded", 400

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
        output_path = process_media(media_path, text, logo_path, opacity)
        return send_file(output_path, as_attachment=True, download_name=f"watermarked_{media.filename}")
    finally:
        media_path.unlink(missing_ok=True)
        if logo_path:
            logo_path.unlink(missing_ok=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)