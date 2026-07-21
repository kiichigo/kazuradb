# Layered relationship DB concept

## 1. Goal

KazuraDB should keep a very small, general-purpose relationship database at its core, then let higher layers add purpose-specific constraints, vocabularies, and user workflows. The core database should be able to store any relationship graph, while a selected schema, mode, or tool can say which node kinds, link types, required properties, and validation rules are appropriate for a specific use case such as a manga character relationship chart.

This keeps the storage model simple for agents and scripts, but gives product features a way to feel domain-specific and safe.

## 2. Layer model

```text
Layer 4: Product tools / modes
         e.g. Manga relationship-chart builder, movie cast map, research map

Layer 3: Domain schemas
         e.g. Fictional-character graph schema, citation graph schema

Layer 2: Constraint and vocabulary profiles
         e.g. allowed node kinds, allowed link types, required props, direction rules

Layer 1: Core relationship DB
         nodes + directed edges + JSON props + timestamps
```

### Layer 1: Core relationship DB

The core should remain intentionally generic:

- `nodes` store entities, concepts, labels, lightweight kinds, and JSON properties.
- `edges` store directed `source -> type -> target` facts and JSON properties.
- Relationship types are plain keys, so unknown or experimental relations can still be stored.
- Multi-edges are allowed, so alternate interpretations, time-scoped states, and conflicting facts can coexist.

The core should not know what a movie, manga character, organization, friendship, or rivalry means. It only guarantees durable graph storage and traversal.

### Layer 2: Constraint and vocabulary profiles

A profile is a reusable restriction set that sits on top of the core. It does not require new core tables at first; it can be represented as configuration, JSON, or graph nodes.

A profile can define:

- Allowed node kinds, such as `work`, `character`, `organization`, `place`, and `event`.
- Allowed link types, such as `appears_in`, `ally_of`, `enemy_of`, `family_of`, `member_of`, and `loves`.
- Direction conventions, such as `character -> appears_in -> work`.
- Symmetry rules, such as `ally_of` and `sibling_of` being conceptually bidirectional.
- Cardinality hints, such as a character may have many works but one primary current faction.
- Required edge properties, such as `source_ref`, `confidence`, `evidence_text`, `chapter`, or `episode`.
- Display hints, such as color, line style, label text, and whether a link should appear in default diagrams.

Profiles should be advisory at first and can become enforceable later. For example, a CLI or MCP tool can warn about invalid edges before the database itself rejects them.

### Layer 3: Domain schemas

A domain schema combines one or more profiles into a named domain. It is closer to a product contract than a low-level database schema.

Example: `fictional_relationship_schema` could define:

```json
{
  "id": "fictional_relationship_schema",
  "node_kinds": ["work", "character", "group", "place", "event"],
  "link_types": {
    "appears_in": {
      "from": ["character"],
      "to": ["work"],
      "required_props": ["evidence"]
    },
    "ally_of": {
      "from": ["character", "group"],
      "to": ["character", "group"],
      "symmetric": true,
      "display": {"line": "solid", "color": "green"}
    },
    "enemy_of": {
      "from": ["character", "group"],
      "to": ["character", "group"],
      "symmetric": true,
      "display": {"line": "solid", "color": "red"}
    },
    "family_of": {
      "from": ["character"],
      "to": ["character"],
      "symmetric": true,
      "required_props": ["relation_detail"]
    },
    "belongs_to": {
      "from": ["character"],
      "to": ["group"],
      "required_props": ["status"]
    }
  }
}
```

This schema gives agents and UI code a shared vocabulary without making the core database fiction-specific.

### Layer 4: Product tools and modes

A tool or mode is the user-facing layer. It chooses a domain schema, adds workflow rules, and exposes only the operations that make sense for a task.

For a manga relationship-chart mode, the mode might provide:

- Natural-language import: “extract the characters and relationships from this chapter summary.”
- Guided editing: only show character, group, place, and event node types.
- Relationship palettes: ally, enemy, family, love interest, mentor, subordinate, same organization, and hidden identity.
- Evidence prompts: ask the user or agent for chapter, episode, page, or quote references.
- Visualization defaults: red enemy edges, green ally edges, dashed uncertain edges, grouped nodes by faction.
- Export views: “main cast only,” “spoiler-free until volume 3,” or “show all factions.”

In this sense, a mode is not only a schema. It is a bundled experience: schema + validation + prompts + UI defaults + export behavior.

## 3. Example: manga relationship-chart mode

### Core data

The underlying graph remains ordinary KazuraDB data:

```bash
kazura add-node work:one-piece --kind work --label "One Piece"
kazura add-node character:luffy --kind character --label "Monkey D. Luffy"
kazura add-node group:straw-hats --kind group --label "Straw Hat Pirates"
kazura add-edge character:luffy appears_in work:one-piece --props '{"evidence":"main character"}'
kazura add-edge character:luffy belongs_to group:straw-hats --props '{"status":"captain"}'
```

### Schema interpretation

The manga mode interprets that graph through its selected domain schema:

- `character:luffy` is valid because `character` is an allowed node kind.
- `appears_in` is valid from `character` to `work`.
- `belongs_to` is valid from `character` to `group` and should include a `status` property.
- A UI can render `belongs_to` as a faction or group-membership relationship.

### Tool behavior

A higher-level `manga-chart` tool could expose commands such as:

```bash
kazura manga-chart import-summary --work work:one-piece summary.md
kazura manga-chart add-relationship character:luffy group:straw-hats --type belongs_to --status captain
kazura manga-chart export --work work:one-piece --view spoiler-free --until-volume 3
```

Internally, those commands still write normal nodes and edges. The mode simply constrains input and shapes output.

## 4. Suggested implementation path

1. **Document schema profiles first.** Define a JSON shape for profiles and a few example profiles without changing the database.
2. **Add validation helpers.** Implement functions that validate proposed nodes and edges against a profile, returning warnings or errors.
3. **Expose profile-aware tools.** Add optional CLI or MCP operations that accept `schema_id` or `mode_id` and validate writes before storing them.
4. **Represent schemas in the graph when useful.** Store schema definitions as nodes such as `schema:fictional_relationship` and link types as `relation_type:*` nodes when agents need to inspect or modify them.
5. **Build one vertical mode.** Start with a manga or movie relationship-chart mode because it is visual, easy to test, and demonstrates the value of constrained link types.

## 5. Naming proposal

Use three separate names so the architecture stays clear:

- **Core graph:** the raw relationship database that stores nodes and edges.
- **Schema profile:** a reusable vocabulary and validation layer for a domain.
- **Mode/tool:** a user-facing workflow that chooses a schema profile and adds prompts, commands, UI defaults, and exports.

This separation lets KazuraDB stay small while still supporting specialized experiences such as manga character maps, movie relationship diagrams, agent memory graphs, and research knowledge maps.
