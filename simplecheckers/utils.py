import draughts
from typing import List, Tuple
from wand.image import Image
from wand.color import Color


def board_to_svg(board: 'draughts.Board', arrows: List[int]) -> str:
    """
    Convert board to SVG and draw a connected arrow path for a list of playable-square indices.
    arrows: list of 1-based indices into the playable squares (top->bottom, left->right),
    indices interpreted rotated 180° (1 -> last playable square).
    """
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

    # Playable (dark) squares: (r + c) % 2 == 1
    is_playable = lambda r, c: (r + c) % 2 == 1

    # Build playable squares list in printed order (top->bottom, left->right)
    playable: List[Tuple[int, int]] = []
    for r in range(height):
        for c in range(width):
            if is_playable(r, c):
                playable.append((r, c))

    def index_to_rc(idx: int) -> Tuple[int, int]:
        # 1-based idx -> playable list, rotated 180° (reverse the playable list)
        if not isinstance(idx, int):
            raise ValueError("Arrow indices must be integers.")
        n = len(playable)
        if idx < 1 or idx > n:
            raise ValueError(f"arrow index {idx} out of range (1..{n})")
        return playable[-idx]

    # Convert indices to SVG centers (rotate to match piece drawing)
    centers: List[Tuple[float, float]] = []
    for idx in arrows or []:
        r, c = index_to_rc(idx)
        rotated_r = height - 1 - r
        rotated_c = width - 1 - c
        cx = margin + rotated_c * square_size + square_size / 2
        cy = margin + rotated_r * square_size + square_size / 2
        centers.append((cx, cy))

    # Start svg
    svg_parts = [
        f'<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">'
    ]

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

    # Draw arrows
    if centers:
        arrow_color = "#17841E"
        stroke_w = max(4.0, square_size * 0.16)
        svg_parts.append(f'<g id="arrows" fill="none" style="opacity:0.95;">')

        poly_points = list(centers) if len(centers) > 1 else []

        # Draw the polyline if there are >1 centers (i.e. at least one segment)
        if poly_points:
            points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly_points)
            svg_parts.append(
                f'<polyline points="{points_str}" stroke="{arrow_color}" stroke-width="{stroke_w:.2f}" '
                f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            )

        # node circles: fill same color
        node_r = max(3.0, square_size * 0.08)
        for x, y in centers[:-1]:
            svg_parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{node_r:.2f}" fill="{arrow_color}" />')

        svg_parts.append('</g>')

    # Draw pieces
    svg_parts.append('<g id="pieces">')
    black_fill = "#111111"
    red_fill = "#DD2E44"
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
                fill = red_fill
                stroke = black_fill
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="3" />'
            )
            if token.isupper():
                inner_r = radius * 0.78
                svg_parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="{fill}" stroke="{stroke}" stroke-width="3" />'
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
    

def board_to_png(board: draughts.Board, overlay_path: str, arrows: List[int]) -> bytes:
    return svg_to_png(board_to_svg(board, arrows), overlay_path)
