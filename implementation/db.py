"""
Database adapter for the SQLite MCP server.

Provides a clean abstraction over SQLite with:
- Schema introspection
- Safe parameterized queries
- Input validation (table names, column names, operators)
"""

import sqlite3
import os
from typing import Any

# ---------------------------------------------------------------------------
# Supported filter operators — only these are allowed in WHERE clauses.
# ---------------------------------------------------------------------------
SUPPORTED_OPERATORS = {
    "=", "!=", ">", "<", ">=", "<=", "LIKE", "NOT LIKE", "IN", "NOT IN",
}

# ---------------------------------------------------------------------------
# Supported aggregate metrics
# ---------------------------------------------------------------------------
SUPPORTED_METRICS = {"count", "avg", "sum", "min", "max"}


class ValidationError(Exception):
    """Raised when a request cannot be safely executed."""


class SQLiteAdapter:
    """
    Thin wrapper around SQLite that enforces identifier validation
    before building any SQL string.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        """Return a connection with Row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------
    def list_tables(self) -> list[str]:
        """Return all user-created table names (excludes sqlite internals)."""
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            return [r["name"] for r in rows]
        finally:
            conn.close()

    def get_table_schema(self, table: str) -> list[dict]:
        """Return column definitions for *table* via PRAGMA table_info."""
        self._validate_table(table)
        conn = self.connect()
        try:
            rows = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            return [
                {
                    "cid": r["cid"],
                    "name": r["name"],
                    "type": r["type"],
                    "notnull": bool(r["notnull"]),
                    "default_value": r["dflt_value"],
                    "primary_key": bool(r["pk"]),
                }
                for r in rows
            ]
        finally:
            conn.close()

    def get_full_schema(self) -> dict:
        """Return the schema for every table in the database."""
        tables = self.list_tables()
        schema: dict[str, list[dict]] = {}
        for t in tables:
            schema[t] = self.get_table_schema(t)
        return schema

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _validate_table(self, table: str) -> None:
        tables = self.list_tables()
        if table not in tables:
            raise ValidationError(
                f"Unknown table '{table}'. Available tables: {tables}"
            )

    def _validate_columns(self, table: str, columns: list[str]) -> None:
        schema = self.get_table_schema(table)
        valid_cols = {col["name"] for col in schema}
        for c in columns:
            if c not in valid_cols:
                raise ValidationError(
                    f"Unknown column '{c}' in table '{table}'. "
                    f"Valid columns: {sorted(valid_cols)}"
                )

    def _validate_operator(self, op: str) -> None:
        if op.upper() not in SUPPORTED_OPERATORS:
            raise ValidationError(
                f"Unsupported operator '{op}'. "
                f"Supported: {sorted(SUPPORTED_OPERATORS)}"
            )

    def _validate_metric(self, metric: str) -> None:
        if metric.lower() not in SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported metric '{metric}'. "
                f"Supported: {sorted(SUPPORTED_METRICS)}"
            )

    # ------------------------------------------------------------------
    # WHERE clause builder
    # ------------------------------------------------------------------
    def _build_where(
        self, filters: list[dict], table: str
    ) -> tuple[str, list[Any]]:
        """
        Build a WHERE clause from a list of filter dicts.

        Each filter dict must have:
          - column: str
          - operator: str  (one of SUPPORTED_OPERATORS)
          - value: any

        Returns (clause_string, params_list).
        """
        if not filters:
            return "", []

        clauses: list[str] = []
        params: list[Any] = []

        # Validate all filter columns at once
        self._validate_columns(table, [f["column"] for f in filters])

        for f in filters:
            col = f["column"]
            op = f.get("operator", "=").upper()
            val = f["value"]

            self._validate_operator(op)

            if op in ("IN", "NOT IN"):
                if not isinstance(val, list) or len(val) == 0:
                    raise ValidationError(
                        f"Operator '{op}' requires a non-empty list value."
                    )
                placeholders = ", ".join(["?"] * len(val))
                clauses.append(f"[{col}] {op} ({placeholders})")
                params.extend(val)
            else:
                clauses.append(f"[{col}] {op} ?")
                params.append(val)

        return "WHERE " + " AND ".join(clauses), params

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict:
        """
        Execute a safe SELECT query.

        Returns {"columns": [...], "rows": [...], "total": int}.
        """
        self._validate_table(table)

        # Column selection
        if columns:
            self._validate_columns(table, columns)
            select_cols = ", ".join(f"[{c}]" for c in columns)
        else:
            select_cols = "*"

        # WHERE
        where_clause, params = self._build_where(filters or [], table)

        # ORDER BY
        order_clause = ""
        if order_by:
            self._validate_columns(table, [order_by])
            direction = "DESC" if descending else "ASC"
            order_clause = f"ORDER BY [{order_by}] {direction}"

        # Count total matching rows
        count_sql = f"SELECT COUNT(*) AS cnt FROM [{table}] {where_clause}"

        # Main query
        sql = (
            f"SELECT {select_cols} FROM [{table}] "
            f"{where_clause} {order_clause} LIMIT ? OFFSET ?"
        )
        params_with_paging = params + [limit, offset]

        conn = self.connect()
        try:
            total = conn.execute(count_sql, params).fetchone()["cnt"]
            rows = conn.execute(sql, params_with_paging).fetchall()
            result_rows = [dict(r) for r in rows]
            col_names = list(result_rows[0].keys()) if result_rows else []
            return {
                "columns": col_names,
                "rows": result_rows,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # INSERT
    # ------------------------------------------------------------------
    def insert(self, table: str, values: dict) -> dict:
        """
        Insert a single row and return the inserted payload with its new ID.
        """
        self._validate_table(table)

        if not values:
            raise ValidationError("Cannot insert an empty row — values must not be empty.")

        columns = list(values.keys())
        self._validate_columns(table, columns)

        col_str = ", ".join(f"[{c}]" for c in columns)
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO [{table}] ({col_str}) VALUES ({placeholders})"

        conn = self.connect()
        try:
            cursor = conn.execute(sql, list(values.values()))
            conn.commit()
            new_id = cursor.lastrowid
            inserted = {"id": new_id, **values}
            return {"inserted": inserted}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # AGGREGATE
    # ------------------------------------------------------------------
    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict] | None = None,
        group_by: str | None = None,
    ) -> dict:
        """
        Execute an aggregate query (COUNT, AVG, SUM, MIN, MAX).
        """
        self._validate_table(table)
        self._validate_metric(metric)

        metric_upper = metric.upper()

        # COUNT can work without a column (COUNT(*))
        if metric_upper == "COUNT" and column is None:
            agg_expr = "COUNT(*)"
        elif column is None:
            raise ValidationError(
                f"Metric '{metric}' requires a column argument."
            )
        else:
            self._validate_columns(table, [column])
            agg_expr = f"{metric_upper}([{column}])"

        # WHERE
        where_clause, params = self._build_where(filters or [], table)

        # GROUP BY
        group_clause = ""
        select_prefix = ""
        if group_by:
            self._validate_columns(table, [group_by])
            group_clause = f"GROUP BY [{group_by}]"
            select_prefix = f"[{group_by}], "

        sql = (
            f"SELECT {select_prefix}{agg_expr} AS value "
            f"FROM [{table}] {where_clause} {group_clause}"
        )

        conn = self.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            result = [dict(r) for r in rows]
            return {
                "metric": metric_upper,
                "column": column,
                "table": table,
                "group_by": group_by,
                "results": result,
            }
        finally:
            conn.close()
