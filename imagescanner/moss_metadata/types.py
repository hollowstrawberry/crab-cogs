"""Structural interfaces shared verbatim by both independently installed cogs."""

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

Box = tuple[float, float, float, float]


class Metadata(Protocol):
    def as_dict(self) -> Mapping[str, object]: ...


@runtime_checkable
class MossMetadata(Metadata, Protocol):
    @property
    def moss_prompt(self) -> str | None: ...

    @property
    def is_comfy(self) -> bool: ...


class MossRegion(Protocol):
    @property
    def label(self) -> str: ...
    @property
    def caption(self) -> str: ...
    @property
    def text(self) -> str | None: ...
    @property
    def bbox(self) -> Box | None: ...
    @property
    def normalized(self) -> Box | None: ...


class MossLayout(Protocol):
    @property
    def scene(self) -> str: ...
    @property
    def regions(self) -> Sequence[MossRegion]: ...
    @property
    def meta(self) -> Sequence[str]: ...
    @property
    def suffix(self) -> str: ...
    @property
    def warnings(self) -> Sequence[str]: ...
