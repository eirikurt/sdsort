from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from sdsort.block import FunctionBlock
    from sdsort.context import TomlTable

T = TypeVar("T", bound=int | None)


@dataclass(slots=True)
class VisibilityRanks(Generic[T]):
    """Configuration options for sorting logic based on visibility of method names on a given class.\\
        We use a TypeState pattern to avoid code duplication and ensure that the consumers of this class handle the expected state of the ranks."""

    dunder: T
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    private: T
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    protected: T
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    public: T
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

    @classmethod
    def try_from(cls, config: TomlTable) -> VisibilityRanks[int | None] | None:
        """Try to create a `VisibilityRanks` instance from a configuration dictionary.

        Args:
            config (TomlTable): A configuration dictionary, parsed from a TOML file, which may contain the needed keys for instantiation.

        Returns:
            VisibilityRanks[int | None] | None: A `VisibilityRanks` instance if the configuration is valid, otherwise `None`.
        """
        keys = ("dunder", "private", "protected", "public")
        values = tuple(config.get(k) for k in keys)
        if all(value is None for value in values):
            return None
        else:
            return VisibilityRanks(*values)

    def into_ok_or_default(self) -> VisibilityRanks[int]:
        """Transform a `VisibilityRanks[T]` into a `VisibilityRanks[int]` by replacing `None` values by a default value.\\
        The default value is the maximum of the non-`None` ranks plus one, so that any `None` rank is considered to be "after" all the other ranks."""
        ranks = (self.dunder, self.private, self.protected, self.public)
        default = max(rank for rank in ranks if rank is not None) + 1
        return VisibilityRanks[int](*(rank if rank is not None else default for rank in ranks))

    def classify_for_block(self: VisibilityRanks[int], block: FunctionBlock, name: str):
        """Classify a `FunctionBlock` according to its name and assign it the corresponding rank."""
        if name.startswith("__"):
            if name.endswith("__"):
                block.rank = self.dunder
            else:
                block.rank = self.private
        elif name.startswith("_"):
            block.rank = self.protected
        else:
            block.rank = self.public
