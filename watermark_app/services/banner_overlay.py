import uuid
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from watermark_app.config import MAX_CANVAS_HEIGHT, MAX_CANVAS_WIDTH

_FONT_PATHS = (
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_BOLD_FONT_PATHS = (
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in _BOLD_FONT_PATHS if bold else _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fitting_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    available_width: int,
    max_size: int,
    bold: bool,
) -> tuple[ImageFont.ImageFont, str]:
    text = text.strip()
    if not text:
        return _font(max_size, bold), ""

    for size in range(max_size, 9, -1):
        font = _font(size, bold)
        if draw.textlength(text, font=font) <= available_width:
            return font, text

    font = _font(10, bold)
    ellipsis = "..."
    trimmed = text
    while trimmed and draw.textlength(trimmed + ellipsis, font=font) > available_width:
        trimmed = trimmed[:-1]
    return font, (trimmed + ellipsis) if trimmed else ""


def build_banner_overlay(
    width: int,
    height: int,
    output_dir: Path,
    title: str,
    description: str,
    top_color: str,
    top_opacity: int,
    bottom_color: str,
    bottom_opacity: int,
    logo_path: Path | None = None,
) -> Path:
    if width > MAX_CANVAS_WIDTH or height > MAX_CANVAS_HEIGHT:
        raise ValueError("Banner canvas exceeds the supported resolution.")

    banner_height = max(8, height // 8)
    band_height = banner_height // 2
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top_rgb = ImageColor.getrgb(top_color)
    bottom_rgb = ImageColor.getrgb(bottom_color)
    draw.rectangle(
        (0, height - banner_height, width, height - band_height - 1),
        fill=(*top_rgb, top_opacity),
    )
    draw.rectangle(
        (0, height - band_height, width, height - 1),
        fill=(*bottom_rgb, bottom_opacity),
    )

    padding = max(8, width // 100)
    text_x = banner_height + padding
    available_width = max(1, width - text_x - padding)
    title_font, title = _fitting_font(
        draw, title, available_width, max(14, band_height * 2 // 3), True
    )
    description_font, description = _fitting_font(
        draw, description, available_width, max(12, band_height // 2), False
    )
    title_box = draw.textbbox((0, 0), title, font=title_font)
    description_box = draw.textbbox((0, 0), description, font=description_font)
    title_y = height - banner_height + (
        band_height - (title_box[3] - title_box[1])
    ) // 2 - title_box[1]
    description_y = height - band_height + (
        band_height - (description_box[3] - description_box[1])
    ) // 2 - description_box[1]
    draw.text((text_x, title_y), title, font=title_font, fill=(255, 255, 255, 255))
    draw.text(
        (text_x, description_y),
        description,
        font=description_font,
        fill=(255, 255, 255, 255),
    )

    if logo_path:
        with Image.open(logo_path) as source:
            if source.width * source.height > 12_000_000:
                raise ValueError("Brand logo exceeds the supported image resolution.")
            logo = source.convert("RGBA")
        inset = max(4, padding // 2)
        logo.thumbnail(
            (max(1, banner_height - inset * 2), max(1, banner_height - inset * 2)),
            Image.Resampling.LANCZOS,
        )
        logo_x = (banner_height - logo.width) // 2
        logo_y = height - banner_height + (banner_height - logo.height) // 2
        overlay.alpha_composite(logo, (logo_x, logo_y))

    overlay_path = output_dir / f"banner_{uuid.uuid4().hex}.png"
    overlay.save(overlay_path, "PNG")
    return overlay_path
