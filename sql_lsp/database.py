from .mysql_connector import MySQLConnector

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

    def get_help(self, function: str):
        return self.connector.get_help(function)
