# sql-lsp

A language server for SQL. This server currently supports only MySQL 
(and MariaDB) for now with plans to add more dialects in the future. This 
package is under active development and doesn't not have a stable release yet
but any use and feedback is highly appreciated!

## Installation

This package provides `sql-ls` which is a language server written with the help
of [`pygls`](https://github.com/openlawlibrary/pygls). It can be installed
directly using `pip`

``` shell
pip install sql-lsp
```

## Features and Usage

The language server can be used by starting in the `stdio` mode

``` 
Usage: sql-ls [OPTIONS]

Options:
  --stdio          Start the server in STDIO mode.
  --tcp            Start the server in TCP mode. This starts the server on
                   127.0.0.1 at port 9000 by default. Use `--host` and
                   `--port` to change these defaults. NOTE: In this mode, the
                   server should start before the client.
  --websocket      Start the server as a websocket connection. This is useful
                   to expose the server to browser based editors.
  --tcp-host TEXT  Host IP to start the TCP connection on.  [default:
                   127.0.0.1]
  --ws-host TEXT   Host IP to start the websocket connection on.  [default:
                   0.0.0.0]
  --port INTEGER   Port to start TCP or websocket connection on.
  --help           Show this message and exit.
```

The server gets the completion information by connecting to the database and
fetching the metadata regarding the tables. The database connection is
configured based on connections provided in the configuration file for the
project. The server expects `.sql-ls/config.json` at the root of the project.
An example `config.json`

``` json
{
  "connections": {
    "localhost": {
      "driver": "mariadb",
      "host": "localhost",
      "username": "username",
      "password": "password",
      "database": "mysql"
    }
  }
}
```

The connections can be switched using the `Switch Connection` code action.

`sql-ls` provides completion and query execution.

## Editor Integration

### Emacs

This server integrates well with the `eglot` language server client. Once the
server in installed, it can be configured for `sql-mode` by adding the following
configuration

``` emacs-lisp
(add-to-list 'eglot-server-programs
               '((sql-mode)
                 . ("sql-ls" "--stdio")))
```

To enable all abilities for the language server, apply the patch provided in the
repository in the file `eglot.patch` to eglot.
