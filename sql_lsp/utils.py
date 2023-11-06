import logging
from typing import List, Optional, Union

from lsprotocol.types import Position, Range
from pygls.workspace import TextDocument
from tabulate import tabulate

logger = logging.getLogger(__file__)


def current_word_range(document: TextDocument, position: Position) -> Optional[Range]:
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


def get_text_in_range(document: TextDocument, text_range: Union[Range, dict]) -> str:
    """Get document lines as string given a range."""
    doc_lines = document.lines
    if isinstance(text_range, Range):
        first_line_index, first_char_index = (
            text_range.start.line,
            text_range.start.character,
        )
        last_line_index, last_char_index = text_range.end.line, text_range.end.character
    elif isinstance(text_range, dict):
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
            f" found: {type(text_range)}"
        )

    if first_line_index == last_line_index:
        if first_char_index == last_char_index:
            return "\n".join(doc_lines)
        return doc_lines[first_line_index][first_char_index:last_char_index]

    logger.debug("utils (doc_lines):")
    logger.debug(f"{doc_lines}")
    lines = []
    for i in range(first_line_index - 1, last_line_index):
        logger.debug(f"Line: {i} of {len(doc_lines) - 1}")
        if i == first_line_index:
            lines.append(doc_lines[i][first_char_index:])
        elif i == last_line_index:
            lines.append(doc_lines[i][:last_char_index])
        elif i < len(doc_lines) - 1:
            lines.append(doc_lines[i])
    return "\n".join(lines)


def tabulate_result(rows: List[dict]) -> str:
    """Tabulate the query results"""
    return tabulate(rows, headers="keys", showindex=True, tablefmt="psql")
