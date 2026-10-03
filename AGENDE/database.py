# =========================================================
# DATABASE.PY
# One simple function that opens a MySQL connection using PyMySQL.
# Every route in app.py calls get_connection() when it needs
# to talk to the database, then closes the connection when done.
# =========================================================

import pymysql
import pymysql.cursors
import config


def get_connection():
    """Open and return a new MySQL connection.

    cursorclass=DictCursor means every row comes back as a
    dictionary, e.g. row["name"] instead of row[0].
    This makes the SQL results easy to use inside templates.
    """
    return pymysql.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )
