import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def get_mysql_url(user=None, password=None, host=None, port=None, db=None, charset="utf8mb4"):
    user = user or os.environ.get("MYSQL_USER", "root")
    password = password or os.environ.get("MYSQL_PASSWORD", "")
    host = host or os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = port or os.environ.get("MYSQL_PORT", "3306")
    db = db or os.environ.get("MYSQL_DATABASE", "knowlion")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset={charset}"


def create_engine_and_session(mysql_url: str = None, echo: bool = False):
    """Create SQLAlchemy engine and sessionmaker.

    Returns (engine, Session) where Session is a scoped session factory.
    """
    if mysql_url is None:
        mysql_url = get_mysql_url()
    engine = create_engine(mysql_url, echo=echo, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, Session


def ensure_database_exists(user=None, password=None, host=None, port=None, db_name=None):
    """Ensure the MySQL database exists. Connects to the server (no specific DB) and creates the DB if missing."""
    user = user or os.environ.get("MYSQL_USER", "root")
    password = password or os.environ.get("MYSQL_PASSWORD", "")
    host = host or os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = port or os.environ.get("MYSQL_PORT", "3306")
    db_name = db_name or os.environ.get("MYSQL_DATABASE", "knowlion")

    # connect without a database to create it if necessary
    base_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/"
    engine = create_engine(base_url, pool_pre_ping=True)
    with engine.connect() as conn:
        # create database if not exists
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;"))
        logger.info(f"Ensured database exists: {db_name}")


# SQL DDL statements for reference
CREATE_FILE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS `files` (
    `file_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `path` VARCHAR(255) UNIQUE,
    `upload_time` DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
'''

CREATE_JOBS_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS `jobs` (
  `job_id` INT PRIMARY KEY AUTO_INCREMENT,
  `stage` VARCHAR(255),
  `end_stage` VARCHAR(255),
    `status` VARCHAR(255) DEFAULT 'pending',
    `progress_index` INT DEFAULT 0,
    `partial_md_path` VARCHAR(255) DEFAULT NULL UNIQUE,
    `markdown_path` VARCHAR(255) DEFAULT NULL UNIQUE,
    `triples_path` VARCHAR(255) DEFAULT NULL UNIQUE,
    `knowledge_path` VARCHAR(255) DEFAULT NULL UNIQUE,
  `error_message` TEXT,
  `file_id` INT,
  `graph_id` VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
'''
CREATE_FILE_GRAPH_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS `file_graph` (
  `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `file_id` INT NOT NULL,
  `graph_id` INT NOT NULL,
  `created_at` DATETIME,
  CONSTRAINT `file_graph_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files`(`file_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `file_graph_ibfk_2` FOREIGN KEY (`graph_id`) REFERENCES `graph`(`graph_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
'''


def create_tables_if_missing(engine):
    """Create the `files` and `jobs` tables if they do not exist using raw DDL.

    This is a lightweight helper for initial setup. For production, prefer using
    migrations (Alembic) or SQLAlchemy models.
    """
    with engine.connect() as conn:
        conn.execute(text(CREATE_FILE_TABLE_SQL))
        conn.execute(text(CREATE_JOBS_TABLE_SQL))
        conn.execute(text(CREATE_FILE_GRAPH_TABLE_SQL))
        logger.info("Ensured `files`, `jobs`, and `file_graph` tables exist.")
