"""Bounded static evaluation of known Comfy MOSS nodes. Never executes a workflow.

Mirrors AEC's comfyPromptResolver; kept identical in both independently usable cogs.
"""

import json
import math
import re
from dataclasses import dataclass

from . import MAX_REGIONS, MAX_TEXT, number, read_layout, record, sequence, text

WIDGETS = {
    "CLIPTextEncode": ["text"],
    "ArcEnCielMossTextEncode": ["text"],
    "StringReplace": ["string", "find", "replace"],
    "MOSSImageLayoutPrompt": ["prompt", "width", "height", "character_boxes"],
    "CreateBoundingBoxes": ["width", "height", "editor_state", "last_incoming"],
    "ResolutionSelector": ["aspect_ratio", "megapixels", "multiple"],
}


@dataclass
class Node:
    kind: str
    inputs: dict[str, object]
    widgets: list[object]
    named: dict[str, object]
    mode: object


def dimension(value: object) -> bool:
    return number(value) and 0 < value <= 16384


def resolve_moss_prompt(flow: dict[str, object]) -> str | None:
    """Return only an unambiguous, sampler-connected positive MOSS prompt."""
    raw_links = flow.get("links")
    raw_nodes = flow.get("nodes")
    if (sequence(raw_links) and len(raw_links) > 16384) or (sequence(raw_nodes) and len(raw_nodes) > 4096):
        return None
    links = (
        {str(link[0]): link for link in raw_links if sequence(link) and len(link) >= 3} if sequence(raw_links) else {}
    )
    entries = (
        [(str(n.get("id", i)), n) for i, n in enumerate(raw_nodes) if record(n)]
        if sequence(raw_nodes)
        else list(flow.items())
    )
    if len(entries) > 4096:
        return None
    nodes: dict[str, Node] = {}
    for node_id, value in entries:
        if not record(value):
            continue
        raw_inputs = value.get("inputs")
        inputs: dict[str, object] = dict(raw_inputs) if record(raw_inputs) else {}
        if sequence(raw_inputs):
            for entry in raw_inputs:
                if record(entry) and isinstance(entry.get("name"), str) and entry.get("link") is not None:
                    link = links.get(str(entry["link"]))
                    inputs[text(entry["name"])] = [str(link[1]), link[2]] if link else None
        widgets, named = value.get("widgets_values"), value.get("widgets_values_named")
        nodes[node_id] = Node(
            text(value.get("type") or value.get("class_type")),
            inputs,
            widgets if sequence(widgets) else [],
            named if record(named) else {},
            value.get("mode"),
        )
    cache: dict[tuple[str, int], object] = {}
    visiting: set[tuple[str, int]] = set()
    evaluations = 0

    def resolve(value: object) -> object:
        if sequence(value) and len(value) == 2 and isinstance(value[0], (str, int)) and type(value[1]) is int:
            return output(str(value[0]), value[1])
        return value

    def field(node: Node, key: str) -> object:
        if key in node.inputs:
            return resolve(node.inputs[key])
        if key in node.named:
            return resolve(node.named[key])
        names = WIDGETS.get(node.kind, [])
        index = names.index(key) if key in names else -1
        return node.widgets[index] if 0 <= index < len(node.widgets) else None

    def output(node_id: str, slot: int) -> object:
        nonlocal evaluations
        key = (node_id, slot)
        if key in cache:
            return cache[key]
        node = nodes.get(node_id)
        if node is None or node.mode in (2, 4) or key in visiting or len(visiting) >= 64 or evaluations >= 4096:
            return None
        evaluations += 1
        visiting.add(key)
        result = evaluate(node, slot)
        visiting.remove(key)
        cache[key] = None if isinstance(result, str) and len(result) > MAX_TEXT else result
        return cache[key]

    def evaluate(node: Node, slot: int) -> object:
        if node.kind in ("CLIPTextEncode", "ArcEnCielMossTextEncode") and slot == 0:
            return field(node, "text")
        if node.kind == "Reroute" and slot == 0:
            return resolve(next(iter(node.inputs.values()), None))
        if node.kind == "StringReplace" and slot == 0:
            original, find, replacement = (field(node, key) for key in ("string", "find", "replace"))
            if not isinstance(original, str) or not isinstance(find, str) or not isinstance(replacement, str):
                return None
            if len(original) > MAX_TEXT or len(replacement) > MAX_TEXT:
                return None
            if len(original) + (original.count(find) * len(replacement)) > MAX_TEXT:
                return None
            return original.replace(find, replacement)
        if node.kind == "ResolutionSelector" and slot in (0, 1):
            ratio, mp, multiple = (field(node, key) for key in ("aspect_ratio", "megapixels", "multiple"))
            multiple = 8 if multiple is None else multiple
            match = re.match(r"^(1:1|2:3|3:2|3:4|4:3|9:16|16:9|21:9) \(", text(ratio))
            if not match or not number(mp) or not number(multiple) or not dimension(mp) or not dimension(multiple):
                return None
            ratio_w, ratio_h = map(int, match[1].split(":"))
            return (
                round((ratio_w, ratio_h)[slot] * math.sqrt(mp * 1024 * 1024 / (ratio_w * ratio_h)) / multiple)
                * multiple
            )
        if node.kind == "CreateBoundingBoxes" and slot == 2:
            if node.inputs.get("bboxes") is not None or node.named.get("bboxes") is not None:
                return None
            width, height, state = (field(node, key) for key in ("width", "height", "editor_state"))
            if (
                not number(width)
                or not number(height)
                or not dimension(width)
                or not dimension(height)
                or not sequence(state)
                or len(state) > MAX_REGIONS
            ):
                return None
            editor_elements: list[dict[str, object]] = []
            for item in state:
                if not record(item):
                    return None
                x, y, w, h = (item.get(key) for key in ("x", "y", "width", "height"))
                if not number(x) or not number(y) or not number(w) or not number(h):
                    return None
                meta = item.get("metadata")
                meta = meta if record(meta) else {}
                if meta.get("palette"):
                    return None
                ys = sorted(max(0, min(1000, round(n / height * 1000))) for n in (y, y + h))
                xs = sorted(max(0, min(1000, round(n / width * 1000))) for n in (x, x + w))
                editor_elements.append(
                    {
                        "type": meta.get("type"),
                        "bbox": [ys[0], xs[0], ys[1], xs[1]],
                        "desc": meta.get("desc", ""),
                        "text": meta.get("text", ""),
                    }
                )
            return editor_elements
        if node.kind == "MOSSImageLayoutPrompt" and slot == 0:
            prompt, elements, width, height, characters = (
                field(node, key) for key in ("prompt", "element", "width", "height", "character_boxes")
            )
            if not isinstance(prompt, str) or not sequence(elements) or len(elements) > MAX_REGIONS:
                return None
            if not elements:
                return prompt
            if (
                not number(width)
                or not number(height)
                or not dimension(width)
                or not dimension(height)
                or characters is not None
                and not isinstance(characters, str)
            ):
                return None
            char_ids = set(map(int, re.findall(r"\d+", text(characters))))
            items: list[dict[str, object]] = []
            for index, element in enumerate(elements):
                if not record(element):
                    return None
                coords = element.get("bbox")
                if not sequence(coords) or len(coords) != 4:
                    return None
                bbox: list[int] = []
                for edge, coordinate in enumerate(coords):
                    if not number(coordinate):
                        return None
                    size = height if edge % 2 == 0 else width
                    pixel = round(coordinate * size / 1000, 9)
                    bbox.append((math.floor(pixel) if edge < 2 else math.ceil(pixel)) - math.floor(size / 2))
                label = "text" if element.get("type") == "text" else "character" if index + 1 in char_ids else "object"
                items.append(
                    {
                        "label": label,
                        "caption": element.get("desc", ""),
                        "bbox": bbox,
                        **({"text": element.get("text", "")} if label == "text" else {}),
                    }
                )
            return json.dumps(
                {
                    "summary": {"caption": prompt.strip()},
                    "items": items,
                    "bbox_coord_space": "abs_centralized",
                    "bbox_format": "yxyx",
                }
            )
        return None

    try:
        values = [
            field(n, "positive")
            for n in nodes.values()
            if n.kind in ("KSampler", "KSamplerAdvanced", "CFGGuider")
            and n.mode not in (2, 4)
            and "positive" in n.inputs
        ]
        if values and isinstance(values[0], str) and all(v == values[0] for v in values) and read_layout(values[0]):
            return values[0]
    except (ValueError, OverflowError, RecursionError):
        pass
    return None
