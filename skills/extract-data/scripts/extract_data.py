"""
Extract data from a Databricks SQL warehouse.

Usage:
    python extract_data.py "<SQL statement>"

Reads connection settings from environment variables (see .env.example):
    DATABRICKS_HOST          Workspace URL
    DATABRICKS_WAREHOUSE_ID  SQL warehouse ID to run the statement against
    DATABRICKS_TOKEN         Personal access token

Prints a JSON object with "columns" and "rows" on success, or exits with a
non-zero status and an error message on failure.
"""

import json
import os
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

DEFAULT_WAIT_TIMEOUT = "50s"


def get_client() -> WorkspaceClient:
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if not host or not token:
        raise RuntimeError("DATABRICKS_HOST and DATABRICKS_TOKEN must be set")

    return WorkspaceClient(host=host, token=token)


def run_query(statement: str, wait_timeout: str = DEFAULT_WAIT_TIMEOUT) -> dict:
    """Execute a SQL statement against the configured warehouse.

    Returns a dict with "columns" (list of column names) and "rows"
    (list of row value arrays).
    """
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise RuntimeError("DATABRICKS_WAREHOUSE_ID must be set")

    client = get_client()
    result = client.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        wait_timeout=wait_timeout,
    )

    state = result.status.state if result.status else None

    if state in (StatementState.PENDING, StatementState.RUNNING):
        raise RuntimeError(f"Warehouse still {state.value} after {wait_timeout}")

    if state != StatementState.SUCCEEDED:
        error_message = result.status.error.message if result.status and result.status.error else "Unknown error"
        state_label = state.value if state else "no state"
        raise RuntimeError(f"SQL failed ({state_label}): {error_message}")

    schema = result.manifest.schema if result.manifest else None
    if not schema or not schema.columns:
        raise RuntimeError("SQL succeeded but result schema is empty")

    columns = [column.name for column in schema.columns]
    rows = result.result.data_array if (result.result and result.result.data_array) else []

    return {"columns": columns, "rows": rows}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('Usage: extract_data.py "<SQL statement>"')

    statement = sys.argv[1]

    try:
        data = run_query(statement)
    except Exception as exc:
        sys.exit(f"ERROR ({exc.__class__.__name__}): {exc}")

    print(json.dumps(data))


if __name__ == "__main__":
    main()
