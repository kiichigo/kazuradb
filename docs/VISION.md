# KazuraDB product vision

## 1. What KazuraDB is today

KazuraDB is a small SQLite-backed relationship graph database prototype for AI agents. It stores knowledge as human-readable nodes and directed edges, with lightweight `kind` fields and arbitrary JSON properties. It exposes the same graph operations through a JSON-printing CLI and an optional MCP server: create or update nodes, create directed multi-edges, search edges, explore neighborhoods, and find shortest directed paths.

The current design prioritizes embeddability and inspectability over a full graph database runtime. SQLite is the storage layer, node keys are meant to be readable by humans and agents, edge types are plain strings, multiple edges between the same nodes are allowed, and relationship-type metadata can be represented as normal graph nodes when needed.

## 2. Technical improvements identified

- **Timestamps as explicit columns on nodes and edges:** `created_at` and `updated_at` are now explicit columns on both core tables. This makes temporal metadata queryable without unpacking JSON properties.
- **`created_by` as an edge rather than a column:** Prefer modeling authorship or provenance as graph structure, for example `fact -> created_by -> agent:alice`, instead of adding a fixed `created_by` column. This keeps provenance extensible and graph-native.
- **Composite indexes:** `idx_edges_source_type` and `idx_edges_target_type` have already been merged. These support common filtered traversals such as “outgoing edges of this type” and “incoming edges of this type.”
- **`neighbors(direction="both")` query rewrite:** The bidirectional neighbor query has already been rewritten to look up the start node ID and filter by `source_id` or `target_id`, avoiding an edge-table scan in the tested query plan.

## 3. Use case directions

### A. AI agent knowledge store

**Actionable now:** KazuraDB can already serve as a shared graph memory for agents. Agents can write facts as nodes and edges, preserve alternate or conflicting facts through multi-edges, and query neighborhoods or paths through the CLI or MCP server.

**Speculative direction:** Position KazuraDB as a complement to RAG. Vector search can retrieve relevant text chunks, while KazuraDB enriches those chunks with explicit relationships: who created a fact, what it depends on, what it contradicts, and which concepts connect it to other knowledge.

### B. Personal knowledge visualization

**Actionable now:** The persistence layer can store the extracted relationship graph for a user-provided domain such as anime, books, or history. The MCP server already enables conversational graph growth, where a user asks an assistant to map relationships and the assistant incrementally adds nodes and edges.

**Speculative direction:** A frontend could turn KazuraDB output into an entertainment and curiosity product: “Map the relationships in this novel,” “Show factions in this history period,” or “Visualize character connections in this anime.” An LLM would extract candidate nodes and edges from natural language, KazuraDB would persist them, and the UI would render an explorable relationship diagram.

### C. Cross-user graph matching

**Actionable now:** The current model can represent each user’s graph independently if the application adds user-level database separation or graph namespace conventions.

**Speculative direction:** Compare topology overlap between user graphs to suggest connections between people. This would match users at the concept-and-relationship level, not only at the item level: closer to “these people understand similar structures” than “these people liked the same object.” A useful analogy is Last.fm-style taste matching, but generalized from music items to knowledge graphs.

## 4. Next concrete steps

1. **Actionable now: expose temporal metadata in read APIs.** The schema has explicit `created_at` and `updated_at` columns, but node and edge JSON responses do not yet include them. Add these fields to `get_node`, `get_edge`, `find_edges`, `neighbors`, and `path` outputs, then test backwards-compatible behavior.

2. **Actionable now: define a graph-native provenance convention.** Document and test a recommended pattern for `created_by`, sources, confidence, and extraction notes. Prefer edges for provenance relationships and JSON properties for scalar annotations. This gives agents a stable convention without prematurely expanding the schema.

3. **Speculative but worth prototyping: build one end-to-end demo.** Choose either the AI-agent knowledge-store flow or the personal visualization flow. Implement the smallest demo that extracts or writes facts, persists them through KazuraDB, and reads back a subgraph that is visibly useful. Use the demo to decide whether the next product investment should be agent memory, visualization, or graph matching.
