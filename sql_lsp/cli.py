import click

from .server import sql_server


@click.command()
@click.option("--stdio", is_flag=True, help="Start the server in STDIO mode.")
@click.option(
    "--tcp",
    is_flag=True,
    help=(
        "Start the server in TCP mode. "
        "This starts the server on 127.0.0.1 at port 9000 by default. Use "
        "`--host` and `--port` to change these defaults. "
        "NOTE: In this mode, the server should start before the client."
    ),
)
@click.option(
    "--websocket",
    is_flag=True,
    help=(
        "Start the server as a websocket connection. This is useful to expose "
        "the server to browser based editors."
    ),
)
@click.option(
    "--tcp-host",
    default="127.0.0.1",
    help="Host IP to start the TCP connection on.",
    show_default=True,
)
@click.option(
    "--ws-host",
    default="0.0.0.0",
    help="Host IP to start the websocket connection on.",
    show_default=True,
)
@click.option(
    "--port", default=9000, help="Port to start TCP or websocket connection on."
)
def main(
    stdio: bool,
    tcp: bool,
    websocket: bool,
    tcp_host: str,
    ws_host: str,
    port: int,
):
    if sum([stdio, tcp, websocket]) > 1:
        raise ValueError(
            "Only one of stdio, tcp or websocket mode can be enabled at a time."
        )
    if stdio:
        sql_server.start_io()
    elif tcp:
        sql_server.start_tcp(tcp_host, port)
    elif websocket:
        sql_server.start_ws(ws_host, port)
