import pytest

from kazura import GraphDB


def test_nodes_edges_and_edge_search():
    db = GraphDB()
    db.add_node("agent:alice", "Alice", props={"role": "planner"})
    db.add_node("concept:graph-db", "Graph DB", kind="concept")

    edge1 = db.add_edge("agent:alice", "uses", "concept:graph-db", {"confidence": 0.9})
    edge2 = db.add_edge("agent:alice", "likes", "concept:graph-db")

    assert edge1["type"] == "uses"
    assert edge2["id"] != edge1["id"]
    found = db.find_edges(source="agent:alice", target="concept:graph-db")
    assert found["count"] == 2


def test_add_node_updates_props_by_key():
    db = GraphDB()
    db.add_node("agent:alice", "Alice", kind="person", props={"role": "planner", "team": "research"})

    updated = db.add_node("agent:alice", props={"role": "reviewer", "timezone": "UTC"})

    assert updated["props"] == {"role": "reviewer", "team": "research", "timezone": "UTC"}


def test_add_node_without_props_preserves_existing_props():
    db = GraphDB()
    db.add_node("agent:alice", props={"role": "planner"})

    updated = db.add_node("agent:alice", "Alice")

    assert updated["props"] == {"role": "planner"}


def test_neighbors_support_depth_and_direction():
    db = GraphDB()
    db.add_edge("a", "knows", "b")
    db.add_edge("b", "knows", "c")
    db.add_edge("x", "knows", "a")

    subgraph = db.neighbors("a", direction="out", depth=2)

    assert {node["key"] for node in subgraph["nodes"]} == {"a", "b", "c"}
    assert [edge["source"] for edge in subgraph["edges"]] == ["a", "b"]


def test_path_finds_shortest_directed_route():
    db = GraphDB()
    db.add_edge("a", "rel", "b")
    db.add_edge("b", "rel", "c")
    db.add_edge("a", "rel", "c")

    result = db.path("a", "c")

    assert result["found"] is True
    assert result["length"] == 1
    assert [edge["target"] for edge in result["edges"]] == ["c"]


def test_path_returns_not_found():
    db = GraphDB()
    db.add_node("a")
    db.add_node("z")

    result = db.path("a", "z")

    assert result == {"found": False, "nodes": [], "edges": [], "length": None}


def test_delete_node_removes_node_and_cascades_edges():
    db = GraphDB()
    db.add_edge("a", "rel", "b")
    db.delete_node("a")
    with pytest.raises(KeyError):
        db.get_node("a")
    assert db.find_edges(source="a")["count"] == 0


def test_delete_edge_removes_edge_only():
    db = GraphDB()
    edge = db.add_edge("a", "rel", "b")
    db.delete_edge(edge["id"])
    assert db.find_edges(source="a")["count"] == 0
    db.get_node("a")
    db.get_node("b")


def test_delete_missing_node_raises():
    db = GraphDB()
    with pytest.raises(KeyError):
        db.delete_node("nonexistent")


def test_delete_missing_edge_raises():
    db = GraphDB()
    with pytest.raises(KeyError):
        db.delete_edge(9999)


def test_neighbors_both_query_plan_avoids_edge_scan():
    db = GraphDB()
    for i in range(20):
        db.add_edge(f"n{i}", "rel", f"n{i + 1}")
    db.add_edge("hub", "rel", "n0")
    db.add_edge("n1", "rel", "hub")

    hub_id = db.get_node("hub")["id"]
    plan_rows = db.conn.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT e.*, s.key AS source_key, t.key AS target_key
        FROM edges e JOIN nodes s ON s.id = e.source_id JOIN nodes t ON t.id = e.target_id
        WHERE (e.source_id = ? OR e.target_id = ?)
        ORDER BY e.id
        """,
        (hub_id, hub_id),
    ).fetchall()
    plan = "\n".join(row[3] for row in plan_rows)

    assert "SCAN e" not in plan
