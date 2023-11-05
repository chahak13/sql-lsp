import logging
from typing import List
from .mysql_connector import MySQLConnector

logger = logging.getLogger(__file__)
SUPPORTED_DBS = ["mysql", "mariadb"]


class DBConnection:
    def __init__(self, db="mysql"):
        match db:
            case "mysql":
                self.connector = MySQLConnector()
            case _:
                raise ValueError(
                    f"{db} is not supported yet. Supported databases - {SUPPORTED_DBS}"
                )

    def get_help(self, function: str) -> str | None:
        return self.connector.get_help(function)

    def execute_query(self, query: str) -> List[dict]:
        logger.info(f"execute_query(query): {query}")
        return self.connector.execute_query(query)
