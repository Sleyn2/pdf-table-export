import re
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import (
    LTChar,
    LTComponent,
    LTContainer,
    LTItem,
    LTPage,
    LTTextContainer,
)
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfpage import PDFPage

import utils
from container import Container
from table import T_table_settings, Table, TableFinder, TableSettings
from utils.pdfinternals import resolve_all, resolve_and_decode
from utils.text import TextMap

T_num = Union[int, float]
T_bbox = Tuple[T_num, T_num, T_num, T_num]
T_obj = Dict[str, Any]
List_T_obj = List[T_obj]

lt_pat = re.compile(r"^LT")

ALL_ATTRS = set(
    [
        "adv",
        "height",
        "linewidth",
        "pts",
        "size",
        "srcsize",
        "width",
        "x0",
        "x1",
        "y0",
        "y1",
        "bits",
        "matrix",
        "upright",
        "text",
        "imagemask",
        "colorspace",
        "evenodd",
        "fill",
        "path",
        "stream",
        "stroke",
    ]
)


class Page(Container):
    cached_properties: List[str] = Container.cached_properties + ["_layout"]
    is_original: bool = True
    pages = None

    def __init__(
            self,
            pdf: "PDF",
            page_obj: PDFPage,
            page_number: int,
            initial_doctop: T_num = 0,
    ):
        self.pdf = pdf
        self.root_page = self
        self.page_obj = page_obj
        self.page_number = page_number
        _rotation = resolve_all(self.page_obj.attrs.get("Rotate", 0)) or 0
        self.rotation = _rotation % 360
        self.page_obj.rotate = self.rotation
        self.initial_doctop = initial_doctop

        cropbox = page_obj.attrs.get("CropBox")
        mediabox = page_obj.attrs.get("MediaBox")

        self.cropbox = resolve_all(cropbox) if cropbox is not None else None
        self.mediabox = resolve_all(mediabox) or self.cropbox
        m = self.mediabox

        self.bbox: T_bbox = (
            (
                min(m[1], m[3]),
                min(m[0], m[2]),
                max(m[1], m[3]),
                max(m[0], m[2]),
            )
            if self.rotation in [90, 270]
            else (
                min(m[0], m[2]),
                min(m[1], m[3]),
                max(m[0], m[2]),
                max(m[1], m[3]),
            )
        )
        self.get_textmap = lru_cache()(self.get_textmap)

    @property
    def width(self) -> T_num:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> T_num:
        return self.bbox[3] - self.bbox[1]

    @property
    def layout(self) -> LTPage:
        if hasattr(self, "_layout"):
            return self._layout
        device = PDFPageAggregator(
            self.pdf.rsrcmgr,
            pageno=self.page_number,
        )
        interpreter = PDFPageInterpreter(self.pdf.rsrcmgr, device)
        interpreter.process_page(self.page_obj)
        self._layout: LTPage = device.get_result()
        return self._layout

    @property
    def obj(self) -> Dict[str, List_T_obj]:
        if hasattr(self, "_objects"):
            return self._objects
        self._objects: Dict[str, List_T_obj] = self.parse_objects()
        return self._objects

    def point2coord(self, pt: Tuple[T_num, T_num]) -> Tuple[T_num, T_num]:
        return pt[0], self.height - pt[1]

    def process_object(self, obj: LTItem) -> T_obj:
        kind = re.sub(lt_pat, "", obj.__class__.__name__).lower()

        def process_attr(item: Tuple[str, Any]) -> Optional[Tuple[str, Any]]:
            k, v = item
            if k in ALL_ATTRS:
                res = resolve_all(v)
                return k, res
            else:
                return None

        attr = dict(filter(None, map(process_attr, obj.__dict__.items())))

        attr["object_type"] = kind
        attr["page_number"] = self.page_number

        for cs in ["ncs", "scs"]:
            if hasattr(obj, cs):
                attr[cs] = resolve_and_decode(getattr(obj, cs).name)

        if isinstance(obj, (LTChar, LTTextContainer)):
            attr["text"] = obj.get_text()

        if "pts" in attr:
            attr["pts"] = list(map(self.point2coord, attr["pts"]))

        if "y0" in attr:
            attr["top"] = self.height - attr["y1"]
            attr["bottom"] = self.height - attr["y0"]
            attr["doctop"] = self.initial_doctop + attr["top"]

        return attr

    def iter_layout_objects(
            self, layout_objects: List[LTComponent]
    ) -> Generator[T_obj, None, None]:
        for obj in layout_objects:
            if isinstance(obj, LTContainer):
                if self.pdf.laparams is not None:
                    yield self.process_object(obj)
                yield from self.iter_layout_objects(obj.objs)
            else:
                yield self.process_object(obj)

    def parse_objects(self) -> Dict[str, List_T_obj]:
        objects: Dict[str, List_T_obj] = {}
        for obj in self.iter_layout_objects(self.layout.objs):
            kind = obj["object_type"]
            if kind in ["anno"]:
                continue
            if objects.get(kind) is None:
                objects[kind] = []
            objects[kind].append(obj)
        return objects

    def find_tables(
            self, table_settings: Optional[T_table_settings] = None
    ) -> List[Table]:
        tset = TableSettings.resolve(table_settings)
        return TableFinder(self, tset).tables

    def find_table(
            self, table_settings: Optional[T_table_settings] = None
    ) -> Optional[Table]:
        tset = TableSettings.resolve(table_settings)
        tables = self.find_tables(tset)

        if len(tables) == 0:
            return None

        # Return the largest table, as measured by number of cells.
        def sorter(x: Table) -> Tuple[int, T_num, T_num]:
            return -len(x.cells), x.bbox[1], x.bbox[0]

        largest = list(sorted(tables, key=sorter))[0]

        return largest

    def extract_table(
            self, table_settings: Optional[T_table_settings] = None
    ) -> Optional[List[List[Optional[str]]]]:
        tset = TableSettings.resolve(table_settings)
        table = self.find_table(tset)
        if table is None:
            return None
        else:
            return table.extract(**(tset.text_settings or {}))

    def get_textmap(self, **kwargs: Any) -> TextMap:
        defaults = dict(x_shift=self.bbox[0], y_shift=self.bbox[1])
        if "layout_width_chars" not in kwargs:
            defaults.update({"layout_width": self.width})
        if "layout_height_chars" not in kwargs:
            defaults.update({"layout_height": self.height})
        full_kwargs: Dict[str, Any] = {**defaults, **kwargs}
        return utils.chars_to_textmap(self.chars, **full_kwargs)

    def extract_text(self, **kwargs: Any) -> str:
        return self.get_textmap(**kwargs).as_string

    def extract_text_simple(self, **kwargs: Any) -> str:
        return utils.extract_text_simple(self.chars, **kwargs)

    def extract_words(self, **kwargs: Any) -> List_T_obj:
        return utils.text.extract_words(self.chars, **kwargs)

    def extract_text_lines(
            self, strip: bool = True, return_chars: bool = True, **kwargs: Any
    ) -> List_T_obj:
        return self.get_textmap(**kwargs).get_lines_txt(
            strip=strip, return_chars=return_chars
        )

    def crop(
            self, bbox: T_bbox, relative: bool = False, strict: bool = True
    ) -> "CroppedPage":
        return CroppedPage(self, bbox, relative=relative, strict=strict)

    def to_dict(self, object_types: Optional[List[str]] = None) -> Dict[str, Any]:
        if object_types is None:
            _object_types = list(self.obj.keys()) + ["annot"]
        else:
            _object_types = object_types
        d = {
            "page_number": self.page_number,
            "initial_doctop": self.initial_doctop,
            "rotation": self.rotation,
            "cropbox": self.cropbox,
            "mediabox": self.mediabox,
            "bbox": self.bbox,
            "width": self.width,
            "height": self.height,
        }
        for t in _object_types:
            d[t + "s"] = getattr(self, t + "s")
        return d

    def __repr__(self) -> str:
        return f"<Page:{self.page_number}>"


class DerivedPage(Page):
    is_original: bool = False

    def __init__(self, parent_page: Page):
        self.parent_page = parent_page
        self.root_page = parent_page.root_page
        self.pdf = parent_page.pdf
        self.page_obj = parent_page.page_obj
        self.page_number = parent_page.page_number
        self.flush_cache(Container.cached_properties)
        self.get_textmap = lru_cache()(self.get_textmap)


def test_proposed_bbox(bbox: T_bbox, parent_bbox: T_bbox) -> None:
    bbox_area = utils.calculate_area(bbox)
    if bbox_area == 0:
        raise ValueError(f"Bounding box {bbox} has an area of zero.")

    overlap = utils.get_bbox_overlap(bbox, parent_bbox)
    if overlap is None:
        raise ValueError(
            f"Bounding box {bbox} is entirely outside "
            f"parent page bounding box {parent_bbox}"
        )

    overlap_area = utils.calculate_area(overlap)
    if overlap_area < bbox_area:
        raise ValueError(
            f"Bounding box {bbox} is not fully within "
            f"parent page bounding box {parent_bbox}"
        )


class CroppedPage(DerivedPage):
    def __init__(
            self,
            parent_page: Page,
            crop_bbox: T_bbox,
            crop_fn: Callable[[List_T_obj, T_bbox], List_T_obj] = utils.geometry.crop_to_bbox,
            relative: bool = False,
            strict: bool = True,
    ):
        if relative:
            o_x0, o_top, _, _ = parent_page.bbox
            x0, top, x1, bottom = crop_bbox
            crop_bbox = (x0 + o_x0, top + o_top, x1 + o_x0, bottom + o_top)

        if strict:
            test_proposed_bbox(crop_bbox, parent_page.bbox)

        def _crop_fn(objs: List_T_obj) -> List_T_obj:
            return crop_fn(objs, crop_bbox)

        super().__init__(parent_page)

        self._crop_fn = _crop_fn

        # Note: testing for original function passed, not _crop_fn
        if crop_fn is utils.outside_bbox:
            self.bbox = parent_page.bbox
        else:
            self.bbox = crop_bbox

    @property
    def obj(self) -> Dict[str, List_T_obj]:
        if hasattr(self, "_objects"):
            return self._objects
        self._objects: Dict[str, List_T_obj] = {
            k: self._crop_fn(v) for k, v in self.parent_page.obj.items()
        }
        return self._objects


class FilteredPage(DerivedPage):
    def __init__(self, parent_page: Page, filter_fn: Callable[[T_obj], bool]):
        self.bbox = parent_page.bbox
        self.filter_fn = filter_fn
        super().__init__(parent_page)

    @property
    def obj(self) -> Dict[str, List_T_obj]:
        if hasattr(self, "_objects"):
            return self._objects
        self._objects: Dict[str, List_T_obj] = {
            k: list(filter(self.filter_fn, v))
            for k, v in self.parent_page.obj.items()
        }
        return self._objects
