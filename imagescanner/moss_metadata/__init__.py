"""Read-only MOSS presentation data; deliberately separate from generation validation.

Kept identical in holo-cogs/arcenciel and crab-cogs/imagescanner so either cog
can be installed independently. Coordinate semantics match the AEC viewer.
"""

import json
import math
from collections import Counter
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TypeGuard, cast

from .types import Box, Metadata, MossLayout, MossMetadata

MAX_TEXT = 131072
MAX_REGIONS = 128


def record(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def sequence(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def number(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= 1e100 and math.isfinite(value)
    )


def text(value: object) -> str:
    return value if isinstance(value, str) else ""


def read_box(value: object) -> Box | None:
    if sequence(value) and len(value) == 4 and all(number(n) for n in value):
        return cast(Box, tuple(value))
    return None


@dataclass(frozen=True)
class Region:
    label: str
    caption: str
    text: str | None
    bbox: Box | None
    normalized: Box | None

    @classmethod
    def from_raw(cls, value: object) -> "Region":
        item = value if record(value) else {}
        literal = item.get("text")
        return cls(
            text(item.get("label")) or "region",
            text(item.get("caption")),
            literal if isinstance(literal, str) else None,
            read_box(item.get("bbox")),
            None,
        )


@dataclass(frozen=True)
class Layout:
    scene: str
    regions: tuple[Region, ...]
    meta: tuple[str, ...]
    suffix: str
    warnings: tuple[str, ...]


def read_layout(prompt: object, width: object = None, height: object = None) -> Layout | None:
    if not isinstance(prompt, str) or len(prompt) > MAX_TEXT:
        return None
    try:
        raw, end = json.JSONDecoder().raw_decode(prompt.lstrip())
    except (ValueError, RecursionError):
        return None
    if not record(raw) or raw.get("bbox_coord_space") != "abs_centralized" or raw.get("bbox_format") != "yxyx":
        return None
    summary, items = raw.get("summary"), raw.get("items")
    if (
        not record(summary)
        or not isinstance(summary.get("caption"), str)
        or not sequence(items)
        or len(items) > MAX_REGIONS
    ):
        return None
    size = (width, height) if number(width) and number(height) and width > 0 and height > 0 else None
    single = summary.get("canvas") in (None, "single")
    regions: list[Region] = []
    warnings: list[str] = []
    for entry in items:
        region = Region.from_raw(entry)
        bbox = region.bbox
        normalized: Box | None = None
        if bbox is not None and single and size is not None:
            width, height = size
            top, left, bottom, right = bbox
            if top < bottom and left < right:
                points = [
                    max(0.0, min(1.0, n / dim + 0.5))
                    for n, dim in zip(bbox, (height, width, height, width), strict=True)
                ]
                if points[0] < points[2] and points[1] < points[3]:
                    normalized = (points[0], points[1], points[2], points[3])
                    if top < -height / 2 or left < -width / 2 or bottom > height / 2 or right > width / 2:
                        warnings.append("Some regions extend beyond the image; only the visible area is shown.")
        regions.append(replace(region, normalized=normalized))
    if not single:
        warnings.append("This canvas layout cannot be overlaid on a single image.")
    elif any(region.normalized is None for region in regions):
        warnings.append("Some positions cannot be mapped reliably; their descriptions are still available.")
    meta = summary.get("meta")
    return Layout(
        text(summary["caption"]),
        tuple(regions),
        tuple(v for v in meta[:32] if isinstance(v, str)) if sequence(meta) else (),
        prompt.lstrip()[end:],
        tuple(dict.fromkeys(warnings)),
    )


def from_params(params: Mapping[str, object], resolved_prompt: object = None) -> Layout | None:
    width: int | None = None
    height: int | None = None
    with suppress(ValueError):
        width, height = map(int, text(params.get("Size")).lower().split("x"))
    return read_layout(resolved_prompt if isinstance(resolved_prompt, str) else params.get("Prompt"), width, height)


def from_metadata(metadata: Metadata) -> Layout | None:
    # A failed Comfy resolution must not fall back to an unrelated text node.
    resolved = (metadata.moss_prompt or "") if isinstance(metadata, MossMetadata) and metadata.is_comfy else None
    return from_params(metadata.as_dict(), resolved)


def summary_params(params: Mapping[str, object], layout: MossLayout | None) -> dict[str, object]:
    """Only the display copy changes. Raw metadata and regeneration inputs survive."""
    if layout is None:
        return dict(params)
    counts = Counter(region.label for region in layout.regions)
    result: dict[str, object] = {
        "Scene · MOSS": layout.scene or "No scene description saved.",
        "Regions": f"{len(layout.regions)} — " + ", ".join(f"{count} {label}" for label, count in counts.items())
        if counts
        else "0",
    }
    if layout.meta:
        result["Scene metadata"] = ", ".join(layout.meta)
    if layout.suffix.strip():
        result["Additional Prompt"] = layout.suffix.strip()
    result.update((k, v) for k, v in params.items() if k != "Prompt")
    return result
