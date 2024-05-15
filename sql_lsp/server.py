import json
import logging
import logging.config
import os
import traceback

import sqlfluff

from pathlib import Path
from typing import override, TypedDict, ParamSpec

from lsprotocol import validators
from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_HOVER,
    CodeActionParams,
    Command,
    CompletionList,
    CompletionParams,
    Diagnostic,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DocumentFormattingParams,
    Hover,
    HoverParams,
    InitializeParams,
    Position,
    Range,
    TextEdit,
)

from sqlfluff.core import Lexer, Parser
from pygls.server import LanguageServer
from pygls.protocol import LanguageServerProtocol, lsp_method
from pygls.workspace import TextDocument

from .completion import get_completion_candidates
from .config import fluff_config
from .database import DBConnection, ConnectionConfig
from .utils import (
    current_word_range,
    get_current_query_statement,
    get_text_in_range,
    tabulate_result,
    get_query_statements,
)

P = ParamSpec("P")

sqlfluff_logger = logging.getLogger("sqlfluff")
sqlfluff_logger.setLevel(logging.WARNING)
sqlfluff_rules_logger = logging.getLogger("sqlfluff.rules.reflow")
sqlfluff_rules_logger.setLevel(logging.WARNING)

server_dir = Path(f"{os.getenv('HOME')}/.local/sql-lsp").absolute()
if not server_dir.is_dir():
    os.makedirs(server_dir, exist_ok=True)
logging.basicConfig(
    filename=server_dir.joinpath("sql-lsp-debug.log"),
    filemode="w",
    level=logging.DEBUG,
    format="[%(levelname)s - %(asctime)s] %(module)s:%(funcName)s(%(lineno)d) %(message)s",
)
logger = logging.getLogger(__file__)


ServerConnectionConfigs = TypedDict(
    "ServerConnectionConfigs", {"connections": dict[str, ConnectionConfig]}
)


class SqlLanguageServerProtocol(LanguageServerProtocol):
    available_connections: dict[str, ConnectionConfig] = {}
    dbconn: DBConnection | None = None

    @lsp_method(INITIALIZE)
    @override
    def lsp_initialize(self, params: InitializeParams):
        try:
            with open(
                Path(params.root_uri.rsplit(":")[-1]).joinpath(".sql-ls/config.json"),
                "r",
            ) as config_file:
                server_config: ServerConnectionConfigs = json.load(config_file)
        except FileNotFoundError:
            logger.error("Couldn't find .sql-ls/config.json, please create one.")
            self.show_message("Couldn't find .sql-ls/config.json, please create one.")
        except Exception as e:
            raise e
        else:
            self.available_connections = server_config["connections"]
            self.dbconn = DBConnection(
                config=list(self.available_connections.values())[0]
            )
        return super().lsp_initialize(params)


sql_server = LanguageServer("sql-ls", "v0.0.4", protocol_cls=SqlLanguageServerProtocol)


def _publish_diagnostics(ls: LanguageServer, uri: str):
    """Publish diagnostics to LSP server."""
    document = ls.workspace.get_text_document(uri)
    lint_diagnostics = sqlfluff.lint(
        document.source, dialect="mysql", config=fluff_config
    )
    logger.debug("chahak: Linting diagnostics:")
    logger.debug(f"{lint_diagnostics}")
    diagnostics: list[Diagnostic] = [
        Diagnostic(
            range=current_word_range(
                document,
                position=Position(line=x["line_no"] - 1, character=x["line_pos"] - 1),
            ),
            message=x["description"],
            code=x["code"],
        )
        for x in lint_diagnostics
    ]
    ls.publish_diagnostics(uri, diagnostics=diagnostics)


@sql_server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls: LanguageServer, params: CompletionParams):
    items = []
    document = ls.workspace.get_document(params.text_document.uri)
    items = get_completion_candidates(document, params.position, ls.lsp.dbconn)
    return CompletionList(is_incomplete=False, items=items)


@sql_server.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    _publish_diagnostics(ls, params.text_document.uri)


@sql_server.feature(TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: LanguageServer, params: DidChangeTextDocumentParams):
    _publish_diagnostics(ls, params.text_document.uri)


@sql_server.feature(TEXT_DOCUMENT_FORMATTING)
def format_document(ls: LanguageServer, params: DocumentFormattingParams):
    uri = params.text_document.uri
    document = ls.workspace.get_text_document(uri)
    formatted_doc = sqlfluff.fix(
        document.source,
        config=fluff_config,
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
async def hover(ls: LanguageServer, params: HoverParams) -> Hover | None:
    """LSP handler for textDocument/hover request."""
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = document.word_at_position(params.position)
    help_str: str = ls.lsp.dbconn.get_help(word)
    return Hover(contents=help_str)


@sql_server.feature(TEXT_DOCUMENT_CODE_ACTION)
def code_action(ls: LanguageServer, params: CodeActionParams) -> list[Command]:
    """Get code actions.

    Currently supports:
        1. Explain query
        2. Execute query
        2. Show Databases
        3. Show Connections
        4. Switch Connections
    """
    document = ls.workspace.get_text_document(params.text_document.uri)
    commands: list[Command] = [
        Command(
            title="Explain Query",
            command="explainQuery",
            arguments=[document, params],
        ),
        Command(
            title="Execute Query",
            command="executeQuery",
            arguments=[document, params],
        ),
        Command(title="Show Databases", command="showDatabases"),
        Command(title="Show Connections", command="showConnections"),
        Command(
            title="Switch Connections",
            command="switchConnections",
            arguments=[params],
        ),
        Command(
            title="Show Tables in Database", command="showTables", arguments=[params]
        ),
    ]
    return commands


# NOTE: While the type for `args` is a tuple of `TextDocument` and
# `CodeActionParams`, the actual parameters that get passed into the
# function by pygls is actually a dictionary version of the classes.
# Hence, to access the values, we use dictionary keys instead of
# class attributes.
@sql_server.command("executeQuery")
def execute_query(
    ls: LanguageServer, *args: tuple[TextDocument, CodeActionParams]
) -> str:
    """Execute query."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `LanguageServer`"
            + " might not have been initialzied with `LanguageServerProtocol`."
            + " Please check."
        )
    document_args = args[0][0]
    document = ls.workspace.get_text_document(document_args["uri"])

    lexer = Lexer(config=fluff_config)
    parser = Parser(config=fluff_config)
    parsed_query = parser.parse(lexer.lex(document.source)[0])
    segments = parsed_query.segments
    statements = get_query_statements(segments)

    action_params = args[0][1]
    cursor_position = action_params["range"]["start"]

    current_statement = get_current_query_statement(segments, cursor_position)
    if current_statement is None:
        return ""

    query = current_statement.raw
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return str(error)
    return tabulate_result(rows)


@sql_server.command("explainQuery")
def explain_query(
    ls: LanguageServer, *args: tuple[TextDocument, CodeActionParams]
) -> str:
    """Execute query."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `LanguageServer`"
            + " might not have been initialzied with `LanguageServerProtocol`."
            + " Please check."
        )
    document_args = args[0][0]
    document = ls.workspace.get_text_document(document_args["uri"])
    action_params = args[0][1]
    query = "explain " + get_text_in_range(document, action_params["range"])
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return str(error)
    return tabulate_result(rows)


@sql_server.command("showDatabases")
def show_databases(ls: LanguageServer, *args) -> str:
    """Show Databases in the connection."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `LanguageServer`"
            + " might not have been initialzied with `LanguageServerProtocol`."
            + " Please check."
        )
    query = "show databases;"
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return "".join(traceback.format_exception(e))
    return tabulate_result(rows)


@sql_server.command("showConnections")
def show_connections(ls: LanguageServer, *args) -> str:
    """Show available connections."""
    return tabulate_result(
        [
            {"alias": alias, **conn, "password": "****"}
            for alias, conn in ls.lsp.available_connections.items()
        ]
    )


@sql_server.command("showTables")
def show_databases(ls: LanguageServer, *args) -> str:
    """Show Databases in the connection."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `LanguageServer`"
            + " might not have been initialzied with `LanguageServerProtocol`."
            + " Please check."
        )
    query = "show tables;"
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return "".join(traceback.format_exception(e))
    return tabulate_result(rows)


@sql_server.command("showConnectionAliases")
def show_connection_aliases(ls: LanguageServer, *args) -> str:
    """Show aliases for all the connections.

    Useful for providing a selection list to switch connections.
    """
    return "\n".join(list(ls.lsp.available_connections.keys()))


@sql_server.command("switchConnections")
def switch_connections(ls: LanguageServer, *args: tuple[CodeActionParams]):
    """Switch Databases in the connection."""
    selected_alias = args[0][0]["connection"]
    selected_config = ls.lsp.available_connections[selected_alias]
    ls.lsp.dbconn = DBConnection(selected_config)
    ls.send_notification(f"Changed DB Connection to {selected_alias}")
    return selected_alias
