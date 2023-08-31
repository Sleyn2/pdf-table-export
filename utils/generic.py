from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Dict, List, Union

if TYPE_CHECKING:  # pragma: nocover
    from pandas.core.frame import DataFrame


def to_list(collection: Union[Sequence[Any], "DataFrame"]) -> List[Any]:
    if isinstance(collection, list):
        return collection
    elif isinstance(collection, Sequence):
        return list(collection)
    elif hasattr(collection, "to_dict"):
        res: List[Dict[Union[str, int], Any]] = collection.to_dict(
            "records"
        )  # pragma: nocover
        return res
    else:
        return list(collection)
