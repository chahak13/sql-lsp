from typing import Optional

from lsprotocol.types import Position, Range
from pygls.workspace import TextDocument


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
