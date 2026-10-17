"""Nexusmart: raw-file checks and nine-file cleaning pipeline.

The staging/database tasks from the skeleton are intentionally not included
until their implementations are available.
"""
import csv
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

log = logging.getLogger(__name__)
RAW_DIR = Path(os.environ.get("RAW_DIR", "/opt/airflow/data/raw"))
PROCESSED_DIR = Path(os.environ.get("PROCESSED_DIR", "/opt/airflow/data/processed"))
INCLUDE_DIR = Path(os.environ.get("INCLUDE_DIR", "/opt/airflow/include"))

EXPECTED_FILES = [
    "customers", "products", "sellers", "locations", "orders",
    "order_items", "payments", "shipping", "returns",
]


@dag(
    dag_id="nexusmart_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["nexusmart"],
)
def nexusmart_pipeline():

    @task
    def extract():
        """Assert that every required file is accessible in the Airflow container."""
        missing = [name + ".csv" for name in EXPECTED_FILES
                   if not (RAW_DIR / f"{name}.csv").is_file()]
        if missing:
            raise FileNotFoundError(f"Missing raw files in {RAW_DIR}: {missing}")
        log.info("All %d raw CSVs found in %s", len(EXPECTED_FILES), RAW_DIR)

    @task
    def validate_raw():
        """Check readable headers and at least one data record in each CSV."""
        for name in EXPECTED_FILES:
            file = RAW_DIR / f"{name}.csv"
            with file.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                first_record = next(reader, None)
            if not header or not any(v.strip() for v in header):
                raise ValueError(f"Missing CSV header: {file}")
            if first_record is None:
                raise ValueError(f"CSV has no data rows: {file}")
            log.info("Validated %s (%d columns)", file.name, len(header))

    @task
    def clean():
        """Invoke the teammate's real cleaner; any failure marks the task failed."""
        if not (INCLUDE_DIR / "clean" / "__init__.py").is_file():
            raise FileNotFoundError(f"Cleaning package not found under {INCLUDE_DIR}/clean")
        if str(INCLUDE_DIR) not in sys.path:
            sys.path.insert(0, str(INCLUDE_DIR))
        from clean import run_all

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        summary = run_all(str(RAW_DIR), str(PROCESSED_DIR))
        log.info("Cleaning completed. Output: %s; summary: %s", PROCESSED_DIR, summary)

    @task
    def reset_database():
        import os
        from pathlib import Path
        from sqlalchemy import create_engine

        warehouse_url = os.environ["WAREHOUSE_URL"]
        sql_path = Path("/opt/airflow/include/sql/00_reset.sql")

        if not sql_path.is_file():
            raise FileNotFoundError(f"Reset SQL not found: {sql_path}")

        reset_sql = sql_path.read_text(encoding="utf-8")

        engine = create_engine(warehouse_url)

        try:
            connection = engine.raw_connection()
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute(reset_sql)
                    connection.commit()
                    log.info("NexusMart warehouse reset completed")
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    cursor.close()
            finally:
                connection.close()
        finally:
            engine.dispose()

    @task
    def load_staging_task():
        """Load CSVs specified by include/sql/load_staging.sql.

        The script contains psql-only COPY meta-commands. Use psycopg2's COPY
        FROM STDIN equivalent so psql need not be installed in Airflow.
        """
        import re
        import psycopg2
        from psycopg2 import sql
        from sqlalchemy.engine import make_url

        script = INCLUDE_DIR / "sql" / "load_staging.sql"
        if not script.is_file():
            raise FileNotFoundError(f"Missing staging script: {script}")

        # Allow only the nine expected staging tables and matching CSVs.
        expected = {f"stg_{name}": f"{name}.csv" for name in EXPECTED_FILES}
        pattern = re.compile(
            r"^\\copy\s+(stg_[a-z_]+)\s+from\s+'[^']*/([^'/]+\.csv)'\s+csv\s+header\s*$",
            re.IGNORECASE,
        )
        commands = []
        for line_number, line in enumerate(script.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            match = pattern.fullmatch(line)
            if not match:
                raise ValueError(f"Unsupported staging command at line {line_number}: {line}")
            table, filename = match.group(1), match.group(2)
            if expected.get(table) != filename:
                raise ValueError(f"Unexpected staging target on line {line_number}: {table}, {filename}")
            commands.append((table, PROCESSED_DIR / filename))
        if len(commands) != len(expected) or {table for table, _ in commands} != set(expected):
            raise ValueError("load_staging.sql must contain each of the nine staging tables exactly once")

        # WAREHOUSE_URL is a SQLAlchemy URL; pass its safely decoded parts to psycopg2.
        url = make_url(os.environ["WAREHOUSE_URL"])
        conn = psycopg2.connect(
            host=url.host, port=url.port or 5432, dbname=url.database,
            user=url.username, password=url.password,
        )
        try:
            with conn.cursor() as cur:
                for table, csv_file in commands:
                    if not csv_file.is_file():
                        raise FileNotFoundError(csv_file)
                    with csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
                        columns = next(csv.reader(handle), None)
                        if not columns:
                            raise ValueError(f"Empty CSV header: {csv_file}")
                        handle.seek(0)
                        statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
                            sql.Identifier(table),
                            sql.SQL(", ").join(map(sql.Identifier, columns)),
                        )
                        cur.copy_expert(statement.as_string(conn), handle)
                    log.info("Loaded %s from %s", table, csv_file.name)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Define every task before constructing its dependency chain.
    extract() >> validate_raw() >> clean() >> reset_database() >> load_staging_task()


nexusmart_pipeline()

