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
    clauses = (MAPPING[clause] for clause in table.get("method-order", []) if clause != "name")
    return Config((clause, _ranks_from_rule(table, clause)) for clause in clauses)


def compute_key(config: Config, node: Function) -> tuple[int, ...]:
    return tuple(ranks[clause.from_node(node)] for clause, ranks in config.items())


def _ranks_from_rule(table: TomlTable, rule: type[Clause]) -> Ranks:
    name = rule.__name__.lower()
    match table.get(f"{name}-order"):
        case None | []:
            return DEFAULTS[rule]
        case order:
            default = len(rule)
            order_ranks = dict(zip(order, range(len(order))))
            return {clause: order_ranks.get(clause, default) for clause in rule}
