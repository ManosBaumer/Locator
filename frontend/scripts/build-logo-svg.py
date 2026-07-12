import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

SRC = Path(__file__).resolve().parents[2] / (
    "assets/c__Users_manos_AppData_Roaming_Cursor_User_workspaceStorage_db6ae8b70a8e0e430f3a108f5bcd73ec_images_"
    "ChatGPT_Image_Jul_12__2026__05_57_53_PM-ca564e2a-373d-428a-bca2-c2521d0474e3.png"
)
PUBLIC = Path(__file__).resolve().parents[1] / "public"
FALLBACK_SRC = PUBLIC / "logo.png"


def main() -> None:
    src = SRC if SRC.exists() else FALLBACK_SRC
    img = Image.open(src).convert("RGBA")
    width, height = img.size
    pixels = img.load()

    min_x, min_y, max_x, max_y = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            if sum(pixels[x, y][:3]) / 3 > 96:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    crop = img.crop((min_x, min_y, max_x + 1, max_y + 1))
    crop_w, crop_h = crop.size
    crop_pixels = crop.load()

    mask = Image.new("L", (crop_w, crop_h), 0)
    mask_pixels = mask.load()
    for y in range(crop_h):
        for x in range(crop_w):
            if sum(crop_pixels[x, y][:3]) / 3 > 96:
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
    print(f"wrote logo.svg ({crop_w}x{crop_h})")


if __name__ == "__main__":
    main()
