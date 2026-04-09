import re
from abc import ABC, abstractmethod
from typing import Any
from collections import OrderedDict
from dataclasses import dataclass

from imagescanner.constants import METADATA_REGEX, PARAM_GROUP_REGEX, PARAM_REGEX, WEBUI_PARAMS_BLACKLIST


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
