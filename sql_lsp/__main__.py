import logging

import sqlparse
from lsprotocol import validators
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_HOVER,
    WORKSPACE_EXECUTE_COMMAND,
    TEXT_DOCUMENT_CODE_ACTION,
    ExecuteCommandParams,
    CompletionItem,
    CompletionList,
    CompletionParams,
    CodeActionKind,
    CodeActionOptions,
    CodeActionParams,
    DocumentFormattingParams,
    Hover,
    HoverParams,
    Position,
    Range,
    TextEdit,
    INITIALIZE,
    InitializeParams,
)
from pygls import server
from pygls.protocol import LanguageServerProtocol, lsp_method

# from utils import current_word_range
from .database import DBConnection

logging.basicConfig(filename="sql-lsp-debug.log", filemode="w", level=logging.DEBUG)
logger = logging.getLogger(__file__)


class SqlLanguageServerProtocol(LanguageServerProtocol):
    @lsp_method(INITIALIZE)
    def lsp_initialize(self, params: InitializeParams):
        self.dbconn = DBConnection(db="mysql")
        return super().lsp_initialize(params)


class SqlLanguageServer(server.LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


sql_server = SqlLanguageServer(
    "example-server", "v0.1", protocol_cls=SqlLanguageServerProtocol
)


# @sql_server.feature(TEXT_DOCUMENT_COMPLETION)
# def completions(params: CompletionParams):
#     logger.error("Does it even go here?")
#     items = []
#     document = server.workspace.get_document(params.text_document.uri)
#     current_line = document.lines[params.position.line].strip()
#     if current_line.startswith("he"):
#         items = [
#             CompletionItem(label="world"),
#             CompletionItem(label="friend"),
#         ]
#     return CompletionList(is_incomplete=False, items=items)


@sql_server.feature(TEXT_DOCUMENT_FORMATTING)
def format_document(ls: SqlLanguageServer, params: DocumentFormattingParams):
    uri = params.text_document.uri
    document = ls.workspace.get_text_document(uri)
    formatted_doc = sqlparse.format(
        document.source, reindent=True, keyword_case="upper"
    )
    return [
        TextEdit(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=validators.UINTEGER_MAX_VALUE, character=0),
            ),
            new_text=formatted_doc,
        )
    ]


@sql_server.feature(TEXT_DOCUMENT_HOVER)
async def hover(ls: SqlLanguageServer, params: HoverParams) -> Hover | None:
    """LSP handler for textDocument/hover request."""
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = document.word_at_position(params.position)
    help_str = ls.lsp.dbconn.get_help(word)
    return Hover(contents=help_str)


@sql_server.feature(
    TEXT_DOCUMENT_CODE_ACTION, CodeActionOptions(code_action_kinds=["Execute query"])
)
async def execute_query(ls: SqlLanguageServer, params: ExecuteCommandParams):
    logger.debug(str(params))
    return


def main():
    sql_server.start_io()
