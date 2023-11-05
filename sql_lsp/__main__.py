import logging

from typing import Optional, List
import sqlparse
import sqlfluff
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
    Diagnostic,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    Command,
    CodeAction,
    CodeActionContext,
)
from pygls import server
from pygls.protocol import LanguageServerProtocol, lsp_method
from pygls.workspace import TextDocument

from .utils import get_text_in_range, tabulate_result
from .database import DBConnection

logging.basicConfig(filename="sql-lsp-debug.log", filemode="w", level=logging.DEBUG)
logger = logging.getLogger(__file__)


class SqlLanguageServerProtocol(LanguageServerProtocol):
    @lsp_method(INITIALIZE)
    def lsp_initialize(self, params: InitializeParams):
        self.dbconn = DBConnection(db="mysql")
        return super().lsp_initialize(params)


class SqlLanguageServer(server.LanguageServer):
    CMD_EXECUTE_QUERY = "executeQuery"
    CMD_SHOW_DATABASES = "showDatabases"
    CMD_SHOW_CONNECTIONS = "showConnections"

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


@sql_server.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: SqlLanguageServer, params: DidOpenTextDocumentParams):
    logger.debug("Please this should trigger.....")
    _publish_diagnostics(ls, params.text_document.uri)


@sql_server.feature(TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: SqlLanguageServer, params: DidChangeTextDocumentParams):
    logger.debug("Please this should trigger.....")
    _publish_diagnostics(ls, params.text_document.uri)


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


@sql_server.feature(TEXT_DOCUMENT_CODE_ACTION)
def code_action(
    ls: SqlLanguageServer, params: CodeActionParams
) -> Optional[List[CodeAction]]:
    """Get code actions.

    Currently supports:
        1. Execute query
        2. Show Databases
        3. Show Connections
    """
    # logger.debug("Code action params:")
    # logger.debug(f"{params}")
    document = ls.workspace.get_text_document(params.text_document.uri)
    commands: List[Command] = [
        Command(
            title="Execute Query",
            command=ls.CMD_EXECUTE_QUERY,
            arguments=[document, params],
        ),
        Command(title="Show Databases", command=ls.CMD_SHOW_DATABASES),
        Command(title="Show Connections", command=ls.CMD_SHOW_CONNECTIONS),
    ]
    return commands


# NOTE: While the type for `args` is a tuple of `TextDocument` and
# `CodeActionParams`, the actual parameters that get passed into the
# function by pygls is actually a dictionary version of the classes.
# Hence, to access the values, we use dictionary keys instead of
# class attributes.
@sql_server.command(sql_server.CMD_EXECUTE_QUERY)
def execute_query(
    ls: SqlLanguageServer, *args: tuple[TextDocument, CodeActionParams]
) -> str:
    """Execute query."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `SqlLanguageServer`"
            " might not have been initialzied with `SqlLanguageServerProtocol`."
            " Please check."
        )
    logger.info(f"chahak: execute_query (args): {args}")
    document_args = args[0][0]
    document = ls.workspace.get_text_document(document_args["uri"])
    action_params = args[0][1]
    query = get_text_in_range(document, action_params["range"])
    logger.info(f"execute_query(query): {query}")
    rows = ls.lsp.dbconn.execute_query(query)
    return tabulate_result(rows)


@sql_server.command(sql_server.CMD_SHOW_DATABASES)
def show_databases(ls: SqlLanguageServer, *args) -> str:
    """Show Databases in the connection."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `SqlLanguageServer`"
            " might not have been initialzied with `SqlLanguageServerProtocol`."
            " Please check."
        )
    query = "show databases;"
    rows = ls.lsp.dbconn.execute_query(query)
    return tabulate_result(rows)


# {'line_no': 1,
#  'line_pos': 65,
#  'code': 'LT12',
#  'description': 'Files must end with a single trailing newline.',
#  'name': 'layout.end_of_file'}
def _publish_diagnostics(ls: SqlLanguageServer, uri: str):
    # logger.debug("URI IS: ", uri)
    document = ls.workspace.get_text_document(uri)
    lint_diagnostics = sqlfluff.lint(document.source, dialect="mysql")
    logger.debug("")
    # logger.debug("")
    logger.debug("Linting diagnostics:")
    logger.debug(f"{lint_diagnostics}")
    diagnostics: list[Diagnostic] = [
        Diagnostic(
            range=Range(
                start=Position(line=x["line_no"], character=x["line_pos"]),
                end=Position(line=x["line_no"], character=x["line_pos"]),
            ),
            message=x["description"],
            code=x["code"],
            code_description=x["name"],
        )
        for x in lint_diagnostics
    ]
    # logger.debug(f"DIAGNOSTICS:  {diagnostics}")
    ls.publish_diagnostics(uri, diagnostics=diagnostics)


def main():
    sql_server.start_io()
