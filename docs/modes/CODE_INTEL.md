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
| `declares` | `file` | `function` or `class` | File declares an entity defined elsewhere (C/C++ headers, interface stubs) |
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

## The `derivation` property

`origin` records **who** wrote an edge. `derivation` records **how confidently it was determined**. These are separate axes, because an LLM can state something it read directly in the source, and a static parser can guess at a cross-file call it cannot fully resolve.

| `derivation` value | Meaning |
|--------------------|---------|
| `extracted` | Explicitly present in the source. A parser saw the import statement; an LLM read the literal declaration. |
| `inferred` | Resolved, guessed, or judged. A cross-file call matched by name only; a semantic responsibility an LLM concluded from reading. |

```json
{
  "origin": "tree-sitter:python",
  "derivation": "inferred",
  "file": "src/auth/login.py",
  "file_hash": "a3f92c1d...",
  "line": 42,
  "note": "callee name matched by name only; target file not resolved"
}
```

Agents should be able to ask for high-confidence structure only (`derivation: extracted`) when precision matters, and include inferred edges when exploring broadly. Keeping this separate from `origin` means a future parser upgrade that resolves cross-file calls properly can flip edges from `inferred` to `extracted` without changing their `origin`.

## Mode commands

The mode exposes a small command surface on top of the core CLI.

| Command | Purpose |
|---------|---------|
| `kazura code-intel ingest <path>` | Scan a directory and register structural relationships |
| `kazura code-intel update <file>` | Re-scan a single file and replace its static edges |
| `kazura code-intel check-stale` | List edges whose `file_hash` no longer matches the file on disk |
| `kazura code-intel explain <node-key>` | Show a node with its incoming and outgoing edges grouped by type |
| `kazura code-intel entrypoints` | List upstream nodes — where execution begins |
| `kazura code-intel foundations [--limit N]` | List the most depended-upon nodes — the reusable machinery |
| `kazura code-intel layers` | Show the import graph in topological order |

### Orientation commands

An agent arriving at a graph it has not seen before needs a way in. `explain` answers "what is this thing connected to?", but only once a node has been chosen. The other three commands answer "which node should I look at first?"

They are separate commands because they answer genuinely different questions. Both `calls` and `imports` edges point in the direction of dependency, so the two ends of the graph hold different things:

| Position in the graph | What lives there | Degree signature |
|----------------------|------------------|------------------|
| Upstream (sources) | `main()`, CLI handlers, HTTP routes, test functions | Low in-degree, moderate out-degree |
| Middle | Domain logic, orchestrators | High out-degree |
| Downstream (sinks) | Logging, string helpers, `os`, `requests` | Very high in-degree |

A naive "most connected nodes" ranking is dominated by in-degree, so it returns the *bottom* of the call tree — widely reused utilities. Those are worth knowing about, but they are not where reading should start. `foundations` reports them under an accurate name; `entrypoints` reports the upstream end; `layers` shows the shape between the two.

Reading top-down from `entrypoints` follows the order in which the program actually executes. Reading `foundations` builds vocabulary — the primitives this codebase is written in terms of. Both are useful and neither substitutes for the other.

### Why orientation leans on the import graph

Identifying entry points by "in-degree zero in the call graph" does not work on its own. Cross-file calls are frequently `inferred` or unresolved (see the `derivation` section), so functions that genuinely are called appear to have no callers. The result is a long list of false entry points.

Two measures address this:

1. **Prefer the import graph for structural orientation.** Import statements are unambiguous and always `extracted`, so the file- and module-level topology is trustworthy. `layers` and the first pass of `entrypoints` should operate at file granularity; function-level detail comes afterward.
2. **Combine degree with heuristics.** A function named `main`, a body inside `if __name__ == "__main__"`, a routing decorator, a symbol re-exported from a package `__init__`, or a test function are all positive signals. Record them in the node props so `entrypoints` does not depend on degree alone.

While cross-file call resolution remains approximate, the reliable skeleton of the graph is the one built from `extracted` edges.

## Language considerations

The `imports` edge type is kept as the generic dependency relation across all languages, with the language-specific mechanism recorded in props:

```json
{
  "origin": "tree-sitter:c",
  "derivation": "extracted",
  "mechanism": "include",
  "system": false
}
```

Splitting the edge type per language (`includes`, `requires`, `uses`) would force agents to write a different query for every language. Keeping one type and describing the mechanism in props follows the same principle as `origin` and `derivation`: the core stays generic, the detail lives in properties.

### Three families of dependency declaration

| Family | Languages | What the statement names | Reliability for orientation |
|--------|-----------|-------------------------|----------------------------|
| Module | Python, Go, Rust, JavaScript, TypeScript | A file or module | High — this is the assumed case |
| Namespace | Java, C# | A namespace, not a file | **Same-package references need no import, so the graph has holes** |
| Textual inclusion | C, C++ | A header file | High, but headers carry declarations only |

Namespace-family languages are the harder case, not C. A Java class referencing another class in the same package produces no import statement at all, so package-internal dependencies are invisible in the import graph. Resolution requires matching type references against the package's own declarations.

### C and C++ specifics

Two properties of C change how the graph should be built.

**Declaration and definition are separate files.** The include graph reaches the header, not the implementation:

```
file:src/main.c    --imports--> file:include/parser.h
file:include/parser.h --declares--> func:parse
file:src/parser.c  --defines-->  func:parse      <-- joined by name, not by any source construct
```

The `declares` edge type exists to record this. Bridging `declares` and `defines` is a name match that no source file states explicitly — it is the linker's job. This is worth doing because C makes the match unusually safe: there is no overloading and the global namespace is flat, so a name identifies at most one external definition. Cross-file call resolution in C can therefore be pushed toward `extracted` more confidently than in Python. The exception is `static` functions, which are translation-unit local and must be excluded from global name matching.

**Every translation unit is a source in the include DAG.** Because `.c` files are compiled independently, none of them is included by anything else. File-level `entrypoints` detection degenerates: a project with 100 `.c` files reports 100 entry points. For C, entry-point detection must come from `main()` and from recorded facts (below), not from in-degree.

The preprocessor is the main limitation. tree-sitter parses source without preprocessing, so `#ifdef` branches are not resolved, macro-generated code is not expanded, and include path resolution depends on build configuration that is not present in the source tree.

### Entry points that static analysis cannot see

Any entry point registered at runtime is invisible to a parser. Examples span every language and platform:

- Host-application plugin hooks — `initializePlugin` / `uninitializePlugin` in a Maya C++ plugin, loaded by the host via `dlopen`
- Shared library and runtime hooks — `DllMain`, `JNI_OnLoad`, `PyInit_*`
- Framework registration — route decorators, event handlers, signal/slot connections, dependency-injection containers, reflection-based dispatch

None of these are called from anywhere in the codebase, so they have zero in-degree and no syntactic marker that distinguishes them from dead code.

This mode does not attempt to enumerate frameworks. Building in a table of every SDK is unbounded work and will always be incomplete. Instead, an entry point is a **recordable fact** rather than only a computed one. An agent that recognizes the convention writes it to the graph:

```bash
kazura add-edge func:src/plugin.cpp::initializePlugin marks concept:entrypoint \
  --props '{"origin":"llm","derivation":"inferred","note":"Maya plugin load hook; invoked by the host application via dlopen, not from any call site in this codebase"}'
```

Because `origin` is `llm`, the fact survives re-ingestion. A later session reads it from the graph instead of re-deriving it from the source.

`entrypoints` therefore returns the union of heuristic detection and recorded facts, and should report which is which. It must not present its output as complete: unsupported does not mean absent, it means unknown, and an agent that is told the difference can go and fill the gap.

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

## Prior art and positioning

Other tools address the same underlying problem — replacing repeated grep with a precomputed relationship graph. [graphifyy](https://pypi.org/project/graphifyy/) (Apache-2.0) is the closest in concept: it uses tree-sitter across 36+ language grammars, adds an LLM pass for documents and media, tags edges as `EXTRACTED` or `INFERRED`, and serves the result over MCP. Its independent arrival at the extracted/inferred distinction is useful corroboration that the axis is worth modeling.

Where this mode deliberately differs:

| Dimension | Build-pipeline tools | KazuraDB code intelligence mode |
|-----------|---------------------|--------------------------------|
| Update model | Rebuild the graph from a scan | Incremental writes at edge granularity |
| Primary author | The scanner; the LLM is one extraction pass | The agent, continuously, as it learns |
| Storage | Generated artifact files | A live SQLite database that is written to during use |
| Scope | A code-graph product | One mode on a general-purpose relationship database |

The distinction that matters most is **who owns the graph over time**. A build pipeline treats the graph as derived output: regenerate it and the previous state is gone. This mode treats the graph as accumulated memory. An agent that reads a file and understands something the parser could never derive should be able to record that, and have it survive the next ingest. Static analysis supplies the skeleton; the agent adds what only reading can reveal; the `origin` field keeps the two from overwriting each other.

That premise also explains why this lives as a mode rather than a standalone tool. The same core stores manga character maps, research citation graphs, and agent memory. Code intelligence is one vocabulary over a general graph, not a separate product — which means relationships that cross the boundary (a design document, a build artifact, a domain concept) are ordinary nodes rather than special cases.

Ideas worth adopting from prior art, on their own merits: broad tree-sitter grammar coverage added incrementally, the value of a graph-level orientation step, and a compact `explain` / `path` / `query` command vocabulary. Note that this mode reaches a different conclusion about what orientation should surface — see [Orientation commands](#orientation-commands) — because ranking nodes by connection count returns reused utilities rather than starting points. Ideas deliberately left out for now: community detection, bundled visualization, and media ingestion — these are valuable but belong to a presentation layer, not to the graph model this mode is responsible for.

## Scope and limitations

- **Call resolution across files**: tree-sitter extracts call site names but cannot resolve which file's function is being called without type information. Cross-file `calls` edges are best-effort or LLM-authored.
- **Dynamic dispatch**: method calls through interfaces or dynamic attributes cannot be resolved statically.
- **Scale**: SQLite BFS is practical for repositories with tens of thousands of nodes. For very large monorepos the graph may need partitioning or an external graph database.
- **Non-code files**: `doc:` and `build:` nodes are written by LLM agents or custom scanners, not by the tree-sitter ingestion pipeline.
