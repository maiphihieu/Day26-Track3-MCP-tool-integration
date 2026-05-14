# Lab: Build a Database MCP Server with FastMCP and SQLite

## Overview

A production-quality **Model Context Protocol (MCP) server** built with [FastMCP](https://gofastmcp.com/) and SQLite. The server exposes a university database through three MCP tools (`search`, `insert`, `aggregate`) and two MCP resources (full schema, per-table schema), with comprehensive input validation and error handling.

## Features

| Category | Details |
|---|---|
| **Tools** | `search` (filters, ordering, pagination, column selection), `insert` (with ID return), `aggregate` (count, avg, sum, min, max + group_by) |
| **Resources** | `schema://database` (full schema), `schema://table/{name}` (per-table) |
| **Validation** | Rejects unknown tables, unknown columns, unsupported operators, invalid metrics, empty inserts |
| **Safety** | All SQL uses parameterized queries — no raw string concatenation |
| **Testing** | 37 automated pytest tests + 26-check verification script |

## Data Model

```
students (id, name, cohort, email, score)
    |
    |--- enrollments (id, student_id, course_id, semester, grade)
    |
courses (id, name, department, credits)
```

Seed data: 8 students, 5 courses, 12 enrollments across cohorts A1, A2, B1, B2.

## Project Structure

```
implementation/
  db.py                 # SQLiteAdapter — database layer with validation
  init_db.py            # Schema creation and seed data
  mcp_server.py         # FastMCP server (tools + resources)
  verify_server.py      # 26-check verification script
  requirements.txt      # Python dependencies
  mcp_config.json       # Client configuration example
  start_inspector.sh    # MCP Inspector launcher
  university.db         # SQLite database (auto-generated)
  tests/
    test_server.py      # 37 pytest tests
```

## Setup

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
cd implementation
pip install -r requirements.txt
```

### Initialize Database

```bash
python init_db.py
```

This creates `university.db` with schema + seed data. Re-running recreates from scratch.

### Start the Server

```bash
# stdio transport (default — for MCP clients)
python mcp_server.py

# SSE transport (for web/Inspector)
python mcp_server.py --transport sse --port 8000
```

## Tool Reference

### `search`

Search rows in a table with optional filtering, ordering, and pagination.

**Parameters:**
| Name | Type | Default | Description |
|---|---|---|---|
| `table` | string | *required* | Table name |
| `columns` | string[] | all | Columns to return |
| `filters` | object[] | none | Filter conditions |
| `limit` | int | 20 | Max rows |
| `offset` | int | 0 | Skip rows |
| `order_by` | string | none | Sort column |
| `descending` | bool | false | Sort direction |

**Filter format:** `{"column": "cohort", "operator": "=", "value": "A1"}`

**Supported operators:** `=`, `!=`, `>`, `<`, `>=`, `<=`, `LIKE`, `NOT LIKE`, `IN`, `NOT IN`

**Example:**
```json
{
  "table": "students",
  "filters": [{"column": "cohort", "operator": "=", "value": "A1"}],
  "order_by": "score",
  "descending": true,
  "limit": 5
}
```

### `insert`

Insert a new row and return the inserted payload with generated ID.

**Parameters:**
| Name | Type | Description |
|---|---|---|
| `table` | string | Table name |
| `values` | object | Column-value mapping |

**Example:**
```json
{
  "table": "students",
  "values": {
    "name": "New Student",
    "cohort": "A1",
    "email": "new@university.edu",
    "score": 88.5
  }
}
```

### `aggregate`

Compute aggregate metrics with optional filtering and grouping.

**Parameters:**
| Name | Type | Default | Description |
|---|---|---|---|
| `table` | string | *required* | Table name |
| `metric` | string | *required* | One of: `count`, `avg`, `sum`, `min`, `max` |
| `column` | string | none | Column to aggregate (optional for count) |
| `filters` | object[] | none | Filter conditions |
| `group_by` | string | none | Grouping column |

**Example:**
```json
{
  "table": "students",
  "metric": "avg",
  "column": "score",
  "group_by": "cohort"
}
```

## Resource Reference

### `schema://database`

Returns the complete database schema as JSON — all tables with their column definitions.

### `schema://table/{table_name}`

Returns the schema for a single table. Example: `schema://table/students`

## Testing

### Automated Tests (pytest)

```bash
cd implementation
python -m pytest tests/test_server.py -v
```

Runs 37 tests covering:
- Tool discovery (2 tests)
- Resource discovery (2 tests)
- Search tool (7 tests — filters, ordering, pagination, LIKE, IN)
- Insert tool (3 tests — students, courses, enrollments)
- Aggregate tool (7 tests — count, avg, sum, min, max, group_by, filters)
- Schema resources (2 tests)
- Error handling (8 tests — unknown table/column, bad operator/metric, empty insert)
- Database adapter unit tests (6 tests)

### Verification Script

```bash
cd implementation
python verify_server.py
```

Runs 26 end-to-end checks through the FastMCP Client API.

### MCP Inspector

```bash
cd implementation

# Linux/macOS
./start_inspector.sh

# Windows (manual)
npx -y @modelcontextprotocol/inspector python mcp_server.py
```

**Inspector checklist:**
- [ ] Tools appear with schemas
- [ ] Resources appear
- [ ] Valid tool call succeeds
- [ ] Invalid tool call returns clear error

## Client Configuration

### Claude Code

Add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "python"
args = ["/ABSOLUTE/PATH/TO/implementation/mcp_server.py"]
```

### Gemini CLI

```bash
gemini mcp add sqlite-lab /ABSOLUTE/PATH/TO/python /ABSOLUTE/PATH/TO/implementation/mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
```

Smoke test:
```bash
gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use the sqlite-lab MCP server and show me the top 2 students by score."
```

### Antigravity

Add to `mcp_config.json`:

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/implementation/mcp_server.py"],
      "cwd": "/ABSOLUTE/PATH/TO/implementation"
    }
  }
}
```

## Example Tasks

| Task | Tool | Arguments |
|---|---|---|
| Search students in cohort A1 | `search` | `{"table": "students", "filters": [{"column": "cohort", "operator": "=", "value": "A1"}]}` |
| Insert a new student | `insert` | `{"table": "students", "values": {"name": "Jane", "cohort": "A1", "email": "jane@uni.edu", "score": 90}}` |
| Count all students | `aggregate` | `{"table": "students", "metric": "count"}` |
| Average score by cohort | `aggregate` | `{"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"}` |
| Read full schema | Resource | `schema://database` |
| Read students schema | Resource | `schema://table/students` |
| Invalid: search missing table | `search` | `{"table": "nonexistent"}` → returns error |

## Error Handling Examples

```json
// Unknown table
{"error": "Unknown table 'nonexistent'. Available tables: ['courses', 'enrollments', 'students']"}

// Unknown column
{"error": "Unknown column 'fake' in table 'students'. Valid columns: ['cohort', 'email', 'id', 'name', 'score']"}

// Unsupported operator
{"error": "Unsupported operator 'DROP'. Supported: ['!=', '<', '<=', '=', '>', '>=', 'IN', 'LIKE', 'NOT IN', 'NOT LIKE']"}

// Empty insert
{"error": "Cannot insert an empty row -- values must not be empty."}
```