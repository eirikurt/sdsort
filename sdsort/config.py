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
    return Config((clause, _ranks_from_rule(table, clause)) for clause in clauses)


def compute_key(config: Config, node: Function) -> tuple[int, ...]:
    return tuple(ranks[clause.from_node(node)] for clause, ranks in config.items())


def _ranks_from_rule(table: TomlTable, rule: type[Clause]) -> Ranks:
    match table.get(rule.__name__.lower()):
        case None:
            return DEFAULTS[rule]
        case sub_table:
            return _ranks_from_table(sub_table, rule)


def _ranks_from_table(table: TomlTable, rule: type[Clause]) -> Ranks:
    default = len(rule)
    ranks: Ranks = {}
    any_ok = False
    for k, v in zip(rule, (table.get(k) for k in rule)):
        match v:
            case None:
                ranks[k] = default
            case _ if v > default:
                msg = f"A rank can't be higher than {rule.__name__} number of options. Expected max rank of {default}, got {v}"
                raise ValueError(msg)
            case _:
                any_ok = True
                ranks[k] = v
    if any_ok:
        return ranks
    else:
        return DEFAULTS[rule]
