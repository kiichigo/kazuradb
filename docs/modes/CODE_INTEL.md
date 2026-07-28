# Code intelligence mode

## Purpose

The code intelligence mode turns a project directory into a relationship graph that AI agents can query. Instead of grepping through files on every request, an agent can ask the graph: "what does this function call?", "which files import this module?", or "what document describes this class?" The graph persists across sessions and can be updated incrementally.

The mode supports two complementary update paths:

- **Static ingestion**: a scanner reads source files and registers structural relationships automatically (imports, function definitions, call sites, class inheritance).
- **LLM annotation**: an agent reads code or documentation and writes semantic relationships that static analysis cannot derive (what a module is responsible for, which source file a design document describes, architectural dependencies).

Both paths write to the same core KazuraDB graph. The `origin` property on each edge records who wrote it, so stale static edges can be refreshed without touching LLM-authored ones.

## Node kinds and key naming

Node keys follow the pattern `<prefix>:<identifier>`.

| Kind | Key format | Example |
|------|-----------|---------|
| `file` | `file:<repo-relative path>` | `file:src/auth/login.py` |
| `function` | `func:<repo-relative path>::<name>` | `func:src/auth/login.py::authenticate` |
| `class` | `class:<repo-relative path>::<name>` | `class:src/models/user.py::User` |
| `module` | `module:<import name>` | `module:os`, `module:requests` |
| `concept` | `concept:<slug>` | `concept:authentication` |
| `doc` | `doc:<repo-relative path>` | `doc:docs/auth.md` |
| `build-artifact` | `build:<repo-relative path>` | `build:dist/bundle.js` |

Use repo-relative paths (no leading slash, forward slashes on all platforms) so keys are stable regardless of where the repository is checked out.

## Edge types

| `type_key` | Typical source kind | Typical target kind | Description |
|------------|--------------------|--------------------|-------------|
| `imports` | `file` | `module` or `file` | File imports a module or another file |
| `defines` | `file` | `function` or `class` | File contains the definition |
| `calls` | `function` | `function` | Function calls another function |
| `inherits` | `class` | `class` | Class extends or implements another class |
| `documents` | `doc` | `file`, `function`, or `class` | Document describes a code entity |
| `generates` | `file` | `build-artifact` | Source file produces a build output |
| `references` | any | any | General reference when a more specific type does not apply |

Additional edge types can be added by convention as long as they are documented here.

## The `origin` property

Every edge should carry an `origin` property that names the tool or actor that wrote it. This is the key mechanism for separating automatically computed relationships from manually or LLM-authored ones.

| `origin` value | Meaning |
|----------------|---------|
| `tree-sitter:python` | Extracted by the tree-sitter Python parser |
| `tree-sitter:typescript` | Extracted by the tree-sitter TypeScript parser |
| `import-scanner` | Extracted by a lightweight import-only scanner |
| `llm` | Written by an LLM agent while reading code or documentation |
| `manual` | Written by a human directly |

Example edge props for a static-analysis edge:

```json
{
  "origin": "tree-sitter:python",
  "file": "src/auth/login.py",
  "file_hash": "a3f92c1d...",
  "line": 42
}
```

Example edge props for an LLM-authored edge:

```json
{
  "origin": "llm",
  "note": "This module owns all session lifecycle logic including token refresh."
}
```

## Staleness detection

Static-analysis edges embed `file` and `file_hash` in their props. When a file changes, its hash changes, and any edge whose `file_hash` no longer matches the current file is considered potentially stale.

The staleness check works as follows:

1. Find all edges whose `origin` starts with a known static-analysis tool name.
2. For each such edge, read the current hash of `props.file`.
3. Report edges where `props.file_hash` differs from the current hash.

LLM-authored edges (`origin: "llm"`) are not checked for staleness by hash, because their validity is semantic, not tied to a single file's byte content. If an LLM-authored relationship becomes wrong after a refactor, an agent updates or removes it directly.

## Update flows

### Full ingestion (initial scan or full refresh)

```
kazura code-intel ingest <project-root> [--lang python|typescript|...]
```

1. Walk the directory tree and collect source files by language.
2. Parse each file with tree-sitter.
3. Extract: file→module imports, file→function/class definitions, function→function calls, class→class inheritance.
4. Delete existing edges with a matching `origin` and `file` (replace, not accumulate).
5. Register updated nodes and edges with the current `file_hash`.

### Partial update (single file changed)

When an agent or tool knows that a specific file changed:

1. Delete all edges where `origin` matches a static-analysis tool name and `file` equals the changed path.
2. Re-parse the file and write new edges.

This can be triggered by an LLM agent without running a full ingest.

### LLM annotation

An agent reads code or documentation and adds semantic edges:

```bash
kazura add-edge module:auth documents concept:authentication \
  --props '{"origin":"llm","note":"Handles login, session management, and token refresh"}'
```

```bash
kazura add-edge doc:docs/auth.md documents file:src/auth/login.py \
  --props '{"origin":"llm"}'
```

LLM-authored edges coexist with static edges in the same graph and are not touched by the ingest or staleness-check workflows.

## Example: querying the graph as an agent

```bash
# What does authenticate() call?
kazura find-edges --source func:src/auth/login.py::authenticate --type calls

# Which files import the requests module?
kazura find-edges --target module:requests --type imports

# What is two hops from the User class?
kazura neighbors class:src/models/user.py::User --depth 2

# Is there a path from the login function to the database layer?
kazura path func:src/auth/login.py::authenticate func:src/db/session.py::get_session
```

## Scope and limitations

- **Call resolution across files**: tree-sitter extracts call site names but cannot resolve which file's function is being called without type information. Cross-file `calls` edges are best-effort or LLM-authored.
- **Dynamic dispatch**: method calls through interfaces or dynamic attributes cannot be resolved statically.
- **Scale**: SQLite BFS is practical for repositories with tens of thousands of nodes. For very large monorepos the graph may need partitioning or an external graph database.
- **Non-code files**: `doc:` and `build:` nodes are written by LLM agents or custom scanners, not by the tree-sitter ingestion pipeline.
