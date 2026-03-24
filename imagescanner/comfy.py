from io import BytesIO
import json
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass, field
from PIL import Image

NEGATIVE_HINTS = (
    "negative prompt", "worst quality", "low quality",
    "bad anatomy", "bad hands", "jpeg artifacts",
    "watermark", "deformed", "blurry",
)


@dataclass
class ComfyLora:
    name: str
    weight: float = 1.0


@dataclass
class ComfyMetadata:
    is_comfy: bool = False
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | str | None = None
    steps: int | None = None
    cfg: float | None = None
    sampler: str | None = None
    extra_seed: int | None = None
    extra_seed_strength: float | None = None
    upscaler: str | None = None
    denoise: float | None = None
    adetailer_model: str | None = None
    adetailer_denoise: float | None = None
    loras: list[ComfyLora] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> OrderedDict[str, Any]:
        output: dict[str, Any] = OrderedDict()

        if self.prompt:
            output["Prompt"] = self.prompt
        if self.negative_prompt:
            output["Negative Prompt"] = self.negative_prompt
        if self.seed is not None and "Seed" not in output:
            output["Seed"] = self.seed
        if self.steps is not None and "Steps" not in output:
            output["Steps"] = self.steps
        if self.cfg is not None and "Cfg" not in output:
            output["CFG"] = self.cfg
        if self.sampler and "Sampler" not in output:
            output["Sampler"] = self.sampler
        if self.extra_seed is not None:
            output["Extra Seed"] = self.extra_seed
        if self.extra_seed_strength is not None:
            output["Extra Seed Strength"] = self.extra_seed_strength
        if self.upscaler:
            output["Upscaler"] = self.upscaler
        if self.denoise is not None:
            output["Denoising"] = self.denoise
        if self.adetailer_model:
            output["ADetailer Model"] = self.adetailer_model
        if self.adetailer_denoise is not None:
            output["ADetailer Denoising"] = self.adetailer_denoise

        if output.get("Prompt"):
            for lora in self.loras:
                clean_name = lora.name.replace(".safetensors", "")
                tag = f"<lora:{clean_name}:{format(lora.weight, 'g')}>"
                if tag not in output['Prompt']:
                    output["Prompt"] = f"{output['Prompt']} {tag}".strip()

        return output


@dataclass
class Node:
    id: str
    node_type: str
    inputs: dict[str, Any]
    widgets: list[Any]


class ComfyMetadataReader:
    @classmethod
    def from_bytes(cls, b) -> ComfyMetadata:
        result = ComfyMetadata()
        try:
            image = Image.open(BytesIO(b))
            return cls.from_info(image.info)
        except Exception as error:
            result.error = f"{type(error).__name__}: {error}"
        return result

    @classmethod
    def from_info(cls, meta: dict[str, Any]) -> ComfyMetadata:
        result = ComfyMetadata()
        try:
            workflow = cls.extract_workflow(meta)
            if workflow is None:
                result.error = "Workflow not found"
                return result
            nodes = cls.normalize_nodes(workflow)
            if not nodes:
                result.error = "Workflow nodes not found"
                return result
            result.is_comfy = True
            cls.parse_nodes(nodes, result)
        except Exception as error:
            result.error = f"{type(error).__name__}: {error}"
        return result

    @staticmethod
    def extract_workflow(meta: dict) -> dict[str, Any] | None:
        for key in ("prompt", "workflow"):
            parsed = ComfyMetadataReader.parse_json_like(meta.get(key))
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def parse_json_like(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if not isinstance(value, str):
            return None
        
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(value[start:end+1])
                except json.JSONDecodeError:
                    return None
        return None

    @staticmethod
    def normalize_nodes(flow: Any) -> list[Node]:
        if not isinstance(flow, dict):
            return []

        if isinstance(flow.get("nodes"), list):
            nodes: list[Node] = []
            for raw in flow["nodes"]:
                if not isinstance(raw, dict):
                    continue
                node_type = ComfyMetadataReader.as_text(raw.get("type") or raw.get("class_type"))
                if not node_type:
                    continue
                node_id = ComfyMetadataReader.as_text(raw.get("id")) or ""
                inputs = raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {}
                widgets = raw.get("widgets_values") if isinstance(raw.get("widgets_values"), list) else []
                nodes.append(Node(node_id, node_type, inputs or {}, widgets or []))
            return nodes

        sortable_entries: list[tuple[int, str, dict[str, Any]]] = []
        for key, value in flow.items():
            if not isinstance(value, dict):
                continue
            node_type = ComfyMetadataReader.as_text(value.get("class_type") or value.get("type"))
            if not node_type:
                continue
            sort_key = int(key) if str(key).isdigit() else 10**9
            sortable_entries.append((sort_key, str(key), value))
        sortable_entries.sort(key=lambda entry: entry[0])

        nodes = []
        for _, key, value in sortable_entries:
            inputs = value.get("inputs") if isinstance(value.get("inputs"), dict) else {}
            widgets = value.get("widgets_values") if isinstance(value.get("widgets_values"), list) else []
            nodes.append(Node(key, str(value.get("class_type") or value.get("type")), inputs or {}, widgets or []))
        return nodes

    @staticmethod
    def looks_negative(text: str) -> bool:
        lower = text.lower()
        return any(hint in lower for hint in NEGATIVE_HINTS)

    @staticmethod
    def as_text(value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return None

    @staticmethod
    def as_int(value: Any) -> int | None:
        if not value or isinstance(value, bool):
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    @staticmethod
    def as_float(value: Any) -> float | None:
        if not value or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if not value:
                return None
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def set_if_missing(meta: ComfyMetadata, key: str, value: Any) -> None:
        if value is None:
            return
        if getattr(meta, key) is None:
            setattr(meta, key, value)

    @staticmethod
    def add_lora(meta: ComfyMetadata, name: str, weight: float) -> None:
        name = name.strip()
        if not name:
            return
        for existing in meta.loras:
            if existing.name.lower() == name.lower():
                return
        meta.loras.append(ComfyLora(name=name, weight=weight))

    @classmethod
    def parse_nodes(cls, nodes: list[Node], meta: ComfyMetadata) -> None:
        text_candidates: list[str] = []

        for node in nodes:
            node_type_lower = node.node_type.lower()
            inputs = node.inputs

            text_value = cls.as_text(inputs.get("text"))
            if text_value:
                if "negative" in node_type_lower or "neg" in node_type_lower:
                    cls.set_if_missing(meta, "negative_prompt", text_value)
                else:
                    text_candidates.append(text_value)

            if "lora" in node_type_lower:
                lora_name = cls.as_text(inputs.get("lora_name") or inputs.get("lora") or inputs.get("name"))
                if lora_name:
                    weight = (
                        cls.as_float(inputs.get("strength_model"))
                        or cls.as_float(inputs.get("weight"))
                        or cls.as_float(inputs.get("strength"))
                        or 1.0
                    )
                    cls.add_lora(meta, lora_name, weight)

            if "sampler" in node_type_lower:
                cls.set_if_missing(meta, "seed", cls.as_int(inputs.get("seed")) or cls.as_text(inputs.get("seed")))
                cls.set_if_missing(meta, "steps", cls.as_int(inputs.get("steps")))
                cls.set_if_missing(meta, "cfg", cls.as_float(inputs.get("cfg")))
                cls.set_if_missing(meta, "sampler", cls.as_text(inputs.get("sampler_name") or inputs.get("sampler") or inputs.get("samplerName")))

                if not meta.seed and len(node.widgets) > 0:
                    cls.set_if_missing(meta, "seed", cls.as_int(node.widgets[0]) or cls.as_text(node.widgets[0]))
                if meta.steps is None and len(node.widgets) > 2:
                    cls.set_if_missing(meta, "steps", cls.as_int(node.widgets[2]))
                if meta.cfg is None and len(node.widgets) > 3:
                    cls.set_if_missing(meta, "cfg", cls.as_float(node.widgets[3]))
                if not meta.sampler and len(node.widgets) > 4:
                    cls.set_if_missing(meta, "sampler", cls.as_text(node.widgets[4]))

                if node.id == "upscale_0_sampler" or "upscale" in node_type_lower:
                    cls.set_if_missing(meta, "denoise", cls.as_float(inputs.get("denoise")))

            if node.id == "extra_seed_extra_noise":
                cls.set_if_missing(meta, "extra_seed", cls.as_int(inputs.get("noise_seed")))
            elif node.id == "extra_seed_noised_latent_blend":
                blend = cls.as_float(inputs.get("blend_factor"))
                if blend is not None:
                    strength = round(1.0 - blend, 4)
                    cls.set_if_missing(meta, "extra_seed_strength", strength)

            if "upscale" in node_type_lower and "loader" in node_type_lower:
                cls.set_if_missing(
                    meta,
                    "upscaler",
                    cls.as_text(inputs.get("model_name") or inputs.get("upscale_model") or inputs.get("upscale_model_name")),
                )

            if "adetailer" in node_type_lower:
                cls.set_if_missing(meta, "adetailer_model", cls.as_text(inputs.get("model")))
                cls.set_if_missing(meta, "adetailer_denoise", cls.as_float(inputs.get("denoise")))

        if not meta.prompt and text_candidates:
            non_negative = [text for text in text_candidates if not cls.looks_negative(text)]
            meta.prompt = non_negative[0] if non_negative else text_candidates[0]
        if not meta.negative_prompt and text_candidates:
            negatives = [text for text in text_candidates if cls.looks_negative(text)]
            if negatives:
                meta.negative_prompt = negatives[0]
            elif len(text_candidates) > 1:
                meta.negative_prompt = text_candidates[1]
