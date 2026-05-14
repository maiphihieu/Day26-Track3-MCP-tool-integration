"""
MCP Server for the SQLite Lab.

Exposes three tools (search, insert, aggregate) and two resources
(full database schema, per-table schema) via the FastMCP framework.

Run:
    python mcp_server.py              # stdio transport (default)
    python mcp_server.py --transport sse   # SSE transport (bonus)
"""

import argparse
import json
import os
import sys

from fastmcp import FastMCP

# Ensure the implementation package is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import SQLiteAdapter, ValidationError
from init_db import create_database, DB_PATH

# ---------------------------------------------------------------------------
# Bootstrap: ensure the database exists
# ---------------------------------------------------------------------------
if not os.path.exists(DB_PATH):
    create_database(DB_PATH)

adapter = SQLiteAdapter(DB_PATH)

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "SQLite Lab MCP Server",
    instructions=(
        "A FastMCP server that exposes a university SQLite database "
        "through search, insert, and aggregate tools, plus schema resources."
    ),
)


# ===================================================================
# TOOLS
# ===================================================================


@mcp.tool(
    name="search",
    description=(
        "Search rows in a database table. Supports column selection, "
        "filtering, ordering, and pagination."
    ),
)
def search(
    table: str,
    columns: list[str] | None = None,
    filters: list[dict] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
) -> str:
    """
    Search a table with optional filters, column selection, ordering,
    and pagination.

    Args:
        table: Name of the table to search.
        columns: List of column names to return (default: all).
        filters: List of filter objects, each with 'column', 'operator', 'value'.
                 Supported operators: =, !=, >, <, >=, <=, LIKE, NOT LIKE, IN, NOT IN.
        limit: Maximum number of rows to return (default 20).
        offset: Number of rows to skip (default 0).
        order_by: Column name to sort by.
        descending: If true, sort descending.

    Returns:
        JSON string with columns, rows, total count, limit, and offset.
    """
    try:
        result = adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )
        return json.dumps(result, indent=2, default=str)
    except ValidationError as e:
        return json.dumps({"error": str(e)})


@mcp.tool(
    name="insert",
    description="Insert a new row into a database table.",
)
def insert(table: str, values: dict) -> str:
    """
    Insert a single row into a table.

    Args:
        table: Name of the table to insert into.
        values: Dictionary mapping column names to values.

    Returns:
        JSON string with the inserted row (including generated ID).
    """
    try:
        result = adapter.insert(table=table, values=values)
        return json.dumps(result, indent=2, default=str)
    except ValidationError as e:
        return json.dumps({"error": str(e)})


@mcp.tool(
    name="aggregate",
    description=(
        "Run an aggregate query on a table. "
        "Supports count, avg, sum, min, max with optional group_by."
    ),
)
def aggregate(
    table: str,
    metric: str,
    column: str | None = None,
    filters: list[dict] | None = None,
    group_by: str | None = None,
) -> str:
    """
    Compute an aggregate metric on a table.

    Args:
        table: Name of the table.
        metric: One of 'count', 'avg', 'sum', 'min', 'max'.
        column: Column to aggregate (required for avg/sum/min/max, optional for count).
        filters: Optional list of filter objects.
        group_by: Optional column name to group results by.

    Returns:
        JSON string with the aggregate results.
    """
    try:
        result = adapter.aggregate(
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )
        return json.dumps(result, indent=2, default=str)
    except ValidationError as e:
        return json.dumps({"error": str(e)})


# ===================================================================
# RESOURCES
# ===================================================================


@mcp.resource("schema://database", description="Full database schema for all tables.")
def database_schema() -> str:
    """Return the complete database schema as JSON."""
    schema = adapter.get_full_schema()
    return json.dumps(schema, indent=2)


@mcp.resource(
    "schema://table/{table_name}",
    description="Schema for a single table, identified by name.",
)
def table_schema(table_name: str) -> str:
    """Return the schema for a specific table as JSON."""
    try:
        cols = adapter.get_table_schema(table_name)
        return json.dumps({"table": table_name, "columns": cols}, indent=2)
    except ValidationError as e:
        return json.dumps({"error": str(e)})


# ===================================================================
# Entry point
# ===================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLite Lab MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport to use (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")
