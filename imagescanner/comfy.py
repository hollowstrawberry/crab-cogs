import os
import re
import math
import json
from io import BytesIO
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass, field
from PIL import Image

from imagescanner.metadata import Metadata

NEGATIVE_HINTS = (
    "negative prompt",
    "worst quality",
    "low quality",
    "bad anatomy",
    "bad hands",
    "jpeg artifacts",
    "watermark",
    "deformed",
)

LORA_INPUT_KEY_RE = re.compile(r"^lora_\d+$", re.IGNORECASE)
RESOURCE_EXT_RE = re.compile(r"\.(?:safetensors|ckpt|pth|pt|bin)$", re.IGNORECASE)
RESOURCE_HASH_RE = re.compile(r"\b(?:0x)?[0-9a-f]{10,64}\b", re.IGNORECASE)
LORA_TAG_RE = re.compile(r"<lora:([^:>]+):", re.IGNORECASE)
LABELLED_HASH_RE = re.compile(r"(?:^|[\s,;])(?:model|vae|lora|lycoris|checkpoint|hash|sha256)[^:\n]{0,24}:\s*(0x?[0-9a-f]{10,64})", re.IGNORECASE)
BRACKET_HASH_RE = re.compile(r"\[([0-9a-f]{10,64})\]", re.IGNORECASE)
UUID_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:[-_][a-z0-9._-]+)?$", re.IGNORECASE)
STORAGE_PREFIX_RE = re.compile(r"^(?:generator|images|thumbnails|uploads|output|outputs|temp|tmp)/", re.IGNORECASE)
UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[-_ ]+", re.IGNORECASE)
NUMERIC_PREFIX_RE = re.compile(r"^(?:\d{3,}[_-]){2,}")
LORA_PREFIX_RE = re.compile(r'^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9]+(?:_[0-9]+)?)_',re.IGNORECASE)

RESOURCE_HASH_KEYS = {
    "hash",
    "sha256",
    "sha256webui",
    "modelhash",
    "model_hash",
    "sshsmodelhash",
}

RESOURCE_KIND_BY_KEY = {
    "model": "checkpoint",
    "model_name": "checkpoint",
    "modelname": "checkpoint",
    "ckpt_name": "checkpoint",
    "checkpoint_name": "checkpoint",
    "checkpoint": "checkpoint",
    "unet_name": "checkpoint",
    "lora": "lora",
    "lora_name": "lora",
    "vae": "vae",
    "vae_name": "vae",
    "upscale_model": "upscaler",
    "upscale_model_name": "upscaler",
    "upscaler": "upscaler",
    "upscaler_name": "upscaler",
    "model_name_upscaler": "upscaler",
    "filename": "resource",
    "file_name": "resource",
    "filepath": "resource",
    "file_path": "resource",
    "name": "resource",
}

def clean_model(name: str) -> str:
    name = UUID_PREFIX_RE.sub("", name)
    name = NUMERIC_PREFIX_RE.sub("", name)
    name = LORA_PREFIX_RE.sub("", name)
    return name

@dataclass
class ComfyLora:
    name: str
    weight: float = 1.0


@dataclass
class ComfyResourceCandidate:
    kind: str
    value: str
    variants: list[str] = field(default_factory=list)


@dataclass
class ComfyResourceHints:
    candidates: list[ComfyResourceCandidate] = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)


@dataclass
class ComfyMetadata(Metadata):
    source = "comfy"  # type: ignore
    is_comfy: bool = False
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | str | None = None
    steps: int | None = None
    cfg: float | None = None
    checkpoint: str | None = None
    vae: str | None = None
    scheduler: str | None = None
    sampler: str | None = None
    extra_seed: int | None = None
    extra_seed_strength: float | None = None
    upscaler: str | None = None
    denoise: float | None = None
    adetailer_model: str | None = None
    adetailer_denoise: float | None = None
    loras: list[ComfyLora] = field(default_factory=list)
    resource_hints: ComfyResourceHints = field(default_factory=ComfyResourceHints)
    error: str | None = None
    raw: str | None = None
    width: int | None = None
    height: int | None = None

    def as_dict(self) -> OrderedDict[str, Any]:
        output: OrderedDict[str, Any] = OrderedDict()

        if self.prompt:
            output["Prompt"] = self.prompt
        if self.negative_prompt:
            output["Negative Prompt"] = self.negative_prompt
        if self.checkpoint:
            output["Checkpoint"] = self.checkpoint
        if self.vae:
            output["VAE"] = self.vae
        if self.seed is not None and "Seed" not in output:
            output["Seed"] = self.seed
        if self.steps is not None and "Steps" not in output:
            output["Steps"] = self.steps
        if self.cfg is not None and "Cfg" not in output:
            output["CFG"] = self.cfg
        if self.sampler and "Sampler" not in output:
            output["Sampler"] = self.sampler
        if self.scheduler:
            output["Scheduler"] = self.scheduler
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
        if self.width and self.height:
            output["Size"] = f"{self.width}x{self.height}"

        if output.get("Prompt"):
            for lora in self.loras:
                clean_name = lora.name.replace(".safetensors", "")
                tag = f"<lora:{clean_name}:{format(lora.weight, 'g')}>"
                if tag not in output["Prompt"]:
                    output["Prompt"] = f"{output['Prompt']} {tag}".strip()

        return output

    def resource_hint_strings(self) -> list[str]:
        return self.resource_hints.hashes + [cand.value for cand in self.resource_hints.candidates if RESOURCE_EXT_RE.search(cand.value)]


@dataclass
class Node:
    id: str
    node_type: str
    inputs: dict[str, Any]
    widgets: list[Any]


class ComfyResourceHintExtractor:
    @staticmethod
    def normalize_hash_token(value: str) -> str | None:
        normalized = str(value or "").strip().lower().removeprefix("0x")
        if len(normalized) < 10 or len(normalized) > 64:
            return None
        if not re.fullmatch(r"[0-9a-f]+", normalized):
            return None
        if not re.search(r"[a-f]", normalized):
            return None
        return normalized

    @staticmethod
    def normalize_name_candidate(value: str) -> str | None:
        candidate = str(value or "").strip().replace("\\", "/")
        if not candidate or len(candidate) > 300:
            return None
        if candidate.lower() in ("true", "false", "null", "undefined"):
            return None
        if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", candidate):
            return None
        return candidate

    @staticmethod
    def canonical_name(value: str) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        base = os.path.basename(normalized)
        without_ext = RESOURCE_EXT_RE.sub("", base)
        return clean_model(without_ext).strip().lower()

    @classmethod
    def name_variants(cls, value: str) -> list[str]:
        candidate = cls.normalize_name_candidate(value)
        if not candidate:
            return []

        variants: list[str] = []
        seen: set[str] = set()

        def push(raw: str) -> None:
            normalized = cls.normalize_name_candidate(raw)
            if not normalized:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            variants.append(normalized)

        normalized = candidate.replace("\\", "/")
        base = os.path.basename(normalized)
        base_no_ext = RESOURCE_EXT_RE.sub("", base)
        canonical = clean_model(base_no_ext)

        push(candidate)
        push(normalized)
        push(base)
        push(base_no_ext)
        push(canonical)

        if canonical:
            push(f"{canonical}.safetensors")
            push(f"{canonical}.ckpt")

        return variants

    @staticmethod
    def parse_json_like(value: Any) -> dict[str, Any] | list[Any] | None:
        if isinstance(value, dict):
            return value

        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                return value
            return None

        if not isinstance(value, str):
            return None

        value = value.strip()
        if not value:
            return None
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(value[start : end + 1])
                    if isinstance(parsed, (dict, list)):
                        return parsed
                except json.JSONDecodeError:
                    return None
        return None

    @classmethod
    def _add_candidate(
        cls,
        hints: ComfyResourceHints,
        seen: set[tuple[str, str]],
        kind: str,
        value: str | None,
    ) -> None:
        normalized = cls.normalize_name_candidate(value or "")
        if not normalized:
            return
        if cls._is_noise_candidate(normalized, kind):
            return
        key = (kind, normalized.lower())
        if key in seen:
            return
        seen.add(key)
        hints.candidates.append(
            ComfyResourceCandidate(
                kind=kind, value=normalized, variants=cls.name_variants(normalized)
            )
        )

    @classmethod
    def _add_hash(
        cls, hints: ComfyResourceHints, seen: set[str], value: str | None
    ) -> None:
        if not value:
            return
        normalized = cls.normalize_hash_token(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        hints.hashes.append(normalized)

    @staticmethod
    def _is_noise_candidate(value: str, kind: str) -> bool:
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            return True
        base = os.path.basename(normalized).strip()
        if not base:
            return True
        base_without_ext = RESOURCE_EXT_RE.sub("", base)
        has_extension = RESOURCE_EXT_RE.search(base) is not None
        if STORAGE_PREFIX_RE.match(normalized) and not has_extension:
            return True
        if UUID_TOKEN_RE.fullmatch(base_without_ext):
            return True
        if kind == "resource" and not has_extension:
            return True
        return False

    @classmethod
    def _kind_from_key(cls, key: str, *, default_kind: str = "resource") -> str:
        key_lower = key.lower()
        if key_lower in RESOURCE_KIND_BY_KEY:
            return RESOURCE_KIND_BY_KEY[key_lower]
        if "lora" in key_lower:
            return "lora"
        if "vae" in key_lower:
            return "vae"
        if "upscale" in key_lower:
            return "upscaler"
        if "model" in key_lower or "checkpoint" in key_lower or "ckpt" in key_lower:
            return "checkpoint"
        return default_kind

    @classmethod
    def _collect_from_unknown(
        cls,
        value: Any,
        hints: ComfyResourceHints,
        seen_names: set[tuple[str, str]],
        seen_hashes: set[str],
        *,
        default_kind: str = "resource",
        allow_bare_names: bool = False,
        depth: int = 0,
    ) -> None:
        if value is None or depth > 8:
            return

        if isinstance(value, str):
            parsed = cls.parse_json_like(value)
            if parsed is not None:
                cls._collect_from_unknown(
                    parsed,
                    hints,
                    seen_names,
                    seen_hashes,
                    default_kind=default_kind,
                    allow_bare_names=True,
                    depth=depth + 1,
                )
                return

            cls._add_hash(hints, seen_hashes, value)

            for hash_match in LABELLED_HASH_RE.findall(value):
                cls._add_hash(hints, seen_hashes, hash_match)

            for hash_match in BRACKET_HASH_RE.findall(value):
                cls._add_hash(hints, seen_hashes, hash_match)

            for lora_match in LORA_TAG_RE.findall(value):
                cls._add_candidate(hints, seen_names, "lora", lora_match)

            normalized = cls.normalize_name_candidate(value)
            if not normalized:
                return

            if allow_bare_names or RESOURCE_EXT_RE.search(normalized):
                cls._add_candidate(hints, seen_names, default_kind, normalized)
            return

        if isinstance(value, (list, tuple, set)):
            for item in value:
                cls._collect_from_unknown(
                    item,
                    hints,
                    seen_names,
                    seen_hashes,
                    default_kind=default_kind,
                    allow_bare_names=allow_bare_names,
                    depth=depth + 1,
                )
            return

        if not isinstance(value, dict):
            return

        for raw_key, nested in value.items():
            key = str(raw_key or "")
            key_lower = key.lower()
            key_kind = cls._kind_from_key(key, default_kind=default_kind)
            targeted_key = (
                key_lower in RESOURCE_KIND_BY_KEY
                or key_lower in RESOURCE_HASH_KEYS
                or any(
                    token in key_lower
                    for token in (
                        "lora",
                        "model",
                        "checkpoint",
                        "ckpt",
                        "vae",
                        "upscale",
                        "file",
                        "hash",
                    )
                )
            )

            if key_lower in RESOURCE_HASH_KEYS and isinstance(nested, str):
                cls._add_hash(hints, seen_hashes, nested)

            if isinstance(nested, str):
                normalized = cls.normalize_name_candidate(nested)
                if normalized:
                    if targeted_key and (
                        RESOURCE_EXT_RE.search(normalized)
                        or len(normalized) >= 6
                        or "/" in normalized
                        or "\\" in normalized
                    ):
                        cls._add_candidate(hints, seen_names, key_kind, normalized)

            cls._collect_from_unknown(
                nested,
                hints,
                seen_names,
                seen_hashes,
                default_kind=key_kind if targeted_key else default_kind,
                allow_bare_names=allow_bare_names or targeted_key,
                depth=depth + 1,
            )

    @classmethod
    def from_sources(
        cls,
        metadata: ComfyMetadata | None,
        raw_info: dict[str, Any] | None,
        payload: dict[str, Any] | None = None,
    ) -> ComfyResourceHints:
        hints = ComfyResourceHints()
        seen_names: set[tuple[str, str]] = set()
        seen_hashes: set[str] = set()

        if metadata:
            cls._add_candidate(hints, seen_names, "checkpoint", metadata.checkpoint)
            cls._add_candidate(hints, seen_names, "vae", metadata.vae)
            cls._add_candidate(hints, seen_names, "upscaler", metadata.upscaler)
            for lora in metadata.loras:
                cls._add_candidate(hints, seen_names, "lora", lora.name)
            if metadata.prompt:
                for lora_name in LORA_TAG_RE.findall(metadata.prompt):
                    cls._add_candidate(hints, seen_names, "lora", lora_name)

        if payload:
            model_name = payload.get("modelName")
            if isinstance(model_name, str):
                cls._add_candidate(hints, seen_names, "checkpoint", model_name)
            vae_name = payload.get("vaeName")
            if isinstance(vae_name, str):
                cls._add_candidate(hints, seen_names, "vae", vae_name)
            loras = payload.get("loras")
            if isinstance(loras, list):
                for lora in loras:
                    if isinstance(lora, dict):
                        cls._add_candidate(hints, seen_names, "lora", lora.get("name"))

        if raw_info:
            cls._collect_from_unknown(raw_info, hints, seen_names, seen_hashes)

        hints.candidates = hints.candidates[:32]
        hints.hashes = hints.hashes[:32]
        return hints


class ComfyMetadataReader:
    @classmethod
    def from_bytes(cls, b) -> ComfyMetadata:
        result = ComfyMetadata()
        try:
            image = Image.open(BytesIO(b))
            return cls.from_info(image.info, image.width, image.height)
        except Exception as error:
            result.error = f"{type(error).__name__}: {error}"
        return result

    @classmethod
    def from_info(cls, meta: dict[str, Any], width: int, height: int) -> ComfyMetadata:
        candidates = cls.extract_workflow_candidates(meta)
        if not candidates:
            result = ComfyMetadata(error="Workflow not found")
            result.resource_hints = ComfyResourceHintExtractor.from_sources(
                result, meta
            )
            return result

        merged = ComfyMetadata(is_comfy=True)
        parsed_any = False
        candidate_errors: list[str] = []

        for workflow in candidates:
            nodes = cls.normalize_nodes(workflow)
            if not nodes:
                continue
            partial = ComfyMetadata(is_comfy=True)
            try:
                cls.parse_nodes(nodes, partial)
            except Exception as error:
                candidate_errors.append(f"{type(error).__name__}: {error}")
                continue
            cls.merge_metadata(merged, partial)
            parsed_any = True

        if not parsed_any:
            error = (
                candidate_errors[0] if candidate_errors else "Workflow nodes not found"
            )
            result = ComfyMetadata(error=error)
            result.resource_hints = ComfyResourceHintExtractor.from_sources(
                result, meta
            )
            return result

        merged.is_comfy = True
        merged.resource_hints = ComfyResourceHintExtractor.from_sources(merged, meta)
        merged.raw = ", ".join(str(val) for val in meta.values())
        merged.width, merged.height = width, height
        return merged

    @classmethod
    def extract_resource_hints(
        cls,
        meta: dict[str, Any],
        *,
        payload: dict[str, Any] | None = None,
        parsed: ComfyMetadata | None = None,
    ) -> ComfyResourceHints:
        metadata = parsed or cls.from_info(meta, 0, 0)
        return ComfyResourceHintExtractor.from_sources(metadata, meta, payload)

    @staticmethod
    def extract_workflow_candidates(meta: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        def push_candidate(value: Any) -> None:
            parsed = ComfyMetadataReader.parse_json_like(value)
            if parsed is None:
                return
            signature = ComfyMetadataReader.workflow_signature(parsed)
            if signature in seen:
                return
            seen.add(signature)
            candidates.append(parsed)

        # Prefer workflow first because UI workflow usually contains resolved widget values.
        for key in ("workflow", "prompt"):
            push_candidate(meta.get(key))

        for key, value in meta.items():
            if key in ("workflow", "prompt"):
                continue
            push_candidate(value)

        return candidates

    @staticmethod
    def workflow_signature(flow: dict[str, Any]) -> str:
        try:
            return json.dumps(flow, sort_keys=True, ensure_ascii=False)
        except TypeError:
            return str(id(flow))

    @staticmethod
    def parse_json_like(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value

        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                return {"nodes": value}
            return None

        if not isinstance(value, str):
            return None

        value = value.strip()
        if not value:
            return None
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            if (
                isinstance(parsed, list)
                and parsed
                and all(isinstance(item, dict) for item in parsed)
            ):
                return {"nodes": parsed}
            return None
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(value[start : end + 1])
                    if isinstance(parsed, dict):
                        return parsed
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
                node_type = ComfyMetadataReader.as_text(
                    raw.get("type") or raw.get("class_type")
                )
                if not node_type:
                    continue
                node_id = ComfyMetadataReader.as_text(raw.get("id")) or ""
                inputs = (
                    raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {}
                )
                widgets = (
                    raw.get("widgets_values")
                    if isinstance(raw.get("widgets_values"), list)
                    else []
                )
                nodes.append(Node(node_id, node_type, inputs or {}, widgets or []))
            return nodes

        sortable_entries: list[tuple[int, str, dict[str, Any]]] = []
        for key, value in flow.items():
            if not isinstance(value, dict):
                continue
            node_type = ComfyMetadataReader.as_text(
                value.get("class_type") or value.get("type")
            )
            if not node_type:
                continue
            sort_key = int(key) if str(key).isdigit() else 10**9
            sortable_entries.append((sort_key, str(key), value))
        sortable_entries.sort(key=lambda entry: entry[0])

        nodes: list[Node] = []
        for _, key, value in sortable_entries:
            inputs = (
                value.get("inputs") if isinstance(value.get("inputs"), dict) else {}
            )
            widgets = (
                value.get("widgets_values")
                if isinstance(value.get("widgets_values"), list)
                else []
            )
            nodes.append(
                Node(
                    key,
                    str(value.get("class_type") or value.get("type")),
                    inputs or {},
                    widgets or [],
                )
            )
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
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return str(value)
        return None

    @staticmethod
    def as_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return None
            return int(float(value))
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if not value:
                return None
            try:
                numeric = float(value)
                if not math.isfinite(numeric):
                    return None
                return int(numeric)
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def as_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            if not math.isfinite(numeric):
                return None
            return numeric
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if not value:
                return None
            try:
                numeric = float(value)
                if not math.isfinite(numeric):
                    return None
                return numeric
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def first_text(*values: Any) -> str | None:
        for value in values:
            text = ComfyMetadataReader.as_text(value)
            if text:
                return text
        return None

    @staticmethod
    def first_float(*values: Any) -> float | None:
        for value in values:
            parsed = ComfyMetadataReader.as_float(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def is_useful_text_candidate(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        return any(char.isalnum() for char in stripped)

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

    @staticmethod
    def merge_metadata(target: ComfyMetadata, source: ComfyMetadata) -> None:
        fields = (
            "prompt",
            "negative_prompt",
            "seed",
            "steps",
            "cfg",
            "checkpoint",
            "vae",
            "scheduler",
            "sampler",
            "extra_seed",
            "extra_seed_strength",
            "upscaler",
            "denoise",
            "adetailer_model",
            "adetailer_denoise",
            "error",
        )
        for field_name in fields:
            if (
                getattr(target, field_name) is None
                and getattr(source, field_name) is not None
            ):
                setattr(target, field_name, getattr(source, field_name))
        for lora in source.loras:
            ComfyMetadataReader.add_lora(target, lora.name, lora.weight)
        target.is_comfy = target.is_comfy or source.is_comfy

    @classmethod
    def parse_lora_payload(cls, payload: Any) -> tuple[str, float] | None:
        if not isinstance(payload, dict):
            return None
        if payload.get("on") is False:
            return None

        name = cls.first_text(
            payload.get("lora"), payload.get("lora_name"), payload.get("name")
        )
        if not name:
            return None

        weight = cls.first_float(
            payload.get("strength_model"),
            payload.get("strength"),
            payload.get("weight"),
        )
        if weight is None:
            weight = 1.0
        return name, weight

    @classmethod
    def parse_nodes(cls, nodes: list[Node], meta: ComfyMetadata) -> None:
        text_candidates: list[tuple[str, bool]] = []

        for node in nodes:
            try:
                cls.parse_single_node(node, meta, text_candidates)
            except Exception:
                # Keep metadata extraction resilient even when one node has exotic structure.
                continue

        if not meta.prompt and text_candidates:
            non_negative = [
                text
                for text, is_neg in text_candidates
                if not is_neg and not cls.looks_negative(text)
            ]
            meta.prompt = non_negative[0] if non_negative else text_candidates[0][0]

        if not meta.negative_prompt and text_candidates:
            negatives = [
                text
                for text, is_neg in text_candidates
                if is_neg or cls.looks_negative(text)
            ]
            if negatives:
                meta.negative_prompt = negatives[0]
            elif len(text_candidates) > 1:
                meta.negative_prompt = text_candidates[1][0]

    @classmethod
    def parse_single_node(
        cls, node: Node, meta: ComfyMetadata, text_candidates: list[tuple[str, bool]]
    ) -> None:
        node_type_lower = node.node_type.lower()
        inputs = node.inputs

        cls.set_if_missing(
            meta,
            "checkpoint",
            cls.first_text(
                inputs.get("ckpt_name"),
                inputs.get("checkpoint_name"),
                inputs.get("unet_name"),
            ),
        )
        cls.set_if_missing(
            meta, "vae", cls.first_text(inputs.get("vae_name"), inputs.get("vae"))
        )
        cls.set_if_missing(
            meta,
            "scheduler",
            cls.first_text(
                inputs.get("scheduler"),
                inputs.get("scheduler_name"),
                inputs.get("schedulerName"),
            ),
        )

        if (
            "checkpoint" in node_type_lower and "upscale" not in node_type_lower
        ) or "unetloader" in node_type_lower:
            cls.set_if_missing(
                meta,
                "checkpoint",
                cls.first_text(inputs.get("model_name"), inputs.get("model")),
            )
            if node.widgets:
                cls.set_if_missing(meta, "checkpoint", cls.as_text(node.widgets[0]))

        if "vae" in node_type_lower and node.widgets:
            cls.set_if_missing(meta, "vae", cls.as_text(node.widgets[0]))

        if "scheduler" in node_type_lower and node.widgets:
            cls.set_if_missing(meta, "scheduler", cls.as_text(node.widgets[0]))

        if "upscale" in node_type_lower and "loader" in node_type_lower:
            cls.set_if_missing(
                meta,
                "upscaler",
                cls.first_text(
                    inputs.get("model_name"),
                    inputs.get("upscale_model"),
                    inputs.get("upscale_model_name"),
                ),
            )
            if node.widgets:
                cls.set_if_missing(meta, "upscaler", cls.as_text(node.widgets[0]))

        if "adetailer" in node_type_lower:
            cls.set_if_missing(
                meta, "adetailer_model", cls.as_text(inputs.get("model"))
            )
            cls.set_if_missing(
                meta, "adetailer_denoise", cls.as_float(inputs.get("denoise"))
            )

        is_text_node = (
            "textencode" in node_type_lower
            or "text encode" in node_type_lower
            or "prompt" in node_type_lower
            or "text multiline" in node_type_lower
            or "text concatenate" in node_type_lower
        )
        if is_text_node:
            text_value = cls.as_text(inputs.get("text"))
            if text_value is None and node.widgets:
                text_value = cls.as_text(node.widgets[0])
            if text_value and cls.is_useful_text_candidate(text_value):
                is_negative = "negative" in node_type_lower or "neg" in node_type_lower
                text_candidates.append((text_value, is_negative))
                if is_negative:
                    cls.set_if_missing(meta, "negative_prompt", text_value)

        if "lora" in node_type_lower:
            lora_name = cls.first_text(
                inputs.get("lora_name"), inputs.get("lora"), inputs.get("name")
            )
            if lora_name:
                weight = cls.first_float(
                    inputs.get("strength_model"),
                    inputs.get("weight"),
                    inputs.get("strength"),
                )
                cls.add_lora(meta, lora_name, 1.0 if weight is None else weight)

            for input_key, value in inputs.items():
                if LORA_INPUT_KEY_RE.match(input_key):
                    parsed_lora = cls.parse_lora_payload(value)
                    if parsed_lora is not None:
                        cls.add_lora(meta, parsed_lora[0], parsed_lora[1])

            for widget in node.widgets:
                parsed_lora = cls.parse_lora_payload(widget)
                if parsed_lora is not None:
                    cls.add_lora(meta, parsed_lora[0], parsed_lora[1])

        if "sampler" in node_type_lower:
            input_seed = cls.as_int(inputs.get("seed"))
            if input_seed is not None:
                cls.set_if_missing(meta, "seed", input_seed)
            else:
                cls.set_if_missing(meta, "seed", cls.as_text(inputs.get("seed")))

            cls.set_if_missing(meta, "steps", cls.as_int(inputs.get("steps")))
            cls.set_if_missing(meta, "cfg", cls.as_float(inputs.get("cfg")))
            cls.set_if_missing(
                meta,
                "sampler",
                cls.first_text(
                    inputs.get("sampler_name"),
                    inputs.get("sampler"),
                    inputs.get("samplerName"),
                ),
            )
            cls.set_if_missing(
                meta,
                "scheduler",
                cls.first_text(
                    inputs.get("scheduler"),
                    inputs.get("scheduler_name"),
                    inputs.get("schedulerName"),
                ),
            )

            if meta.seed is None and len(node.widgets) > 0:
                widget_seed = cls.as_int(node.widgets[0])
                if widget_seed is not None:
                    cls.set_if_missing(meta, "seed", widget_seed)
                else:
                    cls.set_if_missing(meta, "seed", cls.as_text(node.widgets[0]))
            if meta.steps is None and len(node.widgets) > 2:
                cls.set_if_missing(meta, "steps", cls.as_int(node.widgets[2]))
            if meta.cfg is None and len(node.widgets) > 3:
                cls.set_if_missing(meta, "cfg", cls.as_float(node.widgets[3]))
            if meta.sampler is None and len(node.widgets) > 4:
                cls.set_if_missing(meta, "sampler", cls.as_text(node.widgets[4]))
            if meta.scheduler is None and len(node.widgets) > 5:
                cls.set_if_missing(meta, "scheduler", cls.as_text(node.widgets[5]))

            denoise = cls.first_float(
                inputs.get("denoise"),
                node.widgets[6] if len(node.widgets) > 6 else None,
            )
            if denoise is not None:
                if meta.denoise is None:
                    if (
                        denoise < 0.999
                        or node.id == "upscale_0_sampler"
                        or "upscale" in node_type_lower
                    ):
                        meta.denoise = denoise
                elif meta.denoise >= 0.999 and denoise < 0.999:
                    meta.denoise = denoise

        if node.id == "extra_seed_extra_noise":
            cls.set_if_missing(meta, "extra_seed", cls.as_int(inputs.get("noise_seed")))
        elif node.id == "extra_seed_noised_latent_blend":
            blend = cls.as_float(inputs.get("blend_factor"))
            if blend is not None:
                strength = round(1.0 - blend, 4)
                cls.set_if_missing(meta, "extra_seed_strength", strength)
