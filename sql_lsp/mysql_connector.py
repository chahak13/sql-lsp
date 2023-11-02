import mysql.connector


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

    def get_help(self, function: str):
        return self.help_desc.get(function.lower(), None)
