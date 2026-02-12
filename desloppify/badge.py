"""Scorecard badge image generator — produces a visual health summary PNG."""

from __future__ import annotations

import os
from pathlib import Path

from .utils import PROJECT_ROOT


def _score_color(score: float) -> tuple[int, int, int]:
    """Color-code a score: green >= 90, yellow 70-90, red < 70."""
    if score >= 90:
        return (74, 222, 128)   # green-400
    if score >= 70:
        return (250, 204, 21)   # yellow-400
    return (248, 113, 113)      # red-400


def _load_font(size: int, bold: bool = False, mono: bool = False):
    """Load a good font with cross-platform fallback."""
    from PIL import ImageFont

    candidates = []
    if mono:
        candidates = [
            "/System/Library/Fonts/SFNSMono.ttf",        # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
    elif bold:
        candidates = [
            "/System/Library/Fonts/SFCompact.ttf",       # macOS
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/SFCompact.ttf",       # macOS
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_scorecard(state: dict, output_path: str | Path) -> Path:
    """Render a scorecard PNG from scan state. Returns the output path."""
    from PIL import Image, ImageDraw

    output_path = Path(output_path)
    dim_scores = state.get("dimension_scores", {})
    obj_score = state.get("objective_score")
    obj_strict = state.get("objective_strict")

    # Fall back to weighted progress score if no objective health
    main_score = obj_score if obj_score is not None else state.get("score", 0)
    strict_score = obj_strict if obj_strict is not None else state.get("strict_score", 0)

    # Fonts
    font_title = _load_font(22, bold=True)
    font_big = _load_font(64, bold=True)
    font_strict = _load_font(22)
    font_header = _load_font(13, bold=True, mono=True)
    font_row = _load_font(14, mono=True)
    font_tiny = _load_font(11)

    # Colors
    BG = (17, 17, 27)          # near-black with blue tint
    BG2 = (24, 24, 38)         # slightly lighter for table area
    TEXT = (229, 229, 241)      # off-white
    DIM = (113, 113, 142)      # muted
    ACCENT = (99, 102, 241)    # indigo-500
    ACCENT_DIM = (55, 56, 90)  # muted indigo

    # Layout calculations
    active_dims = [(name, data) for name, data in dim_scores.items()
                   if data.get("checks", 0) > 0]
    row_count = len(active_dims)
    W = 500
    table_top = 165
    row_h = 28
    table_h = 30 + row_count * row_h + 16  # header + rows + padding
    H = table_top + table_h + 40

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # --- Background flair ---
    # Smooth radial glow in top-right corner
    glow_cx, glow_cy = W - 50, 25
    glow_max_r = 180
    for i in range(100):
        r = glow_max_r - i * 1.8
        if r <= 0:
            break
        t = i / 100  # 0..1
        intensity = int(10 * (1 - t) ** 2)
        bbox = (glow_cx - r, glow_cy - r, glow_cx + r, glow_cy + r)
        draw.ellipse(bbox, fill=(
            BG[0] + intensity,
            BG[1] + intensity,
            BG[2] + intensity * 3,  # blue-tinted glow
        ))

    # Accent line at top
    draw.rectangle((0, 0, W, 3), fill=ACCENT)

    # --- Title ---
    title = "Desloppify Score"
    tw = draw.textlength(title, font=font_title)
    draw.text(((W - tw) / 2, 24), title, fill=TEXT, font=font_title)

    # --- Main score ---
    score_str = f"{main_score:.1f}"
    score_color = _score_color(main_score)
    sw = draw.textlength(score_str, font=font_big)

    # Strict label next to main score
    strict_str = f"strict: {strict_score:.1f}"
    strict_w = draw.textlength(strict_str, font=font_strict)

    # Center the pair
    total_w = sw + 16 + strict_w
    x_start = (W - total_w) / 2
    score_y = 62
    draw.text((x_start, score_y), score_str, fill=score_color, font=font_big)
    # Vertically center strict with the score
    strict_y = score_y + 30
    draw.text((x_start + sw + 16, strict_y), strict_str, fill=DIM, font=font_strict)

    # --- Separator ---
    sep_y = table_top - 14
    draw.rectangle((32, sep_y, W - 32, sep_y + 1), fill=ACCENT_DIM)

    # --- Table background ---
    draw.rounded_rectangle((28, table_top - 6, W - 28, table_top + table_h), radius=8, fill=BG2)

    # --- Table header ---
    col_name = 46
    col_health = 320
    col_strict = 416
    header_y = table_top + 6
    draw.text((col_name, header_y), "Dimension", fill=DIM, font=font_header)
    draw.text((col_health, header_y), "Health", fill=DIM, font=font_header)
    draw.text((col_strict, header_y), "Strict", fill=DIM, font=font_header)

    # Header underline
    line_y = header_y + 20
    draw.rectangle((col_name, line_y, W - 46, line_y), fill=ACCENT_DIM)

    # --- Dimension rows ---
    y = line_y + 8
    for name, data in active_dims:
        score = data.get("score", 100)
        strict = data.get("strict", score)
        sc = _score_color(score)
        stc = _score_color(strict)
        draw.text((col_name, y), name, fill=TEXT, font=font_row)
        draw.text((col_health, y), f"{score:.1f}%", fill=sc, font=font_row)
        draw.text((col_strict, y), f"{strict:.1f}%", fill=stc, font=font_row)
        y += row_h

    # --- Footer ---
    footer_y = H - 24
    footer = "github.com/peteromallet/desloppify"
    fw = draw.textlength(footer, font=font_tiny)
    draw.text(((W - fw) / 2, footer_y), footer, fill=ACCENT_DIM, font=font_tiny)

    img.save(str(output_path), "PNG", optimize=True)
    return output_path


def get_badge_config(args) -> tuple[Path | None, bool]:
    """Resolve badge output path and whether badge generation is disabled.

    Returns (output_path, disabled). Checks CLI args, then env vars.
    """
    disabled = getattr(args, "no_badge", False) or os.environ.get("DESLOPPIFY_NO_BADGE", "").lower() in ("1", "true", "yes")
    if disabled:
        return None, True
    path_str = getattr(args, "badge_path", None) or os.environ.get("DESLOPPIFY_BADGE_PATH", "scorecard.png")
    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path, False
