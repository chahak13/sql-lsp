import json
import logging
import logging.config
import os
from pathlib import Path
from typing import List, Optional

import sqlfluff
from lsprotocol import validators
from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_HOVER,
    CodeAction,
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
from pygls import server
from pygls.protocol import LanguageServerProtocol, lsp_method
from pygls.workspace import TextDocument

from .completion import get_completion_candidates
from .config import fluff_config
from .database import DBConnection
from .utils import current_word_range, get_text_in_range, tabulate_result

# logging.config.dictConfig({"version": 1, "disable_existing_loggers": True})
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


class SqlLanguageServerProtocol(LanguageServerProtocol):
    @lsp_method(INITIALIZE)
    def lsp_initialize(self, params: InitializeParams):
        try:
            with open(
                Path(params.root_uri.rsplit(":")[-1]).joinpath(".sql-ls/config.json"),
                "r",
            ) as config_file:
                self.server_config = json.load(config_file)
        except FileNotFoundError:
            logger.error("Couldn't find .sql-ls/config.json, please create one.")
            self.show_message("Couldn't find .sql-ls/config.json, please create one.")
        except Exception as e:
            raise e
        self.available_connections = self.server_config["connections"]
        self.dbconn = DBConnection(config=list(self.available_connections.values())[0])
        return super().lsp_initialize(params)


class SqlLanguageServer(server.LanguageServer):
    CMD_EXPLAIN_QUERY = "explainQuery"
    CMD_EXECUTE_QUERY = "executeQuery"
    CMD_SHOW_DATABASES = "showDatabases"
    CMD_SHOW_CONNECTIONS = "showConnections"
    CMD_SHOW_CONNECTION_ALIASES = "showConnectionAliases"
    CMD_SWITCH_CONNECTIONS = "switchConnections"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


sql_server = SqlLanguageServer(
    "sql-ls", "v0.0.2", protocol_cls=SqlLanguageServerProtocol
)


def _publish_diagnostics(ls: SqlLanguageServer, uri: str):
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
            # code_description=CodeDescription(
            #     href=f"https://docs.sqlfluff.com/en/latest/rules.html#rule-{x['name']}"
            # ),
        )
        for x in lint_diagnostics
    ]
    ls.publish_diagnostics(uri, diagnostics=diagnostics)


@sql_server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls: SqlLanguageServer, params: CompletionParams):
    items = []
    document = ls.workspace.get_document(params.text_document.uri)
    items = get_completion_candidates(document, params.position, ls.lsp.dbconn)
    logger.info(f"Completion items: {items}")
    return CompletionList(is_incomplete=False, items=items)


@sql_server.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: SqlLanguageServer, params: DidOpenTextDocumentParams):
    _publish_diagnostics(ls, params.text_document.uri)


@sql_server.feature(TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: SqlLanguageServer, params: DidChangeTextDocumentParams):
    _publish_diagnostics(ls, params.text_document.uri)


@sql_server.feature(TEXT_DOCUMENT_FORMATTING)
def format_document(ls: SqlLanguageServer, params: DocumentFormattingParams):
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
        1. Explain query
        2. Execute query
        2. Show Databases
        3. Show Connections
        4. Switch Connections
    """
    document = ls.workspace.get_text_document(params.text_document.uri)
    commands: List[Command] = [
        Command(
            title="Explain Query",
            command=ls.CMD_EXPLAIN_QUERY,
            arguments=[document, params],
        ),
        Command(
            title="Execute Query",
            command=ls.CMD_EXECUTE_QUERY,
            arguments=[document, params],
        ),
        Command(title="Show Databases", command=ls.CMD_SHOW_DATABASES),
        Command(title="Show Connections", command=ls.CMD_SHOW_CONNECTIONS),
        Command(
            title="Switch Connections",
            command=ls.CMD_SWITCH_CONNECTIONS,
            arguments=[params],
        ),
    ]
    logger.info(f"Trying to send: {commands}")
    # commands = []
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
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return str(error)
    return tabulate_result(rows)


@sql_server.command(sql_server.CMD_EXPLAIN_QUERY)
def explain_query(
    ls: SqlLanguageServer, *args: tuple[TextDocument, CodeActionParams]
) -> str:
    """Execute query."""
    if not ls.lsp.dbconn:
        raise KeyError(
            "DB Connection not found on server. `SqlLanguageServer`"
            " might not have been initialzied with `SqlLanguageServerProtocol`."
            " Please check."
        )
    logger.info(f"explain_query (args): {args}")
    document_args = args[0][0]
    document = ls.workspace.get_text_document(document_args["uri"])
    action_params = args[0][1]
    query = "explain " + get_text_in_range(document, action_params["range"])
    logger.info(f"execute_query(query): {query}")
    rows, error = ls.lsp.dbconn.execute_query(query)
    if error is not None:
        return str(error)
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


@sql_server.command(sql_server.CMD_SHOW_CONNECTIONS)
def show_connections(ls: SqlLanguageServer, *args) -> str:
    """Show available connections."""
    return tabulate_result(
        [
            {"alias": alias, **conn, "password": "****"}
            for alias, conn in ls.lsp.available_connections.items()
        ]
    )


@sql_server.command(sql_server.CMD_SHOW_CONNECTION_ALIASES)
def show_connection_aliases(ls: SqlLanguageServer, *args) -> str:
    """Show aliases for all the connections.

    Useful for providing a selection list to switch connections.
    """
    return "\n".join(list(ls.lsp.available_connections.keys()))


@sql_server.command(sql_server.CMD_SWITCH_CONNECTIONS)
def switch_connections(ls: SqlLanguageServer, *args: tuple[CodeActionParams]):
    """Switch Databases in the connection."""
    selected_alias = args[0][0]
    selected_config = ls.lsp.available_connections[selected_alias]
    ls.lsp.dbconn = DBConnection(selected_config)
    ls.send_notification(f"Changed DB Connection to {selected_alias}")
