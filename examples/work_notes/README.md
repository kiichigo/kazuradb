# work_notes profile example

This directory demonstrates a small declarative profile layered on top of the generic `GraphDB` model.

The core graph database remains generic: nodes still have keys, labels, kinds, and JSON properties, while edges remain directed `source -> type -> target` records. The profile adds an optional validation layer that constrains the shape of allowed graph data before it is written or exchanged.

The profile does not prove factual truth. It can catch structurally invalid edges, such as `concept created work`, but it cannot prove that a specific person really created a specific work. Treat it as schema validation for graph shape, not as fact checking.

This is a proof of concept for domain packs or schema packs: a domain can ship a small YAML file that says which node kinds and edge shapes are valid, while the underlying graph store stays reusable across domains.

## Sample graph

Nodes:

- `author_a`: `person`
- `composer_b`: `person`
- `studio_c`: `organization`
- `sky_castle`: `work`
- `levitation_stone`: `concept`
- `flying_city`: `concept`

Edges:

- `author_a created sky_castle`
- `composer_b composed_music_for sky_castle`
- `studio_c produced sky_castle`
- `sky_castle features levitation_stone`
- `sky_castle features flying_city`
- `levitation_stone related_to flying_city`
