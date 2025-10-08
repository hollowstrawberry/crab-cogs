import logging
import math
import draughts
from wand.image import Image
from wand.color import Color

log = logging.getLogger("red.crab-cogs.simplecheckers")


def create_svg(board: draughts.Board) -> str:
    """
    Create an SVG of a draughts/checkers board.
    `board` may be either a string (the string-repr you pasted) or an object whose str() produces that layout.
    """
    # Config
    square_size = 40
    margin = 16

    # Get string representation
    if not isinstance(board, str):
        board_str = str(board)
    else:
        board_str = board

    # Keep only lines that contain '|' (drops separators like "-----")
    lines = [ln for ln in board_str.splitlines() if '|' in ln]

    # Split on '|' and strip cells; normalize each row to the same width
    rows = [[cell.strip() for cell in ln.split('|')] for ln in lines]
    max_width = max(len(r) for r in rows)
    for r in rows:
        if len(r) < max_width:
            r.extend([''] * (max_width - len(r)))

    width = max_width
    height = len(rows)

    svg_width = width * square_size + 2 * margin
    svg_height = height * square_size + 2 * margin

    # Start svg; use a light background so pieces show up (change to transparent if you want)
    svg_parts = [
        f'<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">',
        # outer background (change fill to "none" if you want transparent)
        f'<rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#f6f3ee" />',
        # defs for gradients (added here once)
        '<defs>'
    ]

    # Pre-create crown gradients for possible king markers (one per cell)
    for r in range(height):
        for c in range(width):
            gid = f'crown_gradient_{r}_{c}'
            svg_parts.append(
                f'<linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="100%">'
                f'<stop offset="0%" stop-color="#FFD700" />'
                f'<stop offset="50%" stop-color="#FFA500" />'
                f'<stop offset="100%" stop-color="#FFD700" />'
                f'</linearGradient>'
            )
    svg_parts.append('</defs>')

    # Coordinates (letters along bottom, numbers along left). Put them outside the board area.
    # Letters
    for i in range(width):
        x = margin + i * square_size + square_size / 2
        # place letters slightly below the board
        y = svg_height - (margin * 0.25)
        svg_parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{margin * 0.8}" '
            f'fill="#333" dominant-baseline="hanging">{chr(97 + i)}</text>'
        )
    # Numbers on left
    for i in range(height):
        y = margin + i * square_size + square_size / 2
        x = margin * 0.6
        svg_parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{margin * 0.8}" '
            f'fill="#333" dominant-baseline="middle">{height - i}</text>'
        )

    # Draw board squares in a group
    svg_parts.append('<g id="squares">')
    for r in range(height):
        for c in range(width):
            x = margin + c * square_size
            y = margin + r * square_size
            # choose two pleasant square colors (light/dark)
            color = "#E8D0AA" if (r + c) % 2 == 0 else "#B87C4C"
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="{color}" />')
    svg_parts.append('</g>')

    # Draw pieces on top
    svg_parts.append('<g id="pieces">')
    # Softened black so it reads on backgrounds (use #000 if you really want pure black)
    black_fill = "#111111"
    white_fill = "#ffffff"
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            token = cell.strip()
            if not token:
                continue
            cx = margin + c * square_size + square_size / 2
            cy = margin + r * square_size + square_size / 2
            radius = square_size * 0.4
            if token.lower() == 'b':
                fill = black_fill
                stroke = "#fff"
            else:
                fill = white_fill
                stroke = "#000"
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2" />'
            )
            # kings: upper-case token => draw small star/crown using the per-cell gradient id
            if token.isupper():
                gid = f'crown_gradient_{r}_{c}'
                # small star path centered at cx,cy
                outer_r = radius * 0.5
                inner_r = outer_r * 0.382
                points = []
                for i_pt in range(10):
                    ang = (i_pt * math.pi / 5) - (math.pi / 2)
                    rad = outer_r if (i_pt % 2 == 0) else inner_r
                    px = cx + rad * math.cos(ang)
                    py = cy + rad * math.sin(ang)
                    points.append(f'{px:.2f},{py:.2f}')
                svg_parts.append(
                    f'<path d="M {" L ".join(points)} Z" fill="url(#{gid})" stroke="#DAA520" stroke-width="1.5" />'
                )

    svg_parts.append('</g>')
    svg_parts.append('</svg>')

    return "\n".join(svg_parts)


def svg_to_png(svg: str):
    with Image(blob=svg.encode('utf-8'), background=Color("transparent")) as img:
        img.format = "png"
        return img.make_blob()
