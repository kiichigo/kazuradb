from __future__ import annotations

import os
from typing import Any

from .graphdb import GraphDB

DB_PATH = os.environ.get("KAZURA_DB", "graph.db")
_db: GraphDB | None = None


def _get_db() -> GraphDB:
    global _db
    if _db is None:
        _db = GraphDB(DB_PATH)
    return _db


def add_node(key: str, label: str | None = None, kind: str = "entity", props: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create or update a node identified by a human-readable key."""
    return _get_db().add_node(key, label, kind, props)


def add_edge(source: str, type_key: str, target: str, props: dict[str, Any] | None = None, create_missing: bool = True) -> dict[str, Any]:
    """Create a directed edge. Multiple edges between the same nodes are allowed."""
    return _get_db().add_edge(source, type_key, target, props, create_missing)


def find_edges(source: str | None = None, target: str | None = None, type_key: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Search relationships by source, target, and/or relationship type."""
    return _get_db().find_edges(source, target, type_key, limit)


def neighbors(key: str, direction: str = "both", depth: int = 1, type_key: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Return a JSON subgraph around a node."""
    return _get_db().neighbors(key, direction, depth, type_key, limit)


def path(source: str, target: str, max_depth: int = 4, type_key: str | None = None) -> dict[str, Any]:
    """Find a shortest directed path between two nodes."""
    return _get_db().path(source, target, max_depth, type_key)


def delete_node(key: str) -> dict[str, Any]:
    """Delete a node and all its connected edges."""
    return _get_db().delete_node(key)


def delete_edge(edge_id: int) -> dict[str, Any]:
    """Delete a specific edge by ID."""
    return _get_db().delete_edge(edge_id)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Install MCP support with: pip install 'kazura[mcp]' or pip install mcp") from exc

    mcp = FastMCP("kazura-graphdb")
    for tool in (add_node, add_edge, find_edges, neighbors, path, delete_node, delete_edge):
        mcp.tool()(tool)
    mcp.run()


if __name__ == "__main__":
    main()
