import re
from bisect import bisect_left
from operator import attrgetter
from typing import TYPE_CHECKING, List, Dict

from lsprotocol.types import Position, CompletionItem
from pygls.workspace import TextDocument
from sqlfluff.core import FluffConfig, Lexer, Parser
from sqlfluff.core.parser.segments.base import BaseSegment


def get_segment_at_point(segments: List[BaseSegment], pos: Position):
    # Get first segment in given line
    line_start_idx = bisect_left(
        segments, pos.line, key=attrgetter("pos_marker.line_no")
    )
    for i in range(line_start_idx, len(segments) + 1):
        if segments[i].pos_marker.line_no != pos.line:
            break
    line_end_idx = i - 1 if i != len(segments) else len(segments)

    line_segments = segments[line_start_idx : line_end_idx + 1]
    segment_idx = bisect_left(
        line_segments,
        pos.character,
        key=attrgetter("pos_marker.line_pos"),
    )
    return line_segments[segment_idx]


def get_last_word(document: TextDocument, pos: Position):
    line = document.lines[pos.line][: pos.character]
    last_word_regex = re.compile(r"[\w`]+$", re.IGNORECASE)
    word_matches = last_word_regex.findall(line)
    last_word = ""
    if len(word_matches) != 0:
        last_word = word_matches[-1]

    return last_word


def get_completion_candidates(document: TextDocument, pos: Position, keywords: Dict):
    last_word = get_last_word(document, pos)
    match_regex = re.compile(last_word, re.IGNORECASE)
    candidate_words = [word for word in keywords if re.match(match_regex, word)]
    candidates = [
        CompletionItem(label=word, documentation=keywords[word])
        for word in candidate_words
    ]
    return candidates


if __name__ == "__main__":
    query = "select\n name, description\n from help_keyword as hk;"
    conf = FluffConfig(
        {"core": {"dialect": "mysql"}, "indentation": {"tab_space_size": 2}}
    )
    lexer = Lexer(config=conf)
    parser = Parser(config=conf)
    parsed_query = parser.parse(lexer.lex(query)[0])
    segments = parsed_query.get_raw_segments()
    res = get_segment_at_point(segments, Position(line=2, character=8))
    print(res)
