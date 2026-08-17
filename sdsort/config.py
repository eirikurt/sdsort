from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeAlias

from .rules import Rule

if TYPE_CHECKING:
    from .context import TomlTable
    from .utils.ast import Function


Ranks: TypeAlias = dict[Rule, int]
"""A configuration mapping from enum keys to integer ranks."""


Config: TypeAlias = dict[type[Rule], Ranks]
"""A mapping from rule classes to their corresponding sub-configurations."""


MAPPING: Final[dict[str, type[Rule]]] = {rule.__name__.lower(): rule for rule in Rule.__subclasses__()}
"""Cached mapping of name -> rule for all `Rule` subclasses."""
DEFAULTS: Final[Config] = {rule: Ranks(zip(rule, range(len(rule)))) for rule in MAPPING.values()}
"""Cached default config."""


def from_table(table: TomlTable) -> Config:
    """Create active rule configurations in the configured partition order."""
    rules = (MAPPING[rule] for rule in table.get("rules-order", []))
    return Config((rule, _ranks_from_rule(table, rule)) for rule in rules)


def compute_key(config: Config, node: Function) -> tuple[int, ...]:
    return tuple(ranks[rule.from_node(node)] for rule, ranks in config.items())


def _ranks_from_rule(table: TomlTable, rule: type[Rule]) -> Ranks:
    match table.get(rule.__name__.lower()):
        case None:
            return DEFAULTS[rule]
        case sub_table:
            return _ranks_from_table(sub_table, rule)


def _ranks_from_table(table: TomlTable, rule: type[Rule]) -> Ranks:
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
