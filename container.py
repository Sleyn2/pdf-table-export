from itertools import chain
from typing import Any, Dict, List, Optional

from utils.geometry import rect_to_edges, line_to_edge, curve_to_edges

T_obj = Dict[str, Any]
T_obj_list = List[T_obj]


class Container(object):
    cached_properties = ["_rect_edges", "_curve_edges", "_edges", "_objects"]

    @property
    def pages(self) -> Optional[List[Any]]:
        ...  # pragma: nocover

    @property
    def obj(self) -> Dict[str, T_obj_list]:
        ...  # pragma: nocover

    @property
    def rectangles(self) -> T_obj_list:
        return self.obj.get("rect", [])

    @property
    def lines(self) -> T_obj_list:
        return self.obj.get("line", [])

    @property
    def curves(self) -> T_obj_list:
        return self.obj.get("curve", [])

    @property
    def chars(self) -> T_obj_list:
        return self.obj.get("char", [])

    @property
    def boxvertical(self) -> T_obj_list:
        return self.obj.get("boxvertical", [])

    @property
    def boxhorizontal(self) -> T_obj_list:
        return self.obj.get("boxhorizontal", [])

    @property
    def textvertical(self) -> T_obj_list:
        return self.obj.get("textvertical", [])

    @property
    def texthorizontal(self) -> T_obj_list:
        return self.obj.get("texthorizontal", [])

    @property
    def rect_edges(self) -> T_obj_list:
        if hasattr(self, "_rect_edges"):
            return self._rect_edges
        rect_edges_gen = (rect_to_edges(r) for r in self.rectangles)
        self._rect_edges: T_obj_list = list(chain(*rect_edges_gen))
        return self._rect_edges

    @property
    def curve_edges(self) -> T_obj_list:
        if hasattr(self, "_curve_edges"):
            return self._curve_edges
        curve_edges_gen = (curve_to_edges(r) for r in self.curves)
        self._curve_edges: T_obj_list = list(chain(*curve_edges_gen))
        return self._curve_edges

    @property
    def edges(self) -> T_obj_list:
        if hasattr(self, "_edges"):
            return self._edges
        line_edges = list(map(line_to_edge, self.lines))
        self._edges: T_obj_list = line_edges + self.rect_edges + self.curve_edges
        return self._edges

    @property
    def horizontal_edges(self) -> T_obj_list:
        def test(x: T_obj) -> bool:
            return bool(x["orientation"] == "h")

        return list(filter(test, self.edges))

    @property
    def vertical_edges(self) -> T_obj_list:
        def test(x: T_obj) -> bool:
            return bool(x["orientation"] == "v")

        return list(filter(test, self.edges))
