import math
import draughts
from wand.image import Image
from wand.color import Color


def board_to_svg(board: draughts.Board) -> str:
    board_str = board if isinstance(board, str) else str(board)
    lines = [ln for ln in board_str.splitlines() if '|' in ln]
    square_size = 512 // len(lines)
    margin = 0

    # Parse rows and normalize widths
    rows = [[cell.strip() for cell in ln.split('|')] for ln in lines]
    max_width = max(len(r) for r in rows)
    for r in rows:
        if len(r) < max_width:
            r.extend([''] * (max_width - len(r)))

    width = max_width
    height = len(rows)

    svg_width = width * square_size + 2 * margin
    svg_height = height * square_size + 2 * margin

    # Pre-calc where playable (dark) squares are: we'll treat (r+c)%2 == 1 as playable
    is_playable = lambda r, c: (r + c) % 2 == 1

    # Start svg (no outer background rect; transparent by default)
    svg_parts = [
        f'<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">'
    ]

    # Single crown gradient (reused for all kings)
    svg_parts.append('<defs>')
    svg_parts.append(
        '<linearGradient id="crown_gradient" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#FFD700" />'
        '<stop offset="50%" stop-color="#FFA500" />'
        '<stop offset="100%" stop-color="#FFD700" />'
        '</linearGradient>'
    )
    svg_parts.append('</defs>')

    # Draw board squares
    svg_parts.append('<g id="squares">')
    light_sq = "#E8D0AA"
    dark_sq = "#B87C4C"  # same palette as before (playable squares)
    for r in range(height):
        for c in range(width):
            x = margin + c * square_size
            y = margin + r * square_size
            color = light_sq if not is_playable(r, c) else dark_sq
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="{color}" />'
            )
    svg_parts.append('</g>')

    # Draw pieces (black + red). red replaces 'white' pieces as requested.
    svg_parts.append('<g id="pieces">')
    black_fill = "#111111"   # softened black for visibility
    red_fill = "#DD2E44"     # user-specified red for "white" pieces
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            token = cell.strip()
            if not token:
                continue
            rotated_r = height - 1 - r
            rotated_c = width - 1 - c
            cx = margin + rotated_c * square_size + square_size / 2
            cy = margin + rotated_r * square_size + square_size / 2
            radius = square_size * 0.4
            if token.lower() == 'b':
                fill = black_fill
                stroke = red_fill
            else:
                # treat anything else (w/W) as the red piece
                fill = red_fill
                stroke = black_fill
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="4" />'
            )
            # kings (upper-case): draw crown/star on top of the piece (but under the numbers)
            if token.isupper():
                inner_r = radius * 0.9
                svg_parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2" />'
                )
    svg_parts.append('</g>')
    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def svg_to_png(svg: str, overlay_path: str) -> bytes:
    with Image(blob=svg.encode('utf-8'), background=Color("transparent")) as base:
        base.format = "png"
        with Image(filename=overlay_path) as overlay:
            base.composite(overlay, left=0, top=0)
        return base.make_blob() or b''
    

def board_to_png(board: draughts.Board, overlay_path: str) -> bytes:
    return svg_to_png(board_to_svg(board), overlay_path)
