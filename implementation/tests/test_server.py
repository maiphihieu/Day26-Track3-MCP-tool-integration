"""
Automated tests for the SQLite Lab MCP Server.

Run:  pytest tests/test_server.py -v
"""

import asyncio
import json
import os
import sys
import pytest

# Add implementation directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastmcp import Client
from db import SQLiteAdapter, ValidationError
from init_db import create_database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB = os.path.join(os.path.dirname(__file__), "..", "test_university.db")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create a fresh test database for the entire test session."""
    create_database(TEST_DB)
    # Patch the server's adapter to use the test DB
    import mcp_server

    mcp_server.adapter = SQLiteAdapter(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def adapter():
    return SQLiteAdapter(TEST_DB)


@pytest.fixture
def client():
    """Return a context-manager-style fixture for the MCP client."""
    import mcp_server
    return mcp_server.mcp


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def call_tool(server, name, args):
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        return json.loads(result.content[0].text)


async def list_tools_async(server):
    async with Client(server) as client:
        return await client.list_tools()


async def list_resources_async(server):
    async with Client(server) as client:
        return await client.list_resources()


async def list_resource_templates_async(server):
    async with Client(server) as client:
        return await client.list_resource_templates()


async def read_resource_async(server, uri):
    async with Client(server) as client:
        result = await client.read_resource(uri)
        return json.loads(result[0].text)


# ===========================================================================
# 1. Tool Discovery
# ===========================================================================

class TestToolDiscovery:
    def test_three_tools_exposed(self, client):
        tools = asyncio.run(list_tools_async(client))
        names = [t.name for t in tools]
        assert "search" in names
        assert "insert" in names
        assert "aggregate" in names
        assert len(names) >= 3

    def test_tool_schemas_have_descriptions(self, client):
        tools = asyncio.run(list_tools_async(client))
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"


# ===========================================================================
# 2. Resource Discovery
# ===========================================================================

class TestResourceDiscovery:
    def test_database_schema_resource(self, client):
        resources = asyncio.run(list_resources_async(client))
        uris = [str(r.uri) for r in resources]
        assert any("schema://database" in u for u in uris)

    def test_table_schema_template(self, client):
        templates = asyncio.run(list_resource_templates_async(client))
        uris = [str(t.uriTemplate) for t in templates]
        assert any("table" in u for u in uris)


# ===========================================================================
# 3. Search Tool
# ===========================================================================

class TestSearchTool:
    def test_search_all_students(self, client):
        data = asyncio.run(call_tool(client, "search", {"table": "students"}))
        assert "rows" in data
        assert data["total"] == 8

    def test_search_with_filter(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "filters": [{"column": "cohort", "operator": "=", "value": "A1"}],
        }))
        assert all(r["cohort"] == "A1" for r in data["rows"])
        assert data["total"] == 3  # Alice, Bob, George

    def test_search_with_ordering(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "order_by": "score",
            "descending": True,
            "limit": 3,
        }))
        scores = [r["score"] for r in data["rows"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_with_column_selection(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "columns": ["name", "email"],
        }))
        assert set(data["columns"]) == {"name", "email"}

    def test_search_with_pagination(self, client):
        page1 = asyncio.run(call_tool(client, "search", {
            "table": "students", "limit": 3, "offset": 0,
        }))
        page2 = asyncio.run(call_tool(client, "search", {
            "table": "students", "limit": 3, "offset": 3,
        }))
        assert len(page1["rows"]) == 3
        assert len(page2["rows"]) == 3
        ids1 = {r["id"] for r in page1["rows"]}
        ids2 = {r["id"] for r in page2["rows"]}
        assert ids1.isdisjoint(ids2), "Pages should not overlap"

    def test_search_with_like_operator(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "filters": [{"column": "name", "operator": "LIKE", "value": "%Nguyen%"}],
        }))
        assert len(data["rows"]) >= 1

    def test_search_with_in_operator(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "filters": [{"column": "cohort", "operator": "IN", "value": ["A1", "B1"]}],
        }))
        for r in data["rows"]:
            assert r["cohort"] in ("A1", "B1")


# ===========================================================================
# 4. Insert Tool
# ===========================================================================

class TestInsertTool:
    def test_insert_student(self, client):
        data = asyncio.run(call_tool(client, "insert", {
            "table": "students",
            "values": {
                "name": "Pytest Student",
                "cohort": "T1",
                "email": "pytest@university.edu",
                "score": 99.0,
            },
        }))
        assert "inserted" in data
        assert data["inserted"]["id"] is not None
        assert data["inserted"]["name"] == "Pytest Student"

    def test_insert_course(self, client):
        data = asyncio.run(call_tool(client, "insert", {
            "table": "courses",
            "values": {
                "name": "Deep Learning",
                "department": "Computer Science",
                "credits": 4,
            },
        }))
        assert data["inserted"]["name"] == "Deep Learning"

    def test_insert_enrollment(self, client):
        data = asyncio.run(call_tool(client, "insert", {
            "table": "enrollments",
            "values": {
                "student_id": 1,
                "course_id": 1,
                "semester": "2025-Fall",
                "grade": 9.0,
            },
        }))
        assert data["inserted"]["semester"] == "2025-Fall"


# ===========================================================================
# 5. Aggregate Tool
# ===========================================================================

class TestAggregateTool:
    def test_count_students(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "count",
        }))
        assert data["results"][0]["value"] >= 8

    def test_avg_score(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "avg", "column": "score",
        }))
        assert isinstance(data["results"][0]["value"], (int, float))

    def test_avg_score_group_by_cohort(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students",
            "metric": "avg",
            "column": "score",
            "group_by": "cohort",
        }))
        assert len(data["results"]) > 1
        for row in data["results"]:
            assert "cohort" in row
            assert "value" in row

    def test_max_score(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "max", "column": "score",
        }))
        assert data["results"][0]["value"] is not None

    def test_min_score(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "min", "column": "score",
        }))
        assert data["results"][0]["value"] is not None

    def test_sum_credits(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "courses", "metric": "sum", "column": "credits",
        }))
        assert data["results"][0]["value"] >= 16

    def test_count_with_filter(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students",
            "metric": "count",
            "filters": [{"column": "cohort", "operator": "=", "value": "A1"}],
        }))
        assert data["results"][0]["value"] >= 3


# ===========================================================================
# 6. Schema Resources
# ===========================================================================

class TestSchemaResources:
    def test_full_schema(self, client):
        schema = asyncio.run(read_resource_async(client, "schema://database"))
        assert "students" in schema
        assert "courses" in schema
        assert "enrollments" in schema

    def test_table_schema(self, client):
        data = asyncio.run(read_resource_async(client, "schema://table/students"))
        assert data["table"] == "students"
        col_names = [c["name"] for c in data["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "cohort" in col_names
        assert "email" in col_names
        assert "score" in col_names


# ===========================================================================
# 7. Error Handling
# ===========================================================================

class TestErrorHandling:
    def test_unknown_table(self, client):
        data = asyncio.run(call_tool(client, "search", {"table": "nonexistent"}))
        assert "error" in data

    def test_unknown_column_in_filter(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "filters": [{"column": "fake", "operator": "=", "value": "x"}],
        }))
        assert "error" in data

    def test_unknown_column_in_columns(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "columns": ["name", "nonexistent"],
        }))
        assert "error" in data

    def test_unsupported_operator(self, client):
        data = asyncio.run(call_tool(client, "search", {
            "table": "students",
            "filters": [{"column": "name", "operator": "DROP", "value": "x"}],
        }))
        assert "error" in data

    def test_unsupported_metric(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "median", "column": "score",
        }))
        assert "error" in data

    def test_empty_insert(self, client):
        data = asyncio.run(call_tool(client, "insert", {
            "table": "students", "values": {},
        }))
        assert "error" in data

    def test_insert_unknown_column(self, client):
        data = asyncio.run(call_tool(client, "insert", {
            "table": "students",
            "values": {"name": "X", "nonexistent": "Y"},
        }))
        assert "error" in data

    def test_aggregate_metric_without_column(self, client):
        data = asyncio.run(call_tool(client, "aggregate", {
            "table": "students", "metric": "avg",
        }))
        assert "error" in data


# ===========================================================================
# 8. Database Adapter Unit Tests
# ===========================================================================

class TestDatabaseAdapter:
    def test_list_tables(self, adapter):
        tables = adapter.list_tables()
        assert "students" in tables
        assert "courses" in tables
        assert "enrollments" in tables

    def test_get_table_schema(self, adapter):
        schema = adapter.get_table_schema("students")
        col_names = [c["name"] for c in schema]
        assert "id" in col_names
        assert "name" in col_names

    def test_validate_table_raises(self, adapter):
        with pytest.raises(ValidationError, match="Unknown table"):
            adapter._validate_table("nonexistent")

    def test_validate_columns_raises(self, adapter):
        with pytest.raises(ValidationError, match="Unknown column"):
            adapter._validate_columns("students", ["fake_column"])

    def test_validate_operator_raises(self, adapter):
        with pytest.raises(ValidationError, match="Unsupported operator"):
            adapter._validate_operator("DROP")

    def test_validate_metric_raises(self, adapter):
        with pytest.raises(ValidationError, match="Unsupported metric"):
            adapter._validate_metric("median")
