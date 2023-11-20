import logging
import re
from bisect import bisect_left
from operator import attrgetter
from typing import List, Optional

from lsprotocol.types import CompletionItem, CompletionItemKind, Position
from pygls.workspace import TextDocument
from sqlfluff.core import FluffConfig, Lexer, Parser
from sqlfluff.core.parser.segments.base import BaseSegment
from sqlfluff.dialects.dialect_ansi import TableReferenceSegment
from sqlfluff.dialects.dialect_mysql import ColumnReferenceSegment

from .config import fluff_config
from .database import DBConnection
from .utils import get_json_segment

logger = logging.getLogger(__file__)


def get_segment_at_point(
    segments: List[BaseSegment], pos: Position
) -> Optional[BaseSegment]:
    # Get first segment in given line
    line_start_idx = bisect_left(
        segments, pos.line + 1, key=attrgetter("pos_marker.line_no")
    )
    if not segments:
        return None, 0
    for i in range(line_start_idx, len(segments)):
        if segments[i].pos_marker.line_no != pos.line + 1:
            break
    line_end_idx = i
    # line_end_idx = i - 1 if i != len(segments) else len(segments)

    line_segments = segments[line_start_idx:line_end_idx]
    # logger.debug(f"Looking at pos: {pos}")
    # logger.debug(
    #     f"Total segments: {len(segments)}, Line start: {line_start_idx}, line end: {line_end_idx}"
    # )
    # logger.debug(f"segments: {segments}")
    # logger.debug(f"line_segments: {line_segments}")
    segment_idx = (
        bisect_left(
            line_segments,
            pos.character + 1,
            key=attrgetter("pos_marker.line_pos"),
        )
        - 1
        if len(line_segments) != 1
        else 0
    )
    # logger.debug(
    #     f"segment pos: {[(x.raw, attrgetter('pos_marker.line_pos')(x)) for x in line_segments]}"
    # )
    # logger.debug(f"segment_idx: {segment_idx}")
    return line_segments[segment_idx], segment_idx


def get_last_word(document: TextDocument, pos: Position):
    line = document.lines[pos.line][: pos.character]
    last_word_regex = re.compile(r"[\w`]+$", re.IGNORECASE)
    word_matches = last_word_regex.findall(line)
    last_word = "*"
    if len(word_matches) != 0:
        last_word = word_matches[-1]

    return last_word


def _get_alias_table_name(alias: str, parsed_query: BaseSegment) -> Optional[str]:
    from_elements = get_json_segment(parsed_query, "from_expression_elements")
    for element in from_elements:
        if element.get("alias_expression", {}).get("naked_identifier", "") == alias:
            return get_json_segment(
                element.get("table_expression", {}), "naked_identifier"
            )[-1]
    return None


def get_completion_candidates(
    document: TextDocument, pos: Position, dbconn: DBConnection
):
    keywords = dbconn.connector.help_cache
    last_word = get_last_word(document, pos)
    match_regex = re.compile(last_word, re.IGNORECASE)
    candidates = []

    text = document.source
    lexer = Lexer(config=fluff_config)
    parser = Parser(config=fluff_config)
    parsed_query = parser.parse(lexer.lex(text)[0])
    segments = parsed_query.get_raw_segments()
    current_segment, segment_id = get_segment_at_point(segments, pos)
    if not current_segment:
        return []
    logger.info(f"Completing segment: {current_segment}")
    logger.info(f"All segments: {segments}")
    match current_segment.get_parent()[0]:
        case ColumnReferenceSegment():
            if segments[segment_id - 1].raw == ".":
                alias = segments[segment_id - 2]
                table_name = _get_alias_table_name(alias, parsed_query)
                columns = dbconn.get_columns(table_name=table_name)
            else:
                columns = dbconn.get_columns()
            candidates.extend(
                [
                    CompletionItem(
                        label=col.name,
                        kind=CompletionItemKind.Field,
                        detail=col.table_name,
                        documentation=str(col),
                        sort_text="0",
                    )
                    for col in columns
                    if re.match(match_regex, col.name)
                ]
            )
        case TableReferenceSegment():
            tables = dbconn.get_tables()
            candidates.extend(
                [
                    CompletionItem(
                        label=table.name,
                        kind=CompletionItemKind.Field,
                        detail=table.type,
                        documentation=table.description,
                        sort_text="1",
                    )
                    for table in tables
                    if re.match(match_regex, table.name)
                ]
            )
        case _:
            logger.info(f"Segment type: {type(current_segment)}")

    candidate_words = [word for word in keywords if re.match(match_regex, word)]
    candidates.extend(
        CompletionItem(
            label=word,
            kind=CompletionItemKind.Keyword,
            documentation=keywords[word],
            sort_text="99",
        )
        for word in candidate_words
    )
    logger.info(f"Candidates: {candidates}")
    return candidates


if __name__ == "__main__":
    # query = "select\n name, description\n from help_keyword as hk;"
    query = "selec"
    conf = FluffConfig(
        {"core": {"dialect": "mysql"}, "indentation": {"tab_space_size": 2}}
    )
    lexer = Lexer(config=conf)
    parser = Parser(config=conf)
    parsed_query = parser.parse(lexer.lex(query)[0])
    segments = parsed_query.get_raw_segments()
    print(segments)
    # res = get_segment_at_point(segments, Position(line=2, character=8))
    # print(res)
