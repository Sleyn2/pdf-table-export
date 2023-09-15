import pathlib
from io import BufferedReader, BytesIO
from types import TracebackType
from typing import Any, Dict, List, Optional, Tuple, Type, Union, Iterable

from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.psparser import PSException
from utils.pdfinternals import resolve_and_decode

from container import Container
from page import Page

# Custom types
T_num = Union[int, float]
T_point = Tuple[T_num, T_num]
T_bbox = Tuple[T_num, T_num, T_num, T_num]
T_obj = Dict[str, Any]
List_T_obj = List[T_obj]
Iter_T_obj = Iterable[T_obj]


class PDF(Container):
    cached_properties: List[str] = Container.cached_properties + ["_pages"]

    def __init__(
            self,
            stream: Union[BufferedReader, BytesIO],
            stream_is_external: bool = False,
            pages: Optional[Union[List[int], Tuple[int]]] = None,
            password: Optional[str] = None,
    ):
        self.stream = stream
        self.stream_is_external = stream_is_external
        self.pages_to_parse = pages
        self.password = password

        self.doc = PDFDocument(PDFParser(stream), password=password or "")
        self.rsrcmgr = PDFResourceManager()
        self.metadata = {}

        for info in self.doc.info:
            self.metadata.update(info)
        for k, v in self.metadata.items():
            self.metadata[k] = resolve_and_decode(v)

    @classmethod
    def open(
            cls,
            path_or_fp: Union[str, pathlib.Path, BufferedReader, BytesIO],
            pages: Optional[Union[List[int], Tuple[int]]] = None,
            password: Optional[str] = None,
    ) -> "PDF":

        stream: Union[str, pathlib.Path, BufferedReader, BytesIO]
        if isinstance(path_or_fp, (str, pathlib.Path)):
            stream = open(path_or_fp, "rb")
            stream_is_external = False
        else:
            stream = path_or_fp
            stream_is_external = True

        try:
            return cls(
                stream,
                pages=pages,
                password=password,
                stream_is_external=stream_is_external,
            )

        except PSException:
            if not stream_is_external:
                stream.close()
            raise

    def close(self) -> None:
        self.flush_cache()
        if not self.stream_is_external:
            self.stream.close()

    def __enter__(self) -> "PDF":
        return self

    def __exit__(
            self,
            t: Optional[Type[BaseException]],
            value: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> None:
        self.close()

    @property
    def pages(self) -> List[Page]:
        if hasattr(self, "_pages"):
            return self._pages

        doctop: T_num = 0
        pp = self.pages_to_parse
        self._pages: List[Page] = []
        for i, page in enumerate(PDFPage.create_pages(self.doc)):
            page_number = i + 1
            if pp is not None and page_number not in pp:
                continue
            p = Page(self, page, page_number=page_number, initial_doctop=doctop)
            self._pages.append(p)
            doctop += p.height
        return self._pages

    @property
    def obj(self) -> Dict[str, List_T_obj]:
        if hasattr(self, "_objects"):
            return self._objects
        all_objects: Dict[str, List_T_obj] = {}
        for p in self.pages:
            for kind in p.obj.keys():
                all_objects[kind] = all_objects.get(kind, []) + p.obj[kind]
        self._objects: Dict[str, List_T_obj] = all_objects
        return self._objects

    def to_dict(self, object_types: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "pages": [page.to_dict(object_types) for page in self.pages],
        }
