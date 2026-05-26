import re
import json
from abc import ABC, abstractmethod
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass, field

from imagescanner.constants import METADATA_REGEX, PARAM_GROUP_REGEX, PARAM_REGEX, RESOURCE_HASH_REGEX
from imagescanner.constants import WEBUI_PARAMS_BLACKLIST, STABLE_SWARM_IDENTIFIERS


def extract_json(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

def normalize_hash(value: str) -> str | None:
    if not value:
        return None
    match = RESOURCE_HASH_REGEX.search(value)
    if not match:
        return None
    token = match.group(0).lower().removeprefix("0x")
    if not re.search(r"[a-f]", token):
        return None
    return token


@dataclass
class Metadata(ABC):
    raw: str | None = None

    @property
    @abstractmethod
    def source(self) -> str:
        pass

    @abstractmethod
    def as_dict(self) -> OrderedDict[str, Any]:
        pass
    

@dataclass
class WebuiMetadata(Metadata):
    source = "webui"  # type: ignore

    def as_dict(self):
        if not self.raw:
            return {}
        match = METADATA_REGEX.match(self.raw + ",")  # extra comma for the regex
        if not match:
            return {}
        
        output_dict = OrderedDict()

        if prompt := match.group("Prompt"):
            output_dict["Prompt"] = prompt
        if negative_prompt := match.group("NegativePrompt"):
            output_dict["Negative Prompt"] = negative_prompt

        params = match.group("Params")
        params = PARAM_GROUP_REGEX.sub("", params)
        param_list = PARAM_REGEX.findall(params)
        for key, value in param_list:
            if len(output_dict) >= 25 or key in output_dict:
                continue
            if any(blacklisted in key for blacklisted in WEBUI_PARAMS_BLACKLIST):
                continue
            if len(key) > 255:
                key = key[:252] + "..."
            output_dict[key] = value

        return output_dict


@dataclass
class StableSwarmMetadata(Metadata):
    source = "stable_swarm"  # type: ignore
    is_stable_swarm: bool = False
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | str | None = None
    steps: int | None = None
    cfg: float | None = None
    model: str | None = None
    vae: str | None = None
    qwen_model: str | None = None
    scheduler: str | None = None
    sampler: str | None = None
    width: int | None = None
    height: int | None = None
    resources: list[str] = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._parse()

    def as_dict(self) -> OrderedDict[str, Any]:
        output: OrderedDict[str, Any] = OrderedDict()
        if self.prompt:
            output["Prompt"] = self.prompt
        if self.negative_prompt:
            output["Negative Prompt"] = self.negative_prompt
        if self.model:
            output["Model"] = self.model
        if self.vae:
            output["VAE"] = self.vae
        if self.qwen_model:
            output["Qwen Model"] = self.qwen_model
        if self.seed is not None:
            output["Seed"] = self.seed
        if self.steps is not None:
            output["Steps"] = self.steps
        if self.cfg is not None:
            output["CFG"] = self.cfg
        if self.sampler:
            output["Sampler"] = self.sampler
        if self.scheduler:
            output["Scheduler"] = self.scheduler
        if self.width and self.height:
            output["Size"] = f"{self.width}x{self.height}"
        return output

    def resource_hint_strings(self) -> list[str]:
        return list(set([s.strip().lower() for s in self.hashes + self.resources]))

    def _parse(self) -> None:
        if not self.raw or not any(s in self.raw for s in STABLE_SWARM_IDENTIFIERS):
            return

        data = extract_json(self.raw)
        if data is None:
            return

        params = data.get("sui_image_params")
        if not isinstance(params, dict):
            nested_params = data.get("parameters")
            if isinstance(nested_params, dict):
                params = nested_params.get("sui_image_params")
        if not isinstance(params, dict):
            params = {}

        touched = False
        self.prompt = params.get("prompt", "")
        if self.prompt:
            touched = True

        self.negative_prompt = params.get("negativeprompt") or params.get("negativePrompt") or ""
        if self.negative_prompt:
            touched = True

        self.model = params.get("model") or params.get("modelname") or ""
        self.vae = params.get("vae", "")
        self.qwen_model = params.get("qwenmodel", "")
        self.scheduler = params.get("scheduler", "")
        self.sampler = params.get("sampler") or params.get("samplerName") or params.get("samplermethod") or ""
        self.seed = params.get("seed") or params.get("seedValue") or ""
        self.steps = int(params.get("steps") or params.get("stepCount") or 0)
        self.cfg = float(params.get("cfgscale") or params.get("cfgScale") or 0.0)
        self.width = int(params.get("width", 0))
        self.height = int(params.get("height", 0))

        if any([self.model, self.vae, self.qwen_model, self.scheduler, self.sampler, self.seed, self.steps, self.cfg, self.width, self.height]):
            touched = True

        extra = data.get("sui_extra_data")
        if not self.prompt and isinstance(extra, dict):
            self.prompt = extra.get("original_prompt", "")
            if self.prompt:
                touched = True

        resources = [val for val in (self.model, self.vae, self.qwen_model) if val]
        resources.extend(params.get("loras", []))

        models = data.get("sui_models", [])
        for entry in models:
            if not isinstance(entry, dict):
                continue
            if name := entry.get("name"):
                resources.append(name)
                touched = True
                param = entry.get("param", "").lower()
                if param == "model" and not self.model:
                    self.model = name
                elif param == "vae" and not self.vae:
                    self.vae = name
                elif param == "qwenmodel" and not self.qwen_model:
                    self.qwen_model = name
            hash_token = normalize_hash(entry.get("hash", ""))
            if hash_token:
                self.hashes.append(hash_token)
                touched = True

        self.resources = list(set(resources))
        self.hashes = list(set(self.hashes))
        self.is_stable_swarm = touched
