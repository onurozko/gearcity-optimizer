# Data files

## Reference data

`vehicle_types.csv` is reference data derived from the GearCity Wiki
[Vehicle Type Importance](https://wiki.gearcity.info/doku.php?id=gamemanual:references_vehicletypeimportance)
table. It is included as editable reference data for local use.

## Sample and user inputs

Other CSV files in this folder are sample or user-editable inputs for the tool,
such as candidate designs and formula design inputs.

## Regenerating wiki-derived data

You can refresh wiki-derived outputs locally with:

```bash
python -m gearcity_optimizer.cli download-wiki
python -m gearcity_optimizer.cli import-wiki
```

Parsed wiki output is written under `generated/`. Cached wiki downloads are
stored under `sources/wiki_html/`, `sources/wiki_raw/`, and `sources/wiki_text/`.
Those paths are gitignored and should not be committed.
