from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import OrderedDict

type MapInfo = OrderedDict[str, ParamInfo]


class ParamInfo:
    pass
