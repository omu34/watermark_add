import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WATERMARK_POSITIONS = ("top-left", "top-right", "center", "bottom-left", "bottom-right")


def _position_coordinates(
    frame_width: int,
    frame_height: int,
    content_width: int,
    content_height: int,
    position: str,
) -> tuple[int, int]:
    pad = max(16, frame_width // 50)
    if position not in WATERMARK_POSITIONS:
        raise ValueError("Unsupported watermark position.")

    positions = {
        "top-left": (pad, pad),
        "top-right": (frame_width - content_width - pad, pad),
        "center": ((frame_width - content_width) // 2, (frame_height - content_height) // 2),
        "bottom-left": (pad, frame_height - content_height - pad),
        "bottom-right": (
            frame_width - content_width - pad,
            frame_height - content_height - pad,
        ),
    }
    return positions[position]


def build_watermark_png(
    w: int,
    h: int,
    text: str,
    logo_path: Path | None,
    opacity: int,
    output_dir: Path,
    position: str = "top-right",
) -> Path:
    """Generates a transparent full-frame RGBA watermark overlay."""
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    if logo_path and logo_path.exists():
        with Image.open(logo_path) as source:
            if source.width * source.height > 12_000_000:
                raise ValueError("Logo exceeds the supported 12-megapixel resolution.")
            logo = source.convert("RGBA")
        target_w = max(64, w // 7)
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.Resampling.LANCZOS)

        alpha = logo.getchannel("A").point(lambda p: int(p * (opacity / 255)))
        logo.putalpha(alpha)

        x, y = _position_coordinates(w, h, logo.width, logo.height, position)
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
        text_h = bbox[3] - bbox[1]
        x, y = _position_coordinates(w, h, text_w, text_h, position)
        draw_x = x - bbox[0]
        draw_y = y - bbox[1]

        draw.text((draw_x + 2, draw_y + 2), text, font=font, fill=(0, 0, 0, opacity))
        draw.text((draw_x, draw_y), text, font=font, fill=(255, 255, 255, opacity))

    wm_path = output_dir / f"wm_{uuid.uuid4().hex}.png"
    overlay.save(wm_path, "PNG")
    return wm_path
