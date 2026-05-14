"""
Verification script for the SQLite Lab MCP Server.

Tests tool discovery, resource discovery, valid calls, and error handling
by communicating directly with the FastMCP server in-process.

Run:  python verify_server.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import Client

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

PASS = "[PASS]"
FAIL = "[FAIL]"
total = 0
passed = 0


def check(label: str, condition: bool, detail: str = ""):
    global total, passed
    total += 1
    if condition:
        passed += 1
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label}  -- {detail}")


def parse_tool_result(result) -> dict:
    """Parse a CallToolResult into a dict."""
    return json.loads(result.content[0].text)


def parse_resource_result(result) -> dict:
    """Parse a read_resource result (list) into a dict."""
    return json.loads(result[0].text)


async def main():
    global total, passed

    # Import the server object
    from mcp_server import mcp as server

    async with Client(server) as client:

        # ==============================================================
        print("\n--- 1. Tool Discovery ---")
        # ==============================================================
        tools = await client.list_tools()
        tool_names = sorted([t.name for t in tools])
        check("Server exposes tools", len(tools) >= 3, f"Found {len(tools)}")
        check("'search' tool exists", "search" in tool_names)
        check("'insert' tool exists", "insert" in tool_names)
        check("'aggregate' tool exists", "aggregate" in tool_names)

        # ==============================================================
        print("\n--- 2. Resource Discovery ---")
        # ==============================================================
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]
        check("Schema resource exists", any("schema://database" in u for u in resource_uris))

        resource_templates = await client.list_resource_templates()
        template_uris = [str(t.uriTemplate) for t in resource_templates]
        check(
            "Table schema template exists",
            any("table" in u for u in template_uris),
            f"Templates: {template_uris}",
        )

        # ==============================================================
        print("\n--- 3. Valid Tool Calls - search ---")
        # ==============================================================
        # Search all students
        result = await client.call_tool("search", {"table": "students"})
        data = parse_tool_result(result)
        check("Search all students returns rows", len(data.get("rows", [])) > 0)
        check("Search returns total count", data.get("total", 0) > 0)

        # Search with filter
        result = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": [{"column": "cohort", "operator": "=", "value": "A1"}],
            },
        )
        data = parse_tool_result(result)
        check(
            "Search with filter cohort=A1",
            all(r["cohort"] == "A1" for r in data["rows"]),
        )

        # Search with ordering
        result = await client.call_tool(
            "search",
            {"table": "students", "order_by": "score", "descending": True, "limit": 3},
        )
        data = parse_tool_result(result)
        scores = [r["score"] for r in data["rows"]]
        check("Search with ORDER BY score DESC", scores == sorted(scores, reverse=True))

        # Search with column selection
        result = await client.call_tool(
            "search",
            {"table": "students", "columns": ["name", "cohort"]},
        )
        data = parse_tool_result(result)
        check(
            "Search with column selection",
            set(data["columns"]) == {"name", "cohort"},
        )

        # ==============================================================
        print("\n--- 4. Valid Tool Calls - insert ---")
        # ==============================================================
        result = await client.call_tool(
            "insert",
            {
                "table": "students",
                "values": {
                    "name": "Test Student",
                    "cohort": "C1",
                    "email": "test@university.edu",
                    "score": 90.0,
                },
            },
        )
        data = parse_tool_result(result)
        check("Insert returns inserted payload", "inserted" in data)
        check("Insert returns an ID", data.get("inserted", {}).get("id") is not None)

        # Verify the insert
        result = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": [{"column": "email", "operator": "=", "value": "test@university.edu"}],
            },
        )
        data = parse_tool_result(result)
        check("Inserted student is searchable", len(data.get("rows", [])) == 1)

        # ==============================================================
        print("\n--- 5. Valid Tool Calls - aggregate ---")
        # ==============================================================
        # COUNT
        result = await client.call_tool(
            "aggregate", {"table": "students", "metric": "count"}
        )
        data = parse_tool_result(result)
        check("COUNT(*) returns a value", data["results"][0]["value"] > 0)

        # AVG with group_by
        result = await client.call_tool(
            "aggregate",
            {
                "table": "students",
                "metric": "avg",
                "column": "score",
                "group_by": "cohort",
            },
        )
        data = parse_tool_result(result)
        check("AVG(score) GROUP BY cohort returns groups", len(data["results"]) > 1)

        # MAX
        result = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "max", "column": "score"},
        )
        data = parse_tool_result(result)
        check("MAX(score) returns a value", data["results"][0]["value"] is not None)

        # ==============================================================
        print("\n--- 6. Resource Reads ---")
        # ==============================================================
        content = await client.read_resource("schema://database")
        schema = parse_resource_result(content)
        check("Full schema has students table", "students" in schema)
        check("Full schema has courses table", "courses" in schema)
        check("Full schema has enrollments table", "enrollments" in schema)

        content = await client.read_resource("schema://table/students")
        tbl = parse_resource_result(content)
        check("Table schema for students has columns", len(tbl.get("columns", [])) > 0)

        # ==============================================================
        print("\n--- 7. Error Handling - invalid requests ---")
        # ==============================================================
        # For error tests, the tool returns JSON with "error" key.
        # We need raise_on_error=False since our tools don't raise but
        # return error JSON. Actually our tools return error JSON as
        # normal text output, so raise_on_error won't trigger.

        # Unknown table
        result = await client.call_tool("search", {"table": "nonexistent"})
        data = parse_tool_result(result)
        check("Unknown table returns error", "error" in data)

        # Unknown column
        result = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": [{"column": "fake_col", "operator": "=", "value": "x"}],
            },
        )
        data = parse_tool_result(result)
        check("Unknown column returns error", "error" in data)

        # Unsupported operator
        result = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": [{"column": "name", "operator": "DROP", "value": "x"}],
            },
        )
        data = parse_tool_result(result)
        check("Unsupported operator returns error", "error" in data)

        # Invalid metric
        result = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "median", "column": "score"},
        )
        data = parse_tool_result(result)
        check("Unsupported metric returns error", "error" in data)

        # Empty insert
        result = await client.call_tool(
            "insert", {"table": "students", "values": {}}
        )
        data = parse_tool_result(result)
        check("Empty insert returns error", "error" in data)

    # ==============================================================
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} checks passed")
    if passed == total:
        print("All checks passed!")
    else:
        print(f"WARNING: {total - passed} check(s) failed.")
    print(f"{'='*50}\n")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
