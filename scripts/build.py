#!/usr/bin/env python3
"""Rebuild GRUB-native assets; the installer uses the already bundled files."""
import argparse
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parents[1]
THEME = BASE / "theme"
PROFILES = {"1080p": (24, 19, 25, 38, 7), "1440p": (32, 25, 33, 50, 10),
            "compact": (17, 13, 18, 27, 5)}


def build(font_path):
    THEME.mkdir(exist_ok=True)
    with Image.open(BASE / "assets/background.png") as image:
        # GRUB's PNG decoder needs ordinary RGB/RGBA, not indexed or 16-bit PNGs.
        image.convert("RGB").save(THEME / "background.png", optimize=True)
    shutil.copyfile(BASE / "assets/FONT-LICENSE.txt", THEME / "FONT-LICENSE.txt")
    for size in sorted({16} | {n for p in PROFILES.values() for n in p[:3]}):
        subprocess.run(["grub-mkfont", "-s", str(size), "-o", str(THEME / f"serif-{size}.pf2"),
                        "-r", "0x20-0x24f,0x370-0x52f,0x2000-0x206f,0x2190-0x21ff,0x2500-0x25ff", str(font_path)], check=True)
    for name, (menu, small, heading, height, spacing) in PROFILES.items():
        content = f'''# Re:Zero Lavender — {name}. Percentages keep the reference composition.
title-text: ""
desktop-image: "background.png"
desktop-image-scale-method: "stretch"
desktop-color: "#f3f3f6"
message-font: "DejaVu Serif Regular {small}"
message-color: "#514177"
message-bg-color: "#f3f3f6"
terminal-font: "DejaVu Serif Regular 16"

+ label {{
    left = 25%
    top = 24%
    width = 25%
    height = {heading + 12}
    text = "—  GNU GRUB  —"
    font = "DejaVu Serif Regular {heading}"
    color = "#78679c"
    align = "center"
}}

+ boot_menu {{
    left = 20%+10
    top = 31%
    width = 44%
    height = 32%
    item_font = "DejaVu Serif Regular {menu}"
    selected_item_font = "DejaVu Serif Regular {menu}"
    item_color = "#655382"
    selected_item_color = "#ffffff"
    item_height = {height}
    item_spacing = {spacing}
    item_padding = 0
    icon_width = 0
    icon_height = 0
    item_icon_space = 0
    item_pixmap_style = "idle_*.png"
    selected_item_pixmap_style = "select_*.png"
    scrollbar = true
    scrollbar_width = 4
    scrollbar_frame = "scroll_*.png"
    scrollbar_thumb = "thumb_*.png"
}}

+ label {{
    left = 20%+10
    top = 73%
    width = 44%
    height = {small + 10}
    text = "Use ↑ and ↓ keys to select an entry."
    font = "DejaVu Serif Regular {small}"
    color = "#78679c"
    align = "center"
}}

+ label {{
    left = 20%+10
    top = 76%
    width = 44%
    height = {small + 10}
    text = "Enter to boot · e to edit · c for command line"
    font = "DejaVu Serif Regular {small}"
    color = "#78679c"
    align = "center"
}}

+ label {{
    id = "__timeout__"
    left = 20%+10
    top = 80%
    width = 44%
    height = {small + 10}
    text = "Booting in %d seconds"
    font = "DejaVu Serif Regular {small}"
    color = "#78679c"
    align = "center"
}}
'''
        (THEME / f"theme-{name}.txt").write_text(content)
    shutil.copyfile(THEME / "theme-1080p.txt", THEME / "theme.txt")
    # Matching side widths keep selected and unselected titles aligned. The
    # triangle belongs to the selected box, so it follows keyboard selection.
    for prefix in ("select", "idle"):
        center = Image.new("RGBA", (1, 40), "#7357b2" if prefix == "select" else (0, 0, 0, 0))
        left = Image.new("RGBA", (46, 40), "#7357b2" if prefix == "select" else (0, 0, 0, 0))
        right = Image.new("RGBA", (26, 40), (0, 0, 0, 0))
        if prefix == "select":
            ImageDraw.Draw(left).polygon([(15, 13), (15, 27), (26, 20)], fill="white")
            ImageDraw.Draw(right).polygon([(0, 0), (0, 39), (25, 39)], fill="#7357b2")
        for side, image in (("c", center), ("w", left), ("e", right)):
            image.save(THEME / f"{prefix}_{side}.png")
    for prefix, color in (("scroll", "#e3deed"), ("thumb", "#a08ac4")):
        Image.new("RGB", (4, 4), color).save(THEME / f"{prefix}_c.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/TTF/DejaVuSerif.ttf"))
    build(parser.parse_args().font)
