import draughts
from typing import List, Tuple, Union
from wand.image import Image
from wand.color import Color


def board_to_svg(board: draughts.Board, arrows: List[Union[int, Tuple[int,int]]]) -> str:
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

    # Build list of playable squares in printed order (top->bottom, left->right)
    playable = []
    for r in range(height):
        for c in range(width):
            if is_playable(r, c):
                playable.append((r, c))  # 1-index will map to playable[i-1]

    # Helper to convert various arrow formats to list of board-centers (cx, cy)
    def index_to_rc(idx: int):
        # idx is 1-based index into playable list
        if idx < 1 or idx > len(playable):
            raise ValueError(f"arrow index {idx} out of range (1..{len(playable)})")
        return playable[idx - 1]

    def to_sequence(arrows_in):
        if not arrows_in:
            return []

        # Case: list of ints -> treat as playable square indices
        if all(isinstance(a, int) for a in arrows_in):
            return list(arrows_in)

        # Case: list of tuples
        if all(isinstance(a, tuple) and len(a) == 2 and isinstance(a[0], int) and isinstance(a[1], int)
               for a in arrows_in):
            tuples = arrows_in  # type: ignore
            # Detect edge-list pattern like [(1,6), (6,14), ...] and flatten to [1,6,14,...]
            is_edge_chain = True
            for i in range(len(tuples) - 1):
                if tuples[i][1] != tuples[i + 1][0]:
                    is_edge_chain = False
                    break
            if is_edge_chain:
                seq = [tuples[0][0]] + [t[1] for t in tuples]
                if all(isinstance(x, int) for x in seq):
                    return seq

            # Otherwise, treat each tuple as a (r,c) coordinate (either 0-based or 1-based)
            # Detect if values look 1-based (i.e., min >= 1 and max <= corresponding dimension)
            rs = [t[0] for t in tuples]
            cs = [t[1] for t in tuples]
            min_r, max_r = min(rs), max(rs)
            min_c, max_c = min(cs), max(cs)

            # If all values lie in 1..height/width, assume 1-based. Otherwise assume 0-based.
            if 1 <= min_r and max_r <= height and 1 <= min_c and max_c <= width:
                # convert to 0-based
                return [ (r-1, c-1) for (r,c) in tuples ]
            else:
                return [ (r, c) for (r, c) in tuples ]

        raise ValueError("Unsupported arrow format. Use ints (1..N playable squares), or (r,c) tuples, "
                         "or edge pairs like [(a,b),(b,c),...]")

    seq_raw = to_sequence(arrows)

    # Convert sequence entries into (cx,cy) in SVG space. Returned sequence will be list of (x,y) floats.
    centers = []
    for item in seq_raw:
        if isinstance(item, int):
            r, c = index_to_rc(item)
        else:
            # item is (r,c)
            r, c = item

        # rotate the same way we rotate pieces so arrows line up visually with pieces
        rotated_r = height - 1 - r
        rotated_c = width - 1 - c
        cx = margin + rotated_c * square_size + square_size / 2
        cy = margin + rotated_r * square_size + square_size / 2
        centers.append((cx, cy))

    # Start svg (no outer background rect; transparent by default)
    svg_parts = [
        f'<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">'
    ]

    # Add defs for arrow marker
    svg_parts.append('''
    <defs>
      <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5"
              orient="auto" markerUnits="strokeWidth">
        <path d="M0,0 L10,3.5 L0,7 z" fill="currentColor" />
      </marker>
    </defs>
    ''')

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

    # Draw arrows (behind pieces so destination piece is visible on top)
    if centers:
        svg_parts.append('<g id="arrows" fill="none" stroke="yellow" stroke-width="8" style="opacity:0.95; color: #FFD54F;">')
        # Build points string for polyline
        points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in centers)
        stroke_w = max(4, int(square_size * 0.15))
        # Polyline + arrowhead at the end
        svg_parts.append(
            f'<polyline points="{points_str}" stroke="currentColor" stroke-width="{stroke_w}" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrowhead)"/>'
        )
        # small circles at nodes to highlight starts and jumps
        node_r = max(3, square_size * 0.06)
        for (x, y) in centers:
            svg_parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{node_r:.2f}" fill="currentColor" stroke="black" stroke-width="1"/>'
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
            # sillyness to rotate the board (same as arrows mapping)
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
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="3" />'
            )
            # kings (upper-case): draw another ring
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
    

def board_to_png(board: draughts.Board, overlay_path: str, arrows: List[Union[int, Tuple[int,int]]]) -> bytes:
    return svg_to_png(board_to_svg(board, arrows), overlay_path)
