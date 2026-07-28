# KazuraDB modes

## What a mode is

A KazuraDB mode is a bundled experience that sits on top of the core graph database. The core stores nodes and directed edges without any domain knowledge. A mode adds the layer above that: it defines which node kinds and edge types are meaningful for a specific use case, what properties edges should carry, and what tools or commands make sense for that domain.

Modes correspond to Layer 3 and Layer 4 in the [layered architecture](../LAYERED_RELATIONSHIP_DB.md):

```
Layer 4: Mode tools and CLI commands
         e.g.  kazura code-intel ingest ./src
               kazura code-intel check-stale

Layer 3: Mode schema
         e.g.  allowed node kinds, allowed edge types, required props

Layer 1–2: Core KazuraDB (unchanged)
           nodes + directed edges + JSON props + timestamps
```

The core database does not know what a file, a function, or a document means. It only guarantees durable graph storage and traversal. The mode interprets the graph and enforces conventions.

## What a mode provides

A mode bundles four things:

| Component | Description |
|-----------|-------------|
| **Schema** | Allowed node `kind` values, allowed edge `type_key` values, required and optional props |
| **Key naming convention** | The `<prefix>:<identifier>` format for node keys in this domain |
| **Workflow tools** | CLI subcommands and MCP operations specific to this mode |
| **Update rules** | Which relationships can be auto-computed, which require human or LLM input, and how staleness is detected |

## Bundled modes

| Mode | Document | Description |
|------|----------|-------------|
| `code-intel` | [CODE_INTEL.md](CODE_INTEL.md) | Code and project file relationship graph for AI agents |

More modes may be added for other domains, such as manga character relationship charts, research citation graphs, or personal knowledge maps. Each lives in its own document in this directory.

## Relationship to the core

A mode writes ordinary KazuraDB nodes and edges. No special tables or core changes are required. The mode's schema is advisory: the CLI and MCP tools for that mode enforce conventions before writing, but the underlying graph remains plain and queryable through the core API as well.

This means:

- A mode can be added without modifying the core database.
- Nodes and edges written by a mode are readable through the standard `get-node`, `find-edges`, `neighbors`, and `path` commands.
- Multiple modes can coexist in the same database as long as their node key prefixes do not collide.
