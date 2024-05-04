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
    segments: list[BaseSegment], pos: Position
) -> tuple[BaseSegment | None, int]:
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

    line_segments = segments[line_start_idx:line_end_idx]
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
    return line_segments[segment_idx], line_start_idx + segment_idx


def get_last_word(document: TextDocument, pos: Position):
    line = document.lines[pos.line][: pos.character]
    last_word_regex = re.compile(r"[\w`]+$", re.IGNORECASE)
    word_matches: list[str] = last_word_regex.findall(line)
    last_word = "*"
    if len(word_matches) != 0:
        last_word = word_matches[-1]

    return last_word


def _get_alias_table_name(alias: str, parsed_query: BaseSegment) -> str | None:
    from_elements = list(
        get_json_segment(
            parsed_query.as_record(show_raw=True), "from_expression_element"
        )
    )
    for element in from_elements:
        guessed_alias = element.get("alias_expression", {}).get("naked_identifier", "")
        logger.debug(
            f"guessed_alias: {guessed_alias}, alias: {alias}, {guessed_alias == alias}"
        )
        if guessed_alias == alias:
            return list(
                get_json_segment(
                    element.get("table_expression", {}), "naked_identifier"
                )
            )[-1]
    return None


def get_completion_candidates(
    document: TextDocument, pos: Position, dbconn: DBConnection
):
    keywords = dbconn.connector.help_cache
    last_word = get_last_word(document, pos)
    logger.debug(f"last_word: {last_word}")
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
    logger.info(f"Completing segment: {current_segment} at id: {segment_id}")
    logger.info(f"Parent segment: {current_segment.get_parent()[0]}")
    match current_segment.get_parent()[0]:
        case ColumnReferenceSegment():
            logger.info("Matched column segment")
            curr_seg = segments[segment_id].raw
            prev_seg = segments[segment_id - 1].raw
            if curr_seg == "." or prev_seg == ".":
                alias = segments[segment_id - 2]
                alias = (
                    segments[segment_id - 1]
                    if curr_seg == "."
                    else segments[segment_id - 2]
                )
                table_name = _get_alias_table_name(alias.raw, parsed_query)
                columns = dbconn.get_columns(table_name=table_name)
            else:
                columns = dbconn.get_columns()
                logger.info(f"Columns from db: {columns}")
            candidates.extend(
                [
                    CompletionItem(
                        label=col.name,
                        kind=CompletionItemKind.Field,
                        detail=f"{col.table_name} (column)",
                        documentation=str(col),
                        sort_text="0",
                    )
                    for col in columns
                    if re.match(match_regex, col.name)
                ]
            )
        case TableReferenceSegment():
            logger.info("Matched table reference segment")
            tables = dbconn.get_tables()
            logger.info(f"tables from db: {tables}")
            candidates.extend(
                [
                    CompletionItem(
                        label=table.name,
                        kind=CompletionItemKind.Field,
                        detail="(table)",
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
