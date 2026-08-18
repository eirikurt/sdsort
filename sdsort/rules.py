from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from sdsort.utils.ast import Function


class Clause(StrEnum):
    """Base class for all rules that can be applied when sorting methods.\\
    Each rule is represented by an enum value, and the order of the values defines the default sorting order when no configuration is provided."""

    @classmethod
    @abstractmethod
    def from_node(cls, node: Function) -> Self:
        """Determine the enum variant corresponding to the given `Function` AST node."""


class Visibility(Clause):
    """Defines the visibility of a method based on its name, i.e is it intended to be public, or an implementation detail.\\
    The visibility is determined by the naming convention of the method."""

    DUNDER = auto()
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    PRIVATE = auto()
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    PROTECTED = auto()
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    PUBLIC = auto()
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

    @classmethod
    def from_node(cls, node: Function) -> Visibility:
        name = node.name
        if name.startswith("__"):
            if name.endswith("__"):
                return cls.DUNDER
            else:
                return cls.PRIVATE
        elif name.startswith("_"):
            return cls.PROTECTED
        else:
            return cls.PUBLIC
