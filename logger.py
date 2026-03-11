import logging
import sqlite3
import os
import datetime

DB_PATH = "uptime_monitor.db"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")


# -- SETUP LOG DIRECTORY --
def setup_log_dir():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


# -- SETUP DATABASE LOG TABLE --
def setup_log_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            level       TEXT,
            source      TEXT,
            message     TEXT,
            logged_at   TEXT
        )
    """)
    conn.commit()
    conn.close()


# -- CUSTOM DATABASE HANDLER --
class DatabaseHandler(logging.Handler):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def emit(self, record):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT INTO logs (level, source, message, logged_at)
                VALUES (?, ?, ?, ?)
            """, (
                record.levelname,
                self.source,
                self.format(record),
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass


# -- GET LOGGER --
def get_logger(source):
    setup_log_dir()
    setup_log_table()

    logger = logging.getLogger(source)

    # Avoid duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # -- FORMAT --
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # -- HANDLER 1: Write to log file --
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # -- HANDLER 2: Print to terminal --
    terminal_handler = logging.StreamHandler()
    terminal_handler.setLevel(logging.WARNING)
    terminal_handler.setFormatter(formatter)

    # -- HANDLER 3: Write to database --
    db_handler = DatabaseHandler(source)
    db_handler.setLevel(logging.DEBUG)
    db_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(terminal_handler)
    logger.addHandler(db_handler)

    return logger