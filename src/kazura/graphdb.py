from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any, Iterable


class GraphDB:
    """Small SQLite relationship graph optimized for agent-readable JSON."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db_path = str(path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                label TEXT,
                kind TEXT NOT NULL DEFAULT 'entity',
                props_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                target_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                type_key TEXT NOT NULL,
                props_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type_key);
            CREATE INDEX IF NOT EXISTS idx_edges_source_type ON edges(source_id, type_key);
            CREATE INDEX IF NOT EXISTS idx_edges_target_type ON edges(target_id, type_key);
            CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
            """
        )
        self.conn.commit()

    def add_node(self, key: str, label: str | None = None, kind: str = "entity", props: dict[str, Any] | None = None) -> dict[str, Any]:
        self._validate_key(key, "node key")
        existing = self.conn.execute("SELECT props_json FROM nodes WHERE key = ?", (key,)).fetchone()
        merged_props = props or {}
        if existing is not None:
            merged_props = {**self._loads(existing["props_json"]), **merged_props}
        props_json = self._dumps(merged_props)
        self.conn.execute(
            """
            INSERT INTO nodes(key, label, kind, props_json) VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                label=COALESCE(excluded.label, nodes.label),
                kind=excluded.kind,
                props_json=excluded.props_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (key, label, kind, props_json),
        )
        self.conn.commit()
        return self.get_node(key)

    def add_edge(self, source: str, type_key: str, target: str, props: dict[str, Any] | None = None, create_missing: bool = True) -> dict[str, Any]:
        self._validate_key(type_key, "edge type")
        if create_missing:
            self.add_node(source)
            self.add_node(target)
        source_node = self.get_node(source)
        target_node = self.get_node(target)
        self.conn.execute(
            "INSERT INTO edges(source_id, target_id, type_key, props_json) VALUES (?, ?, ?, ?)",
            (source_node["id"], target_node["id"], type_key, self._dumps(props or {})),
        )
        self.conn.commit()
        edge_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return self.get_edge(edge_id)

    def get_node(self, key: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM nodes WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise KeyError(f"node not found: {key}")
        return self._node(row)

    def get_edge(self, edge_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT e.*, s.key AS source_key, t.key AS target_key
            FROM edges e
            JOIN nodes s ON s.id = e.source_id
            JOIN nodes t ON t.id = e.target_id
            WHERE e.id = ?
            """,
            (edge_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"edge not found: {edge_id}")
        return self._edge(row)

    def find_edges(self, source: str | None = None, target: str | None = None, type_key: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("s.key = ?")
            params.append(source)
        if target:
            clauses.append("t.key = ?")
            params.append(target)
        if type_key:
            clauses.append("e.type_key = ?")
            params.append(type_key)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT e.*, s.key AS source_key, t.key AS target_key
            FROM edges e JOIN nodes s ON s.id = e.source_id JOIN nodes t ON t.id = e.target_id
            {where}
            ORDER BY e.id LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return {"edges": [self._edge(r) for r in rows], "count": len(rows)}

    def neighbors(self, key: str, direction: str = "both", depth: int = 1, type_key: str | None = None, limit: int = 100) -> dict[str, Any]:
        self.get_node(key)
        seen = {key}
        frontier = deque([(key, 0)])
        nodes: dict[str, dict[str, Any]] = {key: self.get_node(key)}
        edges: list[dict[str, Any]] = []
        while frontier and len(edges) < limit:
            current, dist = frontier.popleft()
            if dist >= depth:
                continue
            for edge in self._incident_edges(current, direction, type_key):
                if len(edges) >= limit:
                    break
                edges.append(edge)
                other = edge["target"] if edge["source"] == current else edge["source"]
                if other not in nodes:
                    nodes[other] = self.get_node(other)
                if other not in seen:
                    seen.add(other)
                    frontier.append((other, dist + 1))
        return {"start": key, "depth": depth, "direction": direction, "nodes": list(nodes.values()), "edges": edges}

    def path(self, source: str, target: str, max_depth: int = 4, type_key: str | None = None) -> dict[str, Any]:
        self.get_node(source)
        self.get_node(target)
        queue = deque([(source, [])])
        seen = {source}
        while queue:
            current, path_edges = queue.popleft()
            if len(path_edges) >= max_depth:
                continue
            for edge in self._incident_edges(current, "out", type_key):
                nxt = edge["target"]
                new_path = [*path_edges, edge]
                if nxt == target:
                    node_keys = [source] + [e["target"] for e in new_path]
                    return {"found": True, "nodes": [self.get_node(k) for k in node_keys], "edges": new_path, "length": len(new_path)}
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, new_path))
        return {"found": False, "nodes": [], "edges": [], "length": None}

    def delete_node(self, key: str) -> dict[str, Any]:
        node = self.get_node(key)
        self.conn.execute("DELETE FROM nodes WHERE key = ?", (key,))
        self.conn.commit()
        return {"deleted": True, "key": key, "id": node["id"]}

    def delete_edge(self, edge_id: int) -> dict[str, Any]:
        self.get_edge(edge_id)
        self.conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        self.conn.commit()
        return {"deleted": True, "id": edge_id}

    def _incident_edges(self, key: str, direction: str, type_key: str | None) -> Iterable[dict[str, Any]]:
        if direction not in {"out", "in", "both"}:
            raise ValueError("direction must be one of: out, in, both")
        if direction == "both":
            node_id = self.get_node(key)["id"]
            type_clause = " AND e.type_key = ?" if type_key else ""
            params: list[Any] = [node_id, node_id]
            if type_key:
                params.append(type_key)
            rows = self.conn.execute(
                f"""
                SELECT e.*, s.key AS source_key, t.key AS target_key
                FROM edges e JOIN nodes s ON s.id = e.source_id JOIN nodes t ON t.id = e.target_id
                WHERE (e.source_id = ? OR e.target_id = ?){type_clause}
                ORDER BY e.id
                """,
                params,
            ).fetchall()
            return [self._edge(r) for r in rows]

        side = "s.key" if direction == "out" else "t.key"
        type_clause = " AND e.type_key = ?" if type_key else ""
        params = [key]
        if type_key:
            params.append(type_key)
        rows = self.conn.execute(
            f"""
            SELECT e.*, s.key AS source_key, t.key AS target_key
            FROM edges e JOIN nodes s ON s.id = e.source_id JOIN nodes t ON t.id = e.target_id
            WHERE ({side} = ?){type_clause}
            ORDER BY e.id
            """,
            params,
        ).fetchall()
        return [self._edge(r) for r in rows]

    @staticmethod
    def _validate_key(key: str, name: str) -> None:
        if not key or not key.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def _dumps(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _loads(value: str) -> dict[str, Any]:
        return json.loads(value) if value else {}

    def _node(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "key": row["key"], "label": row["label"], "kind": row["kind"], "props": self._loads(row["props_json"])}

    def _edge(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "source": row["source_key"], "type": row["type_key"], "target": row["target_key"], "props": self._loads(row["props_json"])}
