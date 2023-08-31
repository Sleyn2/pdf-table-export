import inspect
import itertools
import re
import string
from operator import itemgetter
from typing import Any, Dict, Generator, List, Match, Optional, Pattern, Tuple, Union, Iterable

from utils.clustering import clust_obj
from utils.generic import to_list
from utils.geometry import objects_to_bbox

T_num = Union[int, float]
T_obj = Dict[str, Any]
T_obj_list = List[T_obj]
T_obj_iter = Iterable[T_obj]

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

    def search(
            self,
            pattern: Union[str, Pattern[str]],
            regex: bool = True,
            case: bool = True,
            return_groups: bool = True,
            return_chars: bool = True,
            main_group: int = 0,
    ) -> List[Dict[str, Any]]:

        if isinstance(pattern, Pattern):
            if regex is False:
                raise ValueError(
                    "Cannot pass a compiled search pattern *and* regex=False together."
                )
            if case is False:
                raise ValueError(
                    "Cannot pass a compiled search pattern *and* case=False together."
                )
            compiled = pattern
        else:
            if regex is False:
                pattern = re.escape(pattern)

            flags = re.I if case is False else 0
            compiled = re.compile(pattern, flags)

        gen = re.finditer(compiled, self.as_string)
        filtered = filter(lambda m: bool(m.group(main_group).strip()), gen)
        return [
            self.match_to_dict(
                m,
                return_groups=return_groups,
                return_chars=return_chars,
                main_group=main_group,
            )
            for m in filtered
        ]

    def extract_text_lines(
            self, strip: bool = True, return_chars: bool = True
    ) -> List[Dict[str, Any]]:
        if strip:
            pat = r" *([^\n]+?) *(\n|$)"
        else:
            pat = r"([^\n]+)"

        return self.search(
            pat, main_group=1, return_chars=return_chars, return_groups=False
        )


class WordMap:

    def __init__(self, tuples: List[Tuple[T_obj, T_obj_list]]) -> None:
        self.tuples = tuples

    def to_textmap(
            self,
            layout: bool = False,
            layout_width: T_num = 0,
            layout_height: T_num = 0,
            layout_width_chars: int = 0,
            layout_height_chars: int = 0,
            x_density: T_num = DEFAULT_X_DENSITY,
            y_density: T_num = DEFAULT_Y_DENSITY,
            x_shift: T_num = 0,
            y_shift: T_num = 0,
            y_tolerance: T_num = DEFAULT_Y_TOLERANCE,
            use_text_flow: bool = False,
            presorted: bool = False,
    ) -> TextMap:

        _textmap: List[Tuple[str, Optional[T_obj]]] = []

        if not len(self.tuples):
            return TextMap(_textmap)

        expansions = {}

        if layout:
            if layout_width_chars:
                if layout_width:
                    raise ValueError(
                        "`layout_width` and `layout_width_chars` cannot both be set."
                    )
            else:
                layout_width_chars = int(round(layout_width / x_density))

            if layout_height_chars:
                if layout_height:
                    raise ValueError(
                        "`layout_height` and `layout_height_chars` cannot both be set."
                    )
            else:
                layout_height_chars = int(round(layout_height / y_density))

            blank_line = [(" ", None)] * layout_width_chars
        else:
            blank_line = []

        num_newlines = 0

        words_sorted_doctop = (
            self.tuples
            if presorted or use_text_flow
            else sorted(self.tuples, key=lambda x: float(x[0]["doctop"]))
        )

        first_word = words_sorted_doctop[0][0]
        doctop_start = first_word["doctop"] - first_word["top"]

        for i, ws in enumerate(
                clust_obj(
                    words_sorted_doctop, lambda x: float(x[0]["doctop"]), y_tolerance
                )
        ):
            y_dist = (
                (ws[0][0]["doctop"] - (doctop_start + y_shift)) / y_density
                if layout
                else 0
            )
            num_newlines_prepend = max(
                int(i > 0),
                round(y_dist) - num_newlines,
            )

            for i in range(num_newlines_prepend):
                if not len(_textmap) or _textmap[-1][0] == "\n":
                    _textmap += blank_line
                _textmap.append(("\n", None))

            num_newlines += num_newlines_prepend

            line_len = 0

            line_words_sorted_x0 = (
                ws
                if presorted or use_text_flow
                else sorted(ws, key=lambda x: float(x[0]["x0"]))
            )

            for word, chars in line_words_sorted_x0:
                x_dist = (word["x0"] - x_shift) / x_density if layout else 0
                num_spaces_prepend = max(min(1, line_len), round(x_dist) - line_len)
                _textmap += [(" ", None)] * num_spaces_prepend
                line_len += num_spaces_prepend

                for c in chars:
                    letters = expansions.get(c["text"], c["text"])
                    for letter in letters:
                        _textmap.append((letter, c))
                        line_len += 1

            if layout:
                _textmap += [(" ", None)] * (layout_width_chars - line_len)

        if layout:
            num_newlines_append = layout_height_chars - (num_newlines + 1)
            for i in range(num_newlines_append):
                if i > 0:
                    _textmap += blank_line
                _textmap.append(("\n", None))

            if _textmap[-1] == ("\n", None):
                _textmap = _textmap[:-1]

        return TextMap(_textmap)


class WordExtractor:
    def __init__(
            self,
            x_tolerance: T_num = DEFAULT_X_TOLERANCE,
            y_tolerance: T_num = DEFAULT_Y_TOLERANCE,
            keep_blank_chars: bool = False,
            use_text_flow: bool = False,
            horizontal_ltr: bool = True,
            vertical_ttb: bool = True,
            extra_attrs: Optional[List[str]] = None,
            split_at_punctuation: Union[bool, str] = False,
    ):
        self.x_tolerance = x_tolerance
        self.y_tolerance = y_tolerance
        self.keep_blank_chars = keep_blank_chars
        self.use_text_flow = use_text_flow
        self.horizontal_ltr = horizontal_ltr
        self.vertical_ttb = vertical_ttb
        self.extra_attrs = [] if extra_attrs is None else extra_attrs

        self.split_at_punctuation = (
            string.punctuation
            if split_at_punctuation is True
            else (split_at_punctuation or "")
        )

        self.expansions = {}

    def merge_chars(self, ordered_chars: T_obj_list) -> T_obj:
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
            self, ordered_chars: T_obj_iter
    ) -> Generator[T_obj_list, None, None]:
        current_word: T_obj_list = []

        def start_next_word(
                new_char: Optional[T_obj],
        ) -> Generator[T_obj_list, None, None]:
            nonlocal current_word

            if current_word:
                yield current_word

            current_word = [] if new_char is None else [new_char]

        for char in ordered_chars:
            text = char["text"]

            if not self.keep_blank_chars and text.isspace():
                yield from start_next_word(None)

            elif text in self.split_at_punctuation:
                yield from start_next_word(char)
                yield from start_next_word(None)

            elif current_word and self.char_begins_new_word(current_word[-1], char):
                yield from start_next_word(char)

            else:
                current_word.append(char)

        if current_word:
            yield current_word

    def iter_sort_chars(self, chars: T_obj_iter) -> Generator[T_obj, None, None]:
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

    def iter_extract_tuples(
            self, chars: T_obj_iter
    ) -> Generator[Tuple[T_obj, T_obj_list], None, None]:
        ordered_chars = chars if self.use_text_flow else self.iter_sort_chars(chars)

        grouping_key = itemgetter("upright", *self.extra_attrs)
        grouped_chars = itertools.groupby(ordered_chars, grouping_key)

        for keyvals, char_group in grouped_chars:
            for word_chars in self.iter_chars_to_words(char_group):
                yield (self.merge_chars(word_chars), word_chars)

    def extract_wordmap(self, chars: T_obj_iter) -> WordMap:
        return WordMap(list(self.iter_extract_tuples(chars)))

    def extract_words(self, chars: T_obj_list) -> T_obj_list:
        return list(word for word, word_chars in self.iter_extract_tuples(chars))


TEXTMAP_KWARGS = inspect.signature(WordMap.to_textmap).parameters.keys()
WORD_EXTRACTOR_KWARGS = inspect.signature(WordExtractor).parameters.keys()


def chars_to_textmap(chars: T_obj_list, **kwargs: Any) -> TextMap:
    kwargs.update({"presorted": True})

    extractor = WordExtractor(
        **{k: kwargs[k] for k in WORD_EXTRACTOR_KWARGS if k in kwargs}
    )
    wordmap = extractor.extract_wordmap(chars)
    textmap = wordmap.to_textmap(
        **{k: kwargs[k] for k in TEXTMAP_KWARGS if k in kwargs}
    )

    return textmap


def extract_text(
        chars: T_obj_list,
        **kwargs: Any,
) -> str:
    chars = to_list(chars)
    if len(chars) == 0:
        return ""

    if kwargs.get("layout"):
        return chars_to_textmap(chars, **kwargs).as_string
    else:
        y_tolerance = kwargs.get("y_tolerance", DEFAULT_Y_TOLERANCE)
        extractor = WordExtractor(
            **{k: kwargs[k] for k in WORD_EXTRACTOR_KWARGS if k in kwargs}
        )
        words = extractor.extract_words(chars)
        lines = clust_obj(words, itemgetter("doctop"), y_tolerance)
        return "\n".join(" ".join(word["text"] for word in line) for line in lines)
