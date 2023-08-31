from typing import Any, List, Optional, Union

from pdfminer.pdftypes import PDFObjRef
from pdfminer.psparser import PSLiteral


def resolve_and_decode(obj: Any) -> Any:
    if hasattr(obj, "resolve"):
        obj = obj.resolve()
    if isinstance(obj, list):
        return list(map(resolve_and_decode, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            obj[k] = resolve_and_decode(v)
        return obj

    return obj


def resolve(x: Any) -> Any:
    if isinstance(x, PDFObjRef):
        return x.resolve()
    else:
        return x


def get_dict_type(d: Any) -> Optional[str]:
    if not isinstance(d, dict):
        return None
    t = d.get("Type")
    return t


def resolve_all(x: Any) -> Any:

    if isinstance(x, PDFObjRef):
        resolved = x.resolve()

        # Avoid infinite recursion
        if get_dict_type(resolved) == "Page":
            return x

        return resolve_all(resolved)
    elif isinstance(x, (list, tuple)):
        return type(x)(resolve_all(v) for v in x)
    elif isinstance(x, dict):
        exceptions = ["Parent"] if get_dict_type(x) == "Annot" else []
        return {k: v if k in exceptions else resolve_all(v) for k, v in x.items()}
    else:
        return x
