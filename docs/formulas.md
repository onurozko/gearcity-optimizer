# Formulas

Formula modules are based on the **GearCity Wiki** game-mechanics pages listed
in `sources/wiki_urls.json`. The wiki describes these formulas as pseudo-code
and reference material. Useful for understanding mechanics, but not guaranteed
to match the game's internal implementation exactly.

Treat all formula output as planning guidance, not authoritative in-game values.

Formula implementations are based on GearCity Wiki pseudo-code and reference
formulas. They may not perfectly match the game's internal implementation. This
project does not claim ownership over GearCity formulas or wiki text.

The MIT license applies to this project's source code only, not to GearCity or
GearCity Wiki content.

## Implemented formula modules

| Module | Wiki source | Purpose |
|--------|-------------|---------|
| `formulas/chassis_formula.py` | Chassis Game Mechanics | Dimensions, ratings, requirements |
| `formulas/engine_formula.py` | Engine Game Mechanics | Horsepower, torque, ratings, requirements |
| `formulas/gearbox_formula.py` | Gearbox Game Mechanics | Torque support, weight, ratings, requirements |
| `formulas/vehicle_assembly_formula.py` | Dynamic Reports (partial) | Combine components into vehicle ratings for package scoring |

## Data sources

- Parsed wiki sections: `generated/raw_parsed/wiki_formula_index.json`
- Sample inputs: `data/gearbox_design_inputs.csv`, `data/chassis_design_inputs.csv`, `data/engine_design_inputs.csv`
- Formula exports: `generated/normalized/*_candidates_from_formulas.csv`

## Exact vs approximate areas

**Generally faithful to wiki structure**

- Gearbox max torque support from gear count
- Chassis dimension and weight formulas with year factors
- Rating sliders mapped from wiki design-focus concepts

**Approximate or proxy**

- Some engine smoothness/reliability interactions (documented in module docstrings)
- Package `unit_cost` when CSV cost is zero (proxy for value scoring only)
- Buyer rating proxy in assembly formula (planning aid, not exact game output)

## CLI calculators

```bash
python -m gearcity_optimizer.cli calc-gearboxes --input-file data/gearbox_design_inputs.csv --year 1901
python -m gearcity_optimizer.cli calc-chassis --input-file data/chassis_design_inputs.csv --year 1901
python -m gearcity_optimizer.cli calc-engines --input-file data/engine_design_inputs.csv --year 1901
```

Re-run `download-wiki` and `import-wiki` after wiki URL or parser changes.

## Attribution

Wiki pages are downloaded only from URLs listed in `sources/wiki_urls.json`.
The download manifest is written to `generated/raw_parsed/wiki_download_manifest.json`.

See also the [GearCity Wiki](https://wiki.gearcity.info/) and the configured
page URLs in `sources/wiki_urls.json`.
