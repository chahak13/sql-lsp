import logging
from collections import defaultdict
from collections.abc import ValuesView
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import mysql.connector

from .utils import tabulate_result

logger = logging.getLogger(__file__)


@dataclass(repr=True)
class ColumnInfo:
    """Dataclass for database table column."""

    name: str
    type: str
    default: Optional[str]
    nullable: str
    key: Optional[str]
    table_name: str


@dataclass(repr=True)
class TableInfo:
    """Dataclass for database table."""

    name: str
    type: str
    description: str


class MySQLConnector:
    def __init__(self, config: dict):
        self._config = config
        connection_args = deepcopy(config)
        connection_args.pop("driver")
        self.connection = mysql.connector.connect(**connection_args)
        self.help_cache = {}
        self.table_cache = {}
        self.table_column_map = defaultdict(dict)
        self.column_cache = {}
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
            f"SELECT TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"
            f" WHERE TABLE_SCHEMA='{self._config['database']}';"
        )
        result, _ = self.execute_query(table_query)
        tables = result if result else []
        for table in tables:
            result, err = self.execute_query(f"DESCRIBE {table['TABLE_NAME']};")
            self.table_cache[table["TABLE_NAME"]] = TableInfo(
                name=table["TABLE_NAME"],
                type=table["TABLE_TYPE"],
                description=tabulate_result(result),
            )
            self.help_cache[table["TABLE_NAME"]] = tabulate_result(result)

    def _get_all_columns(self):
        """Fetch all columns."""
        query = (
            "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, "
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

    def get_help(self, function: str) -> Optional[str]:
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
        return self.help_cache.get(function.lower(), None)

    def get_tables(self) -> ValuesView[TableInfo]:
        """Fetch dictionary of table and their types."""
        return self.table_cache.values()

    def get_columns(self, table_name: str = None) -> ValuesView[ColumnInfo]:
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

    def execute_query(self, query: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Execute the given query on the database.

        Parameters
        ----------
        query: String
            Query to execute.

        Returns
        -------
        Tuple[Optional[List[Dict]], Optional[String]]
            A tuple of (results, error). The results are a list of dictionaries
            where the keys are the columns returned by the query.
        """
        rows, error = [], None
        logger.info(f"execute_query (query): {query}")
        try:
            with self.connection.cursor(dictionary=True) as crsr:
                crsr.execute(query)
                for row in crsr:
                    rows.append(row)
        except Exception as e:
            self.connection.reconnect(attempts=2)
            error = e

        return rows, error
