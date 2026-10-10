"""Text: draws smooth DM Sans text onto OpenCV frames using Pillow.

Each (text, size, weight) is rendered once and cached, so drawing text every frame stays fast.
"""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "assets/fonts/DMSans.ttf"


@lru_cache(maxsize=None)
def get_font(size, weight):
    """Load DM Sans at a pixel size and weight (400 regular, 600 semibold); fall back to Pillow's font if missing."""
    try:
        font = ImageFont.truetype(FONT_PATH, size)
        font.set_variation_by_axes([min(max(size, 9), 40), weight])  # axes: optical size, weight
        return font
    except OSError:
        return ImageFont.load_default(size)


@lru_cache(maxsize=256)
def text_mask(text, size, weight):
    """Render text once as a grayscale coverage mask (0 to 1), trimmed to its ink."""
    font = get_font(size, weight)
    left, top, right, bottom = font.getbbox(text)
    image = Image.new("L", (right - left + 2, bottom - top + 2), 0)
    ImageDraw.Draw(image).text((1 - left, 1 - top), text, font=font, fill=255)
    return np.asarray(image, dtype=np.float32) / 255


def text_size(text, size, weight=400):
    """Width and height in pixels that the text will take up."""
    mask = text_mask(text, size, weight)
    return mask.shape[1], mask.shape[0]


def draw_text(frame, text, pos, size=24, color=(255, 255, 255), weight=400, opacity=1.0, align="left"):
    """Blend text onto the frame at pos (top of text). align is left, center or right of pos."""
    if opacity <= 0 or not text:
        return
    mask = text_mask(text, size, weight)
    h, w = mask.shape
    x, y = int(pos[0]), int(pos[1])
    if align == "center":
        x -= w // 2
    elif align == "right":
        x -= w
    # Clip to the frame so text near an edge never crashes.
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, frame.shape[1]), min(y + h, frame.shape[0])
    if x0 >= x1 or y0 >= y1:
        return
    alpha = mask[y0 - y:y1 - y, x0 - x:x1 - x, None] * opacity
    roi = frame[y0:y1, x0:x1]
    roi[:] = (roi * (1 - alpha) + np.array(color, np.float32) * alpha).astype(np.uint8)
