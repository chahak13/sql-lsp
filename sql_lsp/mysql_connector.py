import logging
import mysql.connector

from typing import List

logger = logging.getLogger(__file__)


class MySQLConnector:
    def __init__(self):
        self.connection = mysql.connector.connect(
            user="chahak", password="CPM", host="127.0.0.1", database="mysql"
        )
        with self.connection.cursor() as crsr:
            topic_help_query = "select name, description from help_topic"
            crsr.execute(topic_help_query)
            self.help_desc = {}
            for name, description in crsr:
                self.help_desc[name.lower()] = description

    def get_help(self, function: str) -> str | None:
        return self.help_desc.get(function.lower(), None)

    def execute_query(self, query: str) -> List[dict]:
        rows = []
        logger.info(f"execute_query (query): {query}")
        with self.connection.cursor(dictionary=True) as crsr:
            crsr.execute(query)
            for row in crsr:
                rows.append(row)
        return rows
