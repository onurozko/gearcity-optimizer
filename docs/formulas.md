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

## Rating layers

GearCity uses several related but different rating concepts. This project keeps
them separate on purpose:

- **Component formula pages** (chassis, engine, gearbox game mechanics) calculate
  component stats such as engine reliability, chassis durability, and gearbox
  reliability.
- **Vehicle Game Mechanics** combines assembled components into **final vehicle
  stats** such as `Rating_Drivability`, `Rating_Dependability`, `Rating_Quality`,
  and `Rating_Overall`.
- **Vehicle type importance weights** (from `vehicle_types.csv` and the vehicle
  type importance wiki page) decide how much each final vehicle stat matters for
  buyers of that vehicle class.
- **Dynamic Reports / buyer rating** uses final vehicle stats plus company,
  branch, price, and market factors.

Therefore **engine reliability**, **chassis durability**, and **gearbox
reliability** are related to but not identical to **final vehicle
dependability**. Component overall ratings and final vehicle overall ratings are
broad summaries and should not be treated as dependability either.

The GearCity wiki formulas use `Driveability` / `Rating_Drivability` for the
final vehicle stat. Chassis steering/handling subcomponent values feed into this
rating. Some in-game screens may display Handling, but this tool uses Driveability
as the formula-backed label.

See `gearcity_optimizer/core/terminology.py` for the terminology and layer
mappings used in the Streamlit UI.

## Implemented formula modules

| Module | Wiki source | Purpose |
|--------|-------------|---------|
| `formulas/chassis_formula.py` | Chassis Game Mechanics | Dimensions, ratings, requirements |
| `formulas/engine_formula.py` | Engine Game Mechanics | Horsepower, torque, ratings, requirements |
| `formulas/gearbox_formula.py` | Gearbox Game Mechanics | Torque support, weight, ratings, requirements |
| `formulas/vehicle_assembly_formula.py` | Vehicle Game Mechanics (partial), Dynamic Reports (partial) | Combine components into final vehicle ratings for package scoring |

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
