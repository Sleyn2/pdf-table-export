import inspect
import itertools
from operator import itemgetter
from typing import Any, Dict, Generator, List, Match, Optional, Tuple, Union, Iterable

from utils.clustering import clust_obj
from utils.generic import to_list
from utils.geometry import objects_to_bbox

T_number = Union[int, float]
T_obj = Dict[str, Any]
List_T_obj = List[T_obj]
Iterable_T_obj = Iterable[T_obj]

DEFAULT_X_TOLERANCE = 3
DEFAULT_Y_TOLERANCE = 3
DEFAULT_X_DENSITY = 7.25
DEFAULT_Y_DENSITY = 13


class TextMap:

    def __init__(self, tuples: List[Tuple[str, Optional[T_obj]]]) -> None:
        self.tuples = tuples
        self.as_string = "".join(map(itemgetter(0), tuples))

    def match_to_dict(
            self,
            m: Match[str],
            main_group: int = 0,
            return_groups: bool = True,
            return_chars: bool = True,
    ) -> Dict[str, Any]:
        subset = self.tuples[m.start(main_group): m.end(main_group)]
        chars = [c for (text, c) in subset if c is not None]
        x0, top, x1, bottom = objects_to_bbox(chars)

        result = {
            "text": m.group(main_group),
            "x0": x0,
            "top": top,
            "x1": x1,
            "bottom": bottom,
        }

        if return_groups:
            result["groups"] = m.groups()

        if return_chars:
            result["chars"] = chars

        return result


class WordExtractor:
    def __init__(
            self,
            x_tolerance: T_number = DEFAULT_X_TOLERANCE,
            y_tolerance: T_number = DEFAULT_Y_TOLERANCE,
            use_text_flow: bool = False,
            horizontal_ltr: bool = True,
            vertical_ttb: bool = True,
            extra_attrs: Optional[List[str]] = None,
    ):
        self.x_tolerance = x_tolerance
        self.y_tolerance = y_tolerance
        self.use_text_flow = use_text_flow
        self.horizontal_ltr = horizontal_ltr
        self.vertical_ttb = vertical_ttb
        self.extra_attrs = [] if extra_attrs is None else extra_attrs

        self.expansions = {}

    def merge_chars(self, ordered_chars: List_T_obj) -> T_obj:
        x0, top, x1, bottom = objects_to_bbox(ordered_chars)
        doctop_adj = ordered_chars[0]["doctop"] - ordered_chars[0]["top"]
        upright = ordered_chars[0]["upright"]

        direction = 1 if (self.horizontal_ltr if upright else self.vertical_ttb) else -1

        word = {
            "text": "".join(
                self.expansions.get(c["text"], c["text"]) for c in ordered_chars
            ),
            "x0": x0,
            "x1": x1,
            "top": top,
            "doctop": top + doctop_adj,
            "bottom": bottom,
            "upright": upright,
            "direction": direction,
        }

        for key in self.extra_attrs:
            word[key] = ordered_chars[0][key]

        return word

    def char_begins_new_word(
            self,
            prev_char: T_obj,
            curr_char: T_obj,
    ) -> bool:

        if curr_char["upright"]:
            x = self.x_tolerance
            y = self.y_tolerance
            ay = prev_char["top"]
            cy = curr_char["top"]
            if self.horizontal_ltr:
                ax = prev_char["x0"]
                bx = prev_char["x1"]
                cx = curr_char["x0"]
            else:
                ax = -prev_char["x1"]
                bx = -prev_char["x0"]
                cx = -curr_char["x1"]

        else:
            x = self.y_tolerance
            y = self.x_tolerance
            ay = prev_char["x0"]
            cy = curr_char["x0"]
            if self.vertical_ttb:
                ax = prev_char["top"]
                bx = prev_char["bottom"]
                cx = curr_char["top"]
            else:
                ax = -prev_char["bottom"]
                bx = -prev_char["top"]
                cx = -curr_char["bottom"]

        return bool(
            (cx < ax)
            or (cx > bx + x)
            or (cy > ay + y)
        )

    def iter_chars_to_words(
            self, ordered_chars: Iterable_T_obj
    ) -> Generator[List_T_obj, None, None]:
        current_word: List_T_obj = []

        def start_next_word(
                new_char: Optional[T_obj],
        ) -> Generator[List_T_obj, None, None]:
            nonlocal current_word

            if current_word:
                yield current_word

            current_word = [] if new_char is None else [new_char]

        for char in ordered_chars:
            if current_word and self.char_begins_new_word(current_word[-1], char):
                yield from start_next_word(char)

            else:
                current_word.append(char)

        if current_word:
            yield current_word

    def iter_sort_chars(self, chars: Iterable_T_obj) -> Generator[T_obj, None, None]:
        def upright_key(x: T_obj) -> int:
            return -int(x["upright"])

        for upright_cluster in clust_obj(list(chars), upright_key, 0):
            upright = upright_cluster[0]["upright"]
            cluster_key = "doctop" if upright else "x0"

            subclusters = clust_obj(
                upright_cluster, itemgetter(cluster_key), self.y_tolerance
            )

            for sc in subclusters:
                sort_key = "x0" if upright else "doctop"
                to_yield = sorted(sc, key=itemgetter(sort_key))

                if not (self.horizontal_ltr if upright else self.vertical_ttb):
                    yield from reversed(to_yield)
                else:
                    yield from to_yield

    def iterate_by_tuples(
            self, chars: Iterable_T_obj
    ) -> Generator[Tuple[T_obj, List_T_obj], None, None]:
        found_chars = chars if self.use_text_flow else self.iter_sort_chars(chars)

        key = itemgetter("upright", *self.extra_attrs)
        group_of_chars = itertools.groupby(found_chars, key)

        for keyvals, char_group in group_of_chars:
            for word_chars in self.iter_chars_to_words(char_group):
                yield self.merge_chars(word_chars), word_chars

    def get_words(self, chars: List_T_obj) -> List_T_obj:
        return list(word for word, word_chars in self.iterate_by_tuples(chars))


WORD_EXTRACTOR_KWARGS = inspect.signature(WordExtractor).parameters.keys()


def extract_text(
        chars: List_T_obj,
        **kwargs: Any,
) -> str:
    chars = to_list(chars)
    if len(chars) == 0:
        return ""

    y_tolerance = kwargs.get("y_tolerance", DEFAULT_Y_TOLERANCE)
    extractor = WordExtractor(
        **{k: kwargs[k] for k in WORD_EXTRACTOR_KWARGS if k in kwargs}
    )
    words = extractor.get_words(chars)
    lines = clust_obj(words, itemgetter("doctop"), y_tolerance)
    return "\n".join(" ".join(word["text"] for word in line) for line in lines)
