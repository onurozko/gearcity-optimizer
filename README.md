# GearCity Optimizer

A local Python/Streamlit helper for **GearCity** vehicle design. It turns vehicle
type importance ratings into practical chassis, engine, gearbox, and vehicle
body design guidance.

> The main workflow is the design checklist and Streamlit UI. Formula calculators
> and package optimization are advanced/experimental tools.

**Disclaimer:** GearCity Optimizer is an unofficial fan-made tool. It is not
affiliated with, endorsed by, sponsored by, or maintained by GearCity, Visual
Entertainment And Technologies, or any official GearCity project.

GearCity is the property of its respective owner(s). This project does not
include GearCity game assets, logos, screenshots, or original game files.

This project is intended for personal gameplay assistance and research. It only
downloads the configured wiki URLs in `sources/wiki_urls.json` and does not
redistribute raw wiki cache files by default.

## About GearCity

GearCity is a detailed automobile manufacturing business simulator where the
player designs vehicle components, builds vehicles, manages production, pricing,
factories, branches, marketing, racing, and company finances.

This project is an unofficial fan-made helper tool for GearCity. It is intended
to make vehicle design decisions easier by turning vehicle type importance
ratings and game-mechanics references into practical design guidance.

## Data and formula sources

- Vehicle type importance data comes from the [GearCity Wiki](https://wiki.gearcity.info/).
- Formula calculators are based on GearCity Wiki game-mechanics pseudo-code.
- The wiki formulas are treated as reference material and may not perfectly match
  the game internals.
- Downloaded wiki files are cached locally under `sources/`.
- Generated parser outputs are written under `generated/`.
- The project only downloads the configured URLs in `sources/wiki_urls.json`; it
  does not crawl the entire wiki.

### GearCity and reference links

- [GearCity on Steam](https://store.steampowered.com/app/285110/GearCity/)
- [GearCity official website](https://www.gearcity.info/)
- [GearCity Wiki](https://wiki.gearcity.info/)
- [Vehicle Type Importance](https://wiki.gearcity.info/doku.php?id=gamemanual:references_vehicletypeimportance)
- [Chassis Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_chassis_design)
- [Engine Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_engines_design)
- [Gearbox Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_gearboxes_design)
- [Dynamic Reports](https://wiki.gearcity.info/doku.php?id=gamemanual:gui_dynamicreports)

## What it does

- Shows vehicle-type stat priorities
- Generates practical design checklists
- Provides a local Streamlit UI
- Downloads/parses selected GearCity wiki pages
- Browses parsed formula sections
- Calculates chassis, engine, and gearbox formula outputs
- Offers experimental component/package ranking

## What it does not do

- It is not a perfect GearCity clone.
- Formula pages are wiki pseudo-code references.
- Package optimization is experimental.
- Cost formulas may use temporary proxies until exact formulas are implemented.

## Install

```bash
pip install -e ".[dev]"
```

## Fresh clone setup

A new clone includes:

- source code
- sample/reference CSV files in `data/`
- configured wiki URL list in `sources/wiki_urls.json`

A new clone does **not** include:

- generated parser outputs
- downloaded wiki cache files
- copied local GearCity game files

This is intentional. Those paths are gitignored because they are generated or
cached locally.

Main checklist usage works immediately after install:

```bash
pip install -e ".[dev]"
python -m gearcity_optimizer.cli priorities --vehicle-type Sedan
python -m gearcity_optimizer.cli design-checklist --vehicle-type Sedan --year 1901
streamlit run streamlit_app.py
```

Wiki and formula tools require local regeneration:

```bash
python -m gearcity_optimizer.cli download-wiki
python -m gearcity_optimizer.cli import-wiki
python -m gearcity_optimizer.cli inspect-sources
```

Or use the convenience bootstrap command:

```bash
python -m gearcity_optimizer.cli setup-sources
```

- `download-wiki` recreates local wiki cache folders under `sources/`.
- `import-wiki` recreates `generated/raw_parsed/` and `generated/normalized/`.
- These files are ignored by Git because they are generated/cached artifacts.
- You can safely delete `generated/` and rerun `import-wiki` (after wiki cache
  exists) to rebuild parser outputs.

## Main usage

```bash
python -m gearcity_optimizer.cli priorities --vehicle-type Sedan
python -m gearcity_optimizer.cli design-checklist --vehicle-type Sedan --year 1901
streamlit run streamlit_app.py
```

Save a checklist as Markdown:

```bash
python -m gearcity_optimizer.cli design-checklist --vehicle-type Sedan --year 1901 --output-markdown generated/reports/sedan_1901_checklist.md
```

## Wiki / formula tools

```bash
python -m gearcity_optimizer.cli download-wiki
python -m gearcity_optimizer.cli import-wiki
python -m gearcity_optimizer.cli inspect-sources
python -m gearcity_optimizer.cli formulas --page gearbox_game_mechanics --list-sections
```

## Formula calculators

```bash
python -m gearcity_optimizer.cli calc-chassis --input-file data/chassis_design_inputs.csv --year 1901
python -m gearcity_optimizer.cli calc-engines --input-file data/engine_design_inputs.csv --year 1901
python -m gearcity_optimizer.cli calc-gearboxes --input-file data/gearbox_design_inputs.csv --year 1901
```

## Experimental package optimization

Rank chassis + engine + gearbox combinations (not the primary workflow):

```bash
python -m gearcity_optimizer.cli packages --vehicle-type Sedan --year 1901 --objective formula_fit
```

Legacy finished-design ranking still works:

```bash
python -m gearcity_optimizer.cli --vehicle-type Sedan --year 1901 --objective balanced
python -m gearcity_optimizer.cli rank-designs --vehicle-type Sedan --year 1901
```

## Project structure

```
gearcity_optimizer/
  core/           Models, scoring, priorities, package optimizer
  formulas/       Chassis, engine, gearbox, assembly calculators
  reports/        Design checklists and advisor text
  importers/      Wiki download and parse
  cli/            Command-line interface
  ui/             Streamlit helpers
  formula_browser.py
  data_sources.py

data/             Editable seed/sample CSVs (committed)
generated/        Generated output; safe to delete/regenerate (gitignored)
sources/          Wiki URL config and downloaded caches
streamlit_app.py  Thin Streamlit entry point
docs/             Architecture and formula notes
```

See [docs/architecture.md](docs/architecture.md) and [docs/formulas.md](docs/formulas.md)
for more detail.

## Data folders

| Folder | Purpose |
|--------|---------|
| `data/` | Editable sample inputs; `vehicle_types.csv` is wiki-derived reference data (see [data/README.md](data/README.md)) |
| `generated/` | Parser output, formula exports, reports; regenerate anytime (gitignored) |
| `sources/` | `wiki_urls.json` plus local cached wiki downloads (cache gitignored) |

Do not commit `generated/`, cached wiki files under `sources/wiki_html/`,
`sources/wiki_raw/`, or `sources/wiki_text/`, or any local game installation
files under `sources/game_files/`.

## Assets and trademarks

- This repository does not include GearCity logos, screenshots, artwork, game
  assets, or copied game files.
- Do not commit local GearCity installation files.
- If adding screenshots later, use user-created screenshots only and consider
  whether they are appropriate to include.

## Attribution

This is an unofficial fan-made helper for GearCity. GearCity wiki pages are
downloaded only from URLs configured in `sources/wiki_urls.json` and used as
reference material. The download manifest is stored at
`generated/raw_parsed/wiki_download_manifest.json`.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [NOTICE](NOTICE) for
third-party and trademark notices.

## Development

```bash
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Source code in this repository is licensed under the [MIT License](LICENSE).

GearCity and GearCity-related names and content belong to their respective
owners. GearCity Wiki-derived content is subject to the GearCity Wiki's own
license and terms (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

Formula references and parsed data generated from the wiki should be treated as
third-party derived reference material, not as MIT-licensed original project
code. This project does not claim ownership of GearCity formulas or wiki text.
