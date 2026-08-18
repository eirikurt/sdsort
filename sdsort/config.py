from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeAlias

from .rules import Clause

if TYPE_CHECKING:
    from .context import TomlTable
    from .utils.ast import Function


Ranks: TypeAlias = dict[Clause, int]
"""A configuration mapping from enum keys to integer ranks."""


Config: TypeAlias = dict[type[Clause], Ranks]
"""A mapping from `Clause` classes to their corresponding sub-configurations."""


MAPPING: Final[dict[str, type[Clause]]] = {clause.__name__.lower(): clause for clause in Clause.__subclasses__()}
"""Cached mapping of name -> clause for all `Clause` subclasses."""
DEFAULTS: Final[Config] = {clause: Ranks(zip(clause, range(len(clause)))) for clause in MAPPING.values()}
"""Cached default config."""


def from_table(table: TomlTable) -> Config:
    """Create active clause configurations in the configured partition order."""
    clauses = (MAPPING[clause] for clause in table.get("method-order", []))
    return {clause: _ranks_from_clause(table, clause) for clause in clauses}


def compute_key(config: Config, node: Function) -> tuple[int, ...]:
    return tuple(ranks[clause.from_node(node)] for clause, ranks in config.items())


def _ranks_from_clause(table: TomlTable, clause: type[Clause]) -> Ranks:
    match table.get(clause.config_name(), []):
        case []:
            return DEFAULTS[clause]
        case order:
            default = len(clause)
            order_ranks = dict(zip(order, range(len(order))))
            return {k: order_ranks.get(k, default) for k in clause}
