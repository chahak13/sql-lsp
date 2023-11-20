import logging
from typing import Dict, List, Optional, Tuple, ValuesView

from .mysql_connector import ColumnInfo, MySQLConnector, TableInfo

logger = logging.getLogger(__file__)
SUPPORTED_DBS = ["mysql", "mariadb"]


class DBConnection:
    def __init__(self, config: dict):
        self._config = config
        match config["driver"]:
            case "mysql":
                self.connector = MySQLConnector(config)
            case "mariadb":
                self.connector = MySQLConnector(config)
            case _:
                raise ValueError(
                    f"{config['driver']} is not supported yet."
                    f" Supported databases - {SUPPORTED_DBS}"
                )

    def get_help(self, function: str) -> str | None:
        return self.connector.get_help(function)

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
        logger.info(f"execute_query(query): {query}")
        return self.connector.execute_query(query)

    def get_tables(self) -> ValuesView[TableInfo]:
        """Fetch dictionary of table and their types."""
        return self.connector.get_tables()

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
        return self.connector.get_columns()
