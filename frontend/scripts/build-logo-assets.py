from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parents[1] / "public"
APP = Path(__file__).resolve().parents[1] / "app"
SRC = ROOT / (
    "assets/c__Users_manos_AppData_Roaming_Cursor_User_workspaceStorage_db6ae8b70a8e0e430f3a108f5bcd73ec_images_"
    "ChatGPT_Image_Jul_12__2026__05_57_53_PM-ca564e2a-373d-428a-bca2-c2521d0474e3.png"
)
FAVICON_SRC = ROOT / "assets/favicon-mark.png"
FALLBACK_SRC = PUBLIC / "logo.png"
PANEL_MARK_COLOR = (15, 23, 42, 255)
FAVICON_MARK_COLOR = (255, 255, 255, 255)
FAVICON_SIZE = 512


def is_mark_pixel(r: int, g: int, b: int, a: int) -> bool:
    return a >= 32


def load_crop(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    width, height = img.size
    pixels = img.load()

    min_x, min_y, max_x, max_y = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if is_mark_pixel(r, g, b, a):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    return img.crop((min_x, min_y, max_x + 1, max_y + 1))


def write_logo_dark(crop: Image.Image) -> None:
    crop_w, crop_h = crop.size
    crop_pixels = crop.load()
    panel = Image.new("RGBA", (crop_w, crop_h), (0, 0, 0, 0))
    panel_pixels = panel.load()

    for y in range(crop_h):
        for x in range(crop_w):
            r, g, b, a = crop_pixels[x, y]
            if is_mark_pixel(r, g, b, a):
                panel_pixels[x, y] = PANEL_MARK_COLOR

    panel.save(PUBLIC / "logo-dark.png")


def write_favicon(crop: Image.Image) -> None:
    crop_w, crop_h = crop.size
    scale = min(FAVICON_SIZE / crop_w, FAVICON_SIZE / crop_h)
    target_w = max(1, round(crop_w * scale))
    target_h = max(1, round(crop_h * scale))

    resized = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
    resized_pixels = resized.load()

    canvas = Image.new("RGBA", (FAVICON_SIZE, FAVICON_SIZE), (0, 0, 0, 0))
    offset_x = (FAVICON_SIZE - target_w) // 2
    offset_y = (FAVICON_SIZE - target_h) // 2

    for y in range(target_h):
        for x in range(target_w):
            r, g, b, a = resized_pixels[x, y]
            if is_mark_pixel(r, g, b, a):
                canvas.putpixel((x + offset_x, y + offset_y), FAVICON_MARK_COLOR)

    canvas.save(PUBLIC / "favicon.png")
    canvas.save(APP / "icon.png")


def write_logo_svg(crop: Image.Image) -> None:
    crop_w, crop_h = crop.size
    crop_pixels = crop.load()

    mask = Image.new("L", (crop_w, crop_h), 0)
    mask_pixels = mask.load()
    for y in range(crop_h):
        for x in range(crop_w):
            r, g, b, a = crop_pixels[x, y]
            if is_mark_pixel(r, g, b, a):
                mask_pixels[x, y] = 255

    buffer = BytesIO()
    mask.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {crop_w} {crop_h}" role="img" aria-label="Mitu">
  <defs>
    <mask id="mitu-mark" maskUnits="userSpaceOnUse" x="0" y="0" width="{crop_w}" height="{crop_h}">
      <image href="data:image/png;base64,{encoded}" width="{crop_w}" height="{crop_h}" />
    </mask>
  </defs>
  <rect width="{crop_w}" height="{crop_h}" fill="currentColor" mask="url(#mitu-mark)" />
</svg>
"""
    (PUBLIC / "logo.svg").write_text(svg, encoding="utf-8")


def main() -> None:
    src = SRC if SRC.exists() else FALLBACK_SRC
    crop = load_crop(src)
    write_logo_dark(crop)
    write_logo_svg(crop)
    print(f"logo assets updated from {src.name} ({crop.size[0]}x{crop.size[1]})")

    favicon_src = FAVICON_SRC if FAVICON_SRC.exists() else src
    favicon_crop = load_crop(favicon_src)
    write_favicon(favicon_crop)
    print(f"favicon updated from {favicon_src.name} ({favicon_crop.size[0]}x{favicon_crop.size[1]})")


if __name__ == "__main__":
    main()
