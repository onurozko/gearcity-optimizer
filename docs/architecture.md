# Architecture

> GearCity Optimizer is organized around converting GearCity vehicle type
> priorities into actionable design guidance.

GearCity Optimizer is a small Python package that turns vehicle type importance
ratings into practical design guidance, with optional formula calculators and
experimental package ranking.

## Package layout

```
gearcity_optimizer/
  core/           Models, scoring, component priorities, package optimizer
  formulas/       Wiki-based chassis, engine, gearbox, assembly calculators
  reports/        Design checklists and advisor commentary
  importers/      Wiki download and parse pipeline
  cli/            Command-line interface
  ui/             Streamlit helpers
  formula_browser.py
  data_sources.py Default paths to data/, generated/, sources/
```

Root-level folders:

- `data/`: editable seed/sample CSV inputs
- `generated/`: parser output, formula exports, reports (safe to delete)
- `sources/`: configured source references and local cached wiki downloads

`sources/` contains configured source references (`wiki_urls.json`) and local
cached downloads from the GearCity Wiki. Cached wiki pages under
`sources/wiki_html/`, `sources/wiki_raw/`, and `sources/wiki_text/`, plus
generated parser outputs under `generated/`, are excluded from Git.

## Main flow: design guidance

```
vehicle_types.csv
    -> get_adjusted_vehicle_weights()
    -> calculate_component_priorities()
    -> build_design_checklist()
    -> CLI or Streamlit UI
```

The checklist is deterministic: it ranks final vehicle stats and maps component
priorities to chassis, engine, gearbox, and vehicle body focus bullets.

## Optional flow: formulas and packages

```
design input CSVs (data/*_design_inputs.csv)
    -> calculate_chassis / calculate_engine / calculate_gearbox
    -> generated/normalized/*_candidates_from_formulas.csv
    -> rank_component_packages() (experimental)
```

Assembly scoring (`vehicle_assembly_formula.py`) combines component stats into
vehicle ratings for formula-backed package ranking.

## Wiki pipeline

```
sources/wiki_urls.json
    -> download-wiki -> sources/wiki_html, sources/wiki_raw
    -> import-wiki -> generated/raw_parsed/*.json
    -> formulas CLI / formula_browser.py
```

Wiki pages are reference material only. Parsed pseudo-code feeds the formula
modules and browser; it is not a full game simulation.

## CLI entry points

- `python -m gearcity_optimizer.cli`: module entry (`cli/__main__.py`)
- `gearcity-optimizer`: console script (`pyproject.toml`)

Both call `gearcity_optimizer.cli.main.main()`.
