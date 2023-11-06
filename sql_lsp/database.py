import logging
from typing import List, Optional, Tuple

from .mysql_connector import MySQLConnector

logger = logging.getLogger(__file__)
SUPPORTED_DBS = ["mysql", "mariadb"]


class DBConnection:
    def __init__(self, config: dict):
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

    def execute_query(self, query: str) -> Tuple[Optional[List[dict]], Optional[str]]:
        logger.info(f"execute_query(query): {query}")
        return self.connector.execute_query(query)
