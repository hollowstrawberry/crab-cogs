import math
import draughts
from wand.image import Image
from wand.color import Color


def create_svg(board: draughts.Board) -> str:
    """Create an SVG of a board. https://github.com/AttackingOrDefending/pydraughts/blob/main/draughts/svg.py"""
    # Base square size
    square_size = 40
    margin = 16  # Fixed margin size for coordinates

    # Calculate SVG dimensions based on board size
    str_representation = list(map(lambda row_str: row_str.split("|"), filter(lambda row_str: "|" in row_str, str(board).split("\n"))))
    width = len(str_representation[0])
    height = len(str_representation)
    svg_width = (square_size * width) + (2 * margin)
    svg_height = (square_size * height) + (2 * margin)

    # Background color for coordinates
    svg = [f'''<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
<rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#1A1A1A"/>''']

    # Add coordinates in white
    for i in range(width):
        # Letters along bottom
        svg.append(f'<text x="{margin + i * square_size + square_size / 2}" '
                   f'y="{svg_height - margin / 4}" '
                   f'text-anchor="middle" font-size="{margin * 0.8}" '
                   f'fill="white">{chr(97 + i)}</text>')

    for i in range(height):
        # Numbers along left side
        svg.append(f'<text x="{margin / 2}" '
                   f'y="{margin + i * square_size + square_size / 2}" '
                   f'text-anchor="middle" dominant-baseline="central" '
                   f'font-size="{margin * 0.8}" fill="white">{height - i}</text>')

    # Draw board
    for row in range(height):
        for col in range(width):
            x = margin + col * square_size
            y = margin + row * square_size
            color = "#E8D0AA" if (row + col) % 2 == 0 else "#B87C4C"
            svg.append(f'<rect x="{x}" y="{y}" width="{square_size}" '
                       f'height="{square_size}" fill="{color}"/>')

    # Draw pieces
    for row, row_str in enumerate(str_representation):
        for col, piece in enumerate(row_str):
            piece = piece.strip()
            if not piece:
                continue

            # Center of square
            cx = margin + col * square_size + square_size // 2
            cy = margin + row * square_size + square_size // 2

            piece_radius = square_size * 0.4
            piece_color = "#000000" if piece.lower() == 'b' else "#FFFFFF"
            stroke_color = "#FFFFFF" if piece.lower() == 'b' else "#000000"

            # Draw main piece
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{piece_radius}" '
                       f'fill="{piece_color}" stroke="{stroke_color}" stroke-width="2"/>')

            # Enhanced crown for kings
            if piece.isupper():
                gradient_id = f"crown_gradient_{cx}_{cy}"
                svg.append(f'''<defs>
    <linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:#FFD700;stop-opacity:1" />
        <stop offset="50%" style="stop-color:#FFA500;stop-opacity:1" />
        <stop offset="100%" style="stop-color:#FFD700;stop-opacity:1" />
    </linearGradient>
</defs>''')

                # Draw 5-pointed star
                num_points = 5
                outer_radius = piece_radius * 0.5
                inner_radius = outer_radius * 0.382
                points = []

                for i in range(num_points * 2):
                    angle = (i * math.pi / num_points) - (math.pi / 2)
                    radius = outer_radius if i % 2 == 0 else inner_radius
                    x = cx + radius * math.cos(angle)
                    y = cy + radius * math.sin(angle)
                    points.append(f"{x},{y}")

                svg.append(f'<path d="M {" L ".join(points)} Z" '
                           f'fill="url(#{gradient_id})" '
                           f'stroke="#DAA520" stroke-width="2"/>')

    svg.append('</svg>')
    return '\n'.join(svg)


def svg_to_png(svg: str):
    with Image(blob=svg.encode('utf-8'), background=Color("transparent")) as img:
        img.format = "png"
        return img.make_blob()
