import logging

from collections.abc import Iterator
from typing import Any, TypedDict

from lsprotocol.types import Position, Range
from pygls.workspace import TextDocument
from sqlfluff.core.parser import RawSegment
from sqlfluff.core.parser.segments import UnparsableSegment
from sqlfluff.core.parser.segments.base import RecordSerialisedSegment
from sqlfluff.dialects.dialect_ansi import StatementSegment
from tabulate import tabulate

logger = logging.getLogger(__file__)


def current_word_range(document: TextDocument, position: Position) -> Range | None:
    """Get the range of the word under the cursor."""
    word = document.word_at_position(position)
    word_len = len(word)
    line: str = document.lines[position.line]
    start = 0
    for _ in range(1000):  # prevent infinite hanging in case we hit edge case
        begin = line.find(word, start)
        if begin == -1:
            return None
        end = begin + word_len
        if begin <= position.character <= end:
            return Range(
                start=Position(line=position.line, character=begin),
                end=Position(line=position.line, character=end),
            )
        start = end
    return None


PositionAsDict = TypedDict("PositionAsDict", {"line": int, "character": int})
RangeAsDict = TypedDict("RangeAsDict", {"start": PositionAsDict, "end": PositionAsDict})


def get_text_in_range(document: TextDocument, text_range: Range | RangeAsDict) -> str:
    """Get document lines as string given a range."""
    doc_lines = document.lines
    if isinstance(text_range, Range):
        first_line_index, first_char_index = (
            text_range.start.line,
            text_range.start.character,
        )
        last_line_index, last_char_index = text_range.end.line, text_range.end.character
    elif isinstance(text_range, dict):  # type: ignore[reportUnnecessaryIsInstance]
        first_line_index, first_char_index = (
            text_range["start"]["line"],
            text_range["start"]["character"],
        )
        last_line_index, last_char_index = (
            text_range["end"]["line"],
            text_range["end"]["character"],
        )
    else:
        raise TypeError(
            f"`range` should either be a `Range` object or a dictionary."
            + f" found: {type(text_range)}"
        )

    if first_line_index == last_line_index:
        if first_char_index == last_char_index:
            return "\n".join(doc_lines)
        return doc_lines[first_line_index][first_char_index:last_char_index]

    lines: list[str] = []
    for i in range(first_line_index - 1, last_line_index):
        if i == first_line_index:
            lines.append(doc_lines[i][first_char_index:])
        elif i == last_line_index:
            lines.append(doc_lines[i][:last_char_index])
        elif i < len(doc_lines) - 1:
            lines.append(doc_lines[i])
    return "\n".join(lines)


def tabulate_result(rows: list[dict[str, str]]) -> str:
    """Tabulate the query results"""
    return tabulate(rows, headers="keys", showindex=True, tablefmt="psql")


def get_json_segment(
    parse_result: RecordSerialisedSegment, segment_type: str
) -> Iterator[str | dict[str, Any] | list[dict[str, Any]]]:
    """Recursively search JSON parse result for specified segment type.

    Args:
        parse_result RecordSerialisedSegment: JSON parse result from `sqlfluff.fix`.
        segment_type (str): The segment type to search for.

    Yields:
        Iterator[Union[str, Dict[str, Any], List[Dict[str, Any]]]]:
        Retrieves children of specified segment type as either a string for a raw
        segment or as JSON or an array of JSON for non-raw segments.
    """
    for k, v in parse_result.items():
        if k == segment_type:
            yield v
        elif isinstance(v, dict):
            yield from get_json_segment(v, segment_type)
        elif isinstance(v, list):
            for s in v:
                yield from get_json_segment(s, segment_type)


def get_query_statements(segments: list[RawSegment]):
    statements: list[StatementSegment] = []
    for segment in segments:
        if isinstance(segment, StatementSegment) or isinstance(
            segment, UnparsableSegment
        ):
            statements.append(segment)
    return statements


def get_current_query_statement(
    segments: list[RawSegment], cursor_position: PositionAsDict
):
    statements = get_query_statements(segments)
    for statement in statements:
        start_line, _ = statement.get_start_loc()
        end_line, _ = statement.get_end_loc()
        if start_line <= cursor_position["line"] + 1 <= end_line:
            return statement
