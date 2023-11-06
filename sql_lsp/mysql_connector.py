import logging
from copy import deepcopy
from typing import List, Optional, Tuple

import mysql.connector

logger = logging.getLogger(__file__)


class MySQLConnector:
    def __init__(self, config: dict):
        connection_args = deepcopy(config)
        connection_args.pop("alias")
        connection_args.pop("driver")
        self.connection = mysql.connector.connect(**connection_args)
        with self.connection.cursor() as crsr:
            crsr.execute("select database();")
            current_database = crsr.fetchone()[0]
            topic_help_query = "use mysql;" if current_database != "mysql" else ""
            topic_help_query += "select name, description from help_topic;"
            crsr.execute(topic_help_query)
            self.help_desc = {}
            for name, description in crsr:
                self.help_desc[name.lower()] = description

    def get_help(self, function: str) -> str | None:
        return self.help_desc.get(function.lower(), None)

    def execute_query(self, query: str) -> Tuple[Optional[List[dict]], Optional[str]]:
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
