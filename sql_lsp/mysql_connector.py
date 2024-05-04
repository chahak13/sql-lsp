import logging
from collections import defaultdict
from collections.abc import ValuesView
from copy import deepcopy
from dataclasses import dataclass
from traceback import format_exception
from typing import TypedDict

import mysql.connector

from .utils import tabulate_result

logger = logging.getLogger(__file__)


@dataclass(repr=True)
class ColumnInfo:
    """Dataclass for database table column."""

    name: str
    type: str
    default: str | None
    nullable: str
    key: str | None
    table_name: str


@dataclass(repr=True)
class TableInfo:
    """Dataclass for database table."""

    name: str
    description: str


MysqlConnectionConfig = TypedDict(
    "MysqlConnectionConfig",
    {"driver": str, "host": str, "username": str, "database": str, "password": str},
)


class MySQLConnector:
    def __init__(self, config: MysqlConnectionConfig):  # type: ignore[reportMissingSuperCall]
        """MySQL connector for the database.

        Parameters
        ----------
        config: ConnectionConfig
            Configuration required by `mysql.connector` to connect to the database.
        """
        self._config = config
        connection_args = deepcopy(config)
        connection_args.pop("driver")  # type: ignore[reportUnusedCallResult]
        self.connection = mysql.connector.connect(**connection_args)
        self.help_cache: dict[str, str] = {}
        self.table_cache: dict[str, TableInfo] = {}
        self.table_column_map: defaultdict[str, dict[str, ColumnInfo]] = defaultdict(
            dict
        )
        self.column_cache: dict[str, ColumnInfo] = {}
        self.generate_caches()

    def _get_help_documentation(self):
        """Fetch help docs for keywords."""
        with self.connection.cursor() as crsr:
            crsr.execute("select database();")
            current_database = crsr.fetchone()[0]
            topic_help_query = "use mysql;" if current_database != "mysql" else ""
            topic_help_query += "SELECT NAME, DESCRIPTION FROM help_topic;"
            crsr.execute(topic_help_query)
            for name, description in crsr:
                self.help_cache[name.lower()] = description

    def generate_caches(self):
        """Generate cache of database info.

        This fetches information from the database regarding the information
        schema which is useful in populating completion candidates. It fetches
        the following information:

        1. Fetch help documentation for all keywords.
        2. Fetch tables, columns, and their descriptions from the information schema.
        """
        self._get_help_documentation()
        self._get_schema_tables()
        self._get_all_columns()

    def _get_schema_tables(self):
        """Initialize table cache."""
        table_query = (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, "
            "COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT "
            "FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, "
            "TABLE_NAME, ORDINAL_POSITION"
        )
        logger.info(f"tables query: {table_query}")
        result, e = self.execute_query(table_query)
        logger.info(f"Schema tables: {result}")
        logger.info(f"Error: {e}")
        query_results = result if result else []
        schema_table_columns: defaultdict[
            str, defaultdict[str, list[dict[str, str]]]
        ] = defaultdict(lambda: defaultdict(list))
        for row in query_results:
            schema_table_columns[row["TABLE_SCHEMA"]][row["TABLE_NAME"]].append(
                {
                    "COLUMN_NAME": row["COLUMN_NAME"],
                    "COLUMN_TYPE": row["COLUMN_TYPE"],
                    "IS_NULLABLE": row["IS_NULLABLE"],
                    "COLUMN_KEY": row["COLUMN_KEY"],
                    "COLUMN_DEFAULT": row["COLUMN_DEFAULT"],
                }
            )
        for schema_tables in schema_table_columns.values():
            for table_name, table_columns in schema_tables.items():
                self.table_cache[table_name] = TableInfo(
                    name=table_name,
                    description=tabulate_result(table_columns),
                )

    def _get_all_columns(self):
        """Fetch all columns."""
        query = (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, "
            "COLUMN_DEFAULT, IS_NULLABLE, DATA_TYPE, COLUMN_TYPE, COLUMN_KEY "
            "FROM INFORMATION_SCHEMA.COLUMNS"
        )
        result, _ = self.execute_query(query)
        if result:
            for row in result:
                self.column_cache[row["COLUMN_NAME"]] = ColumnInfo(
                    row["COLUMN_NAME"],
                    row["COLUMN_TYPE"],
                    row["COLUMN_DEFAULT"],
                    row["IS_NULLABLE"],
                    row["COLUMN_KEY"],
                    row["TABLE_NAME"],
                )
                self.table_column_map[row["TABLE_NAME"]][
                    row["COLUMN_NAME"]
                ] = ColumnInfo(
                    row["COLUMN_NAME"],
                    row["COLUMN_TYPE"],
                    row["COLUMN_DEFAULT"],
                    row["IS_NULLABLE"],
                    row["COLUMN_KEY"],
                    row["TABLE_NAME"],
                )

    def get_help(self, function: str) -> str:
        """Return help documentation for function.

        Parameters
        ----------
        function: str
            Function name to get help for.

        Returns
        -------
        Optional[String]
            Help string from the manual if a valid function.

        """
        return self.help_cache.get(function.lower(), "")

    def get_tables(self) -> ValuesView[TableInfo]:
        """Fetch dictionary of table and their types."""
        logger.info(f"Table cache: {self.table_cache}")
        return self.table_cache.values()

    def get_columns(self, table_name: str | None = "") -> ValuesView[ColumnInfo]:
        """Fetch list of columns.

        If table name is provided and valid, columns for only that table are
        returned else if it is invalid then an empty list is returned.

        If table name is not provided, then all columns in the database are
        returned.

        Parameters
        ----------
        table_name : str
            Name of the table to get columns for.

        Returns
        -------
        ValuesView[ColumnInfo]
            A values view of ColumnInfo objects for each column present in the
        table/database.
        """
        if table_name:
            return self.table_column_map.get(table_name, {}).values()
        return self.column_cache.values()

    def execute_query(
        self, query: str
    ) -> tuple[list[dict[str, str]] | None, Exception | None]:
        """Execute the given query on the database.

        Parameters
        ----------
        query: str
            Query to execute.

        Returns
        -------
        tuple[list[dict[str, str]] | None, Exception | None]
            A tuple of (results, error). The results are a list of dictionaries
            where the keys are the columns returned by the query.
        """
        rows: list[dict[str, str]] | None = []
        error: Exception | None = None
        logger.info(f"execute_query (query): {query}")
        try:
            self.connection.reconnect()
            with self.connection.cursor(dictionary=True) as crsr:
                crsr.execute(query)
                for row in crsr:
                    rows.append(row)
        except Exception as e:
            self.connection.reconnect(attempts=2)
            logger.error(f"{''.join(format_exception(e))}")
            error = e

        return rows, error
