from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .block import FunctionBlock

    Section: TypeAlias = list[FunctionBlock]


class FnKind(StrEnum):
    DUNDER = auto()
    PRIVATE = auto()
    PROTECTED = auto()
    PUBLIC = auto()

    def name_as_key(self, name: str) -> str:
        match self:
            case self.DUNDER:
                return name.removeprefix("__").removesuffix("__")
            case self.PRIVATE:
                return name.removeprefix("__")
            case self.PROTECTED:
                return name.removeprefix("_")
            case self.PUBLIC:
                return name


@dataclass(slots=True)
class OrderingRules:
    dunder: int | None
    private: int | None
    protected: int | None
    public: int | None
    alphabetical: bool


@dataclass(slots=True)
class MethodsPartitions:
    public: Section
    """Methods without special prefixes/suffixes are considered public."""
    protected: Section
    """A method starting by "_" is considered protected."""
    dunders: Section
    """A method starting and ending by "__" is considered a dunder."""
    private: Section
    """A method starting by "__", without "__" suffix, is considered private."""
