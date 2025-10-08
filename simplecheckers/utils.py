import math
import base64
import draughts
from wand.image import Image
from wand.color import Color


def load_font_base64(path: str) -> str:
    with open(path, "rb") as f:
        font_bytes = f.read()  # read raw font bytes
    b64 = base64.b64encode(font_bytes).decode("ascii")  # base64 encode -> string
    return f"data:font/ttf;base64,{b64}"


def board_to_svg(board: draughts.Board, font_path: str) -> str:
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
    font_data_uri = load_font_base64(font_path)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}">',
        "<style><![CDATA[",
        "@font-face {",
        "  font-family: 'DejaVuSans';",
        f"  src: url('{font_data_uri}') format('truetype');",
        "}",
        "text { font-family: 'DejaVuSans'; }",
        "]]></style>",
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
    dark_sq = "#B87C4C"
    for r in range(height):
        for c in range(width):
            x = margin + c * square_size
            y = margin + r * square_size
            color = light_sq if not is_playable(r, c) else dark_sq
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="{color}" />'
            )
    svg_parts.append('</g>')

    # Draw pieces (black + red). red replaces white
    svg_parts.append('<g id="pieces">')
    black_fill = "#111111"
    red_fill = "#DD2E44"
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
                stroke = red_fill
            else:
                # treat anything else (w/W) as the red piece
                fill = red_fill
                stroke = black_fill
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="3" />'
            )
            # kings (upper-case): draw crown/star on top of the piece (but under the numbers)
            if token.isupper():
                outer_r = radius * 0.6
                inner_r = outer_r * 0.45
                points = []
                for i_pt in range(10):
                    ang = (i_pt * math.pi / 5) - (math.pi / 2)
                    rad = outer_r if (i_pt % 2 == 0) else inner_r
                    px = cx + rad * math.cos(ang)
                    py = cy + rad * math.sin(ang)
                    points.append(f'{px:.2f},{py:.2f}')
                svg_parts.append(
                    f'<path d="M {" L ".join(points)} Z" fill="url(#crown_gradient)" stroke="#DAA520" stroke-width="1.5" />'
                )
    svg_parts.append('</g>')

    # Number playable squares (1..N), always on top and color changes if there's a piece under it.
    svg_parts.append('<g id="numbers" font-family="sans-serif">')
    font_size = square_size * 0.30
    number = 1
    for r in range(height):
        for c in range(width):
            if not is_playable(r, c):
                continue
            cx = margin + c * square_size + square_size / 2
            cy = margin + r * square_size + square_size / 2

            # detect if a piece occupies this cell
            token = rows[r][c].strip()
            occupied = bool(token)
            # choose number color depending on piece below:
            # - if empty: white
            # - if black piece: white (contrasts black)
            # - if red piece: black (contrasts red)
            if not occupied:
                num_color = "#ffffff"
            else:
                num_color = "#ffffff" if token.lower() == 'b' else "#000000"

            svg_parts.append(
                f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central" '
                f'font-size="{font_size}" font-weight="bold" fill="{num_color}">{number}</text>'
            )
            number += 1
    svg_parts.append('</g>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def svg_to_png(svg: str) -> bytes:
    with Image(blob=svg.encode('utf-8'), background=Color("transparent")) as img:
        img.format = "png"
        return img.make_blob() or b''
    

def board_to_png(board: draughts.Board, font_path: str) -> bytes:
    return svg_to_png(board_to_svg(board, font_path))
