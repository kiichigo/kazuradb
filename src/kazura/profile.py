from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only without optional dependency installed
    yaml = None


class ProfileValidationError(ValueError):
    """Raised when graph data does not match a declarative profile."""


@dataclass(frozen=True)
class NodeKind:
    """A node kind allowed by a profile."""

    key: str
    description: str | None = None


@dataclass(frozen=True)
class EdgeType:
    """An edge type allowed by a profile."""

    key: str
    source_kinds: tuple[str, ...]
    target_kinds: tuple[str, ...]
    description: str | None = None
    symmetric: bool = False


@dataclass(frozen=True)
class Profile:
    """Small declarative schema for validating GraphDB node and edge shapes."""

    name: str
    description: str | None = None
    node_kinds: dict[str, NodeKind] = field(default_factory=dict)
    edge_types: dict[str, EdgeType] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        """Load a profile from a YAML file."""

        profile_path = Path(path)
        with profile_path.open("r", encoding="utf-8") as fh:
            raw = _load_yaml(fh.read())
        if not isinstance(raw, dict):
            raise ProfileValidationError(f"profile must be a YAML mapping: {profile_path}")
        return cls.from_dict(raw, source=str(profile_path))

    @classmethod
    def from_dict(cls, raw: dict[str, Any], source: str = "profile") -> "Profile":
        name = _required_string(raw, "name", source)
        description = _optional_string(raw, "description", source)
        node_kinds_raw = _required_mapping(raw, "node_kinds", source)
        edge_types_raw = _required_mapping(raw, "edge_types", source)

        node_kinds: dict[str, NodeKind] = {}
        for key, spec in node_kinds_raw.items():
            kind = _mapping_spec(key, spec, "node kind", source)
            node_kinds[str(key)] = NodeKind(
                key=str(key),
                description=_optional_string(kind, "description", source),
            )

        edge_types: dict[str, EdgeType] = {}
        for key, spec in edge_types_raw.items():
            edge = _mapping_spec(key, spec, "edge type", source)
            source_kinds = _string_list(
                edge,
                "source_kinds",
                f"edge type {key!r} in {source}",
            )
            target_kinds = _string_list(
                edge,
                "target_kinds",
                f"edge type {key!r} in {source}",
            )
            for kind in (*source_kinds, *target_kinds):
                if kind not in node_kinds:
                    raise ProfileValidationError(
                        f"edge type {key!r} references unknown node kind {kind!r}"
                    )
            edge_types[str(key)] = EdgeType(
                key=str(key),
                source_kinds=tuple(source_kinds),
                target_kinds=tuple(target_kinds),
                description=_optional_string(edge, "description", source),
                symmetric=bool(edge.get("symmetric", False)),
            )

        return cls(
            name=name,
            description=description,
            node_kinds=node_kinds,
            edge_types=edge_types,
        )

    def validate_node_kind(self, kind: str) -> bool:
        if kind not in self.node_kinds:
            allowed = ", ".join(sorted(self.node_kinds)) or "none"
            raise ProfileValidationError(
                f"node kind {kind!r} is not allowed by profile {self.name!r}; "
                f"allowed kinds: {allowed}"
            )
        return True

    def validate_edge(self, source_kind: str, edge_type: str, target_kind: str) -> bool:
        self.validate_node_kind(source_kind)
        self.validate_node_kind(target_kind)
        edge = self.edge_types.get(edge_type)
        if edge is None:
            allowed = ", ".join(sorted(self.edge_types)) or "none"
            raise ProfileValidationError(
                f"edge type {edge_type!r} is not allowed by profile {self.name!r}; "
                f"allowed edge types: {allowed}"
            )
        if source_kind not in edge.source_kinds:
            allowed = ", ".join(edge.source_kinds)
            raise ProfileValidationError(
                f"edge {edge_type!r} cannot start from node kind {source_kind!r}; "
                f"allowed source kinds: {allowed}"
            )
        if target_kind not in edge.target_kinds:
            allowed = ", ".join(edge.target_kinds)
            raise ProfileValidationError(
                f"edge {edge_type!r} cannot target node kind {target_kind!r}; "
                f"allowed target kinds: {allowed}"
            )
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "node_kinds": {
                key: {"description": node.description}
                for key, node in self.node_kinds.items()
            },
            "edge_types": {
                key: {
                    "description": edge.description,
                    "source_kinds": list(edge.source_kinds),
                    "target_kinds": list(edge.target_kinds),
                    "symmetric": edge.symmetric,
                }
                for key, edge in self.edge_types.items()
            },
        }


def _required_string(raw: dict[str, Any], key: str, source: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(
            f"{source} must define non-empty string field {key!r}"
        )
    return value


def _optional_string(raw: dict[str, Any], key: str, source: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileValidationError(
            f"{source} field {key!r} must be a string when provided"
        )
    return value


def _required_mapping(raw: dict[str, Any], key: str, source: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict) or not value:
        raise ProfileValidationError(f"{source} must define non-empty mapping {key!r}")
    return value


def _mapping_spec(key: Any, spec: Any, label: str, source: str) -> dict[str, Any]:
    if not isinstance(key, str) or not key.strip():
        raise ProfileValidationError(
            f"{source} contains a {label} with a non-empty string key"
        )
    if not isinstance(spec, dict):
        raise ProfileValidationError(f"{label} {key!r} in {source} must be a mapping")
    return spec


def _string_list(raw: dict[str, Any], key: str, source: str) -> list[str]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ProfileValidationError(
            f"{source} must define non-empty string list {key!r}"
        )
    return value


def _load_yaml(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return _load_simple_profile_yaml(text)


def _load_simple_profile_yaml(text: str) -> dict[str, Any]:
    """Parse the small profile YAML subset used by bundled examples.

    This fallback keeps the core profile API usable in constrained test
    environments where PyYAML cannot be installed. PyYAML remains the declared
    dependency and is used whenever available.
    """

    root: dict[str, Any] = {}
    section: str | None = None
    current_key: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0:
            key, value = _split_yaml_pair(line)
            if value == "":
                root[key] = {}
                section = key
                current_key = None
            else:
                root[key] = _parse_yaml_scalar(value)
                section = None
                current_key = None
        elif indent == 2 and section in {"node_kinds", "edge_types"}:
            key, value = _split_yaml_pair(line)
            root[section][key] = {} if value == "" else _parse_yaml_scalar(value)
            current_key = key
        elif indent == 4 and section and current_key:
            key, value = _split_yaml_pair(line)
            root[section][current_key][key] = _parse_yaml_scalar(value)
        else:
            raise ProfileValidationError(f"unsupported YAML profile line: {raw_line!r}")
    return root


def _split_yaml_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ProfileValidationError(f"unsupported YAML profile line: {line!r}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_yaml_scalar(value: str) -> Any:
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [item.strip() for item in inner.split(",")]
    return value
