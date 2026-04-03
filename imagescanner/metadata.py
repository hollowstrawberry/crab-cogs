import re
from abc import ABC, abstractmethod
from typing import Any, Literal
from collections import OrderedDict
from dataclasses import dataclass

METADATA_REGEX = re.compile(r"(?:(?P<Prompt>[\S\s]+?)\n)?(?:Negative prompt: ?(?P<NegativePrompt>[\S\s]*)\n)?(?P<Params>[^\n:]+: .+)", re.IGNORECASE)
LOOKAHEAD_PATTERN = r'(?=(?:[^"]*"[^"]*")*[^"]*$)'  # ensures the characters surrounding the lookahead are not inside quotes
PARAM_REGEX = re.compile(rf" ?([^:]+): (.+?),{LOOKAHEAD_PATTERN}")
PARAM_GROUP_REGEX = re.compile(rf", [^:]+: {{.+?{LOOKAHEAD_PATTERN}}}")

PARAMS_BLACKLIST = [
    "Template", "Version", "Hires prompt", "Hires negative",
    "ADetailer mask", "ADetailer dilate", "ADetailer prompt", "ADetailer use", "ADetailer checkpoint", "ADetailer sampler", "ADetailer scheduler",
    "ADetailer inpaint", "ADetailer min", "ADetailer method", "ADetailer hires",
    "RP Divide", "RP Ma", "RP Prompt", "RP Calc", "RP Ratio", "RP Base", "RP Use", "RP LoRA", "RP Options", "RP Flip", "RP threshold",
    "FreeU Stages", "FreeU Schedule",
    "Mimic", "Separate Feature Channels", "Scaling Startpoint", "Variability Measure",  # Dynamic thresholding
    "Interpolate Phi", "Threshold percentile",
]


@dataclass
class Metadata(ABC):
    raw: str | None = None

    @property
    @abstractmethod
    def source(self):
        pass

    @abstractmethod
    def as_dict(self) -> OrderedDict[str, Any]:
        pass
    

@dataclass
class WebuiMetadata(Metadata):
    source = "webui"

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
            if any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                continue
            if len(key) > 255:
                key = key[:252] + "..."
            output_dict[key] = value

        return output_dict
