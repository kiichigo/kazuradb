from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .graphdb import GraphDB
from .profile import Profile


def parse_props(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("props must be a JSON object")
    return value


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SQLite relationship graph DB for AI agents"
    )
    parser.add_argument("--db", default="graph.db", help="SQLite DB path (default: graph.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    node = sub.add_parser("add-node", help="Create or update a node")
    node.add_argument("key")
    node.add_argument("--label")
    node.add_argument("--kind", default="entity")
    node.add_argument("--props")

    edge = sub.add_parser("add-edge", help="Create a directed relationship")
    edge.add_argument("source")
    edge.add_argument("type")
    edge.add_argument("target")
    edge.add_argument("--props")
    edge.add_argument("--no-create-missing", action="store_true")

    find = sub.add_parser("find-edges", help="Search relationships")
    find.add_argument("--source")
    find.add_argument("--target")
    find.add_argument("--type")
    find.add_argument("--limit", type=int, default=100)

    neigh = sub.add_parser("neighbors", help="Explore a node neighborhood")
    neigh.add_argument("key")
    neigh.add_argument("--direction", choices=["out", "in", "both"], default="both")
    neigh.add_argument("--depth", type=int, default=1)
    neigh.add_argument("--type")
    neigh.add_argument("--limit", type=int, default=100)

    path = sub.add_parser("path", help="Find a shortest directed path")
    path.add_argument("source")
    path.add_argument("target")
    path.add_argument("--max-depth", type=int, default=4)
    path.add_argument("--type")

    get = sub.add_parser("get-node", help="Look up a node by key")
    get.add_argument("key")

    dn = sub.add_parser("delete-node", help="Delete a node and its edges")
    dn.add_argument("key")

    de = sub.add_parser("delete-edge", help="Delete an edge by ID")
    de.add_argument("edge_id", type=int)

    profile_info = sub.add_parser("profile-info", help="Describe a declarative profile")
    profile_info.add_argument("profile")

    validate_edge = sub.add_parser("validate-edge", help="Validate a profile edge shape")
    validate_edge.add_argument("profile")
    validate_edge.add_argument("source_kind")
    validate_edge.add_argument("edge_type")
    validate_edge.add_argument("target_kind")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "profile-info":
        print_json(Profile.load(args.profile).to_dict())
        return
    if args.command == "validate-edge":
        Profile.load(args.profile).validate_edge(
            args.source_kind,
            args.edge_type,
            args.target_kind,
        )
        print_json(
            {
                "valid": True,
                "source_kind": args.source_kind,
                "edge_type": args.edge_type,
                "target_kind": args.target_kind,
            }
        )
        return

    db = GraphDB(args.db)
    try:
        if args.command == "add-node":
            result = db.add_node(args.key, args.label, args.kind, parse_props(args.props))
        elif args.command == "add-edge":
            result = db.add_edge(args.source, args.type, args.target, parse_props(args.props), not args.no_create_missing)
        elif args.command == "find-edges":
            result = db.find_edges(args.source, args.target, args.type, args.limit)
        elif args.command == "neighbors":
            result = db.neighbors(args.key, args.direction, args.depth, args.type, args.limit)
        elif args.command == "path":
            result = db.path(args.source, args.target, args.max_depth, args.type)
        elif args.command == "get-node":
            result = db.get_node(args.key)
        elif args.command == "delete-node":
            result = db.delete_node(args.key)
        elif args.command == "delete-edge":
            result = db.delete_edge(args.edge_id)
        else:  # pragma: no cover
            raise SystemExit(f"unknown command: {args.command}")
        print_json(result)
    except (KeyError, ValueError) as exc:
        print_json({"error": str(exc)})
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
