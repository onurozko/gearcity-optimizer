# Contributing

Thanks for helping improve GearCity Optimizer.

## Setup

```bash
pip install -e ".[dev]"
```

## Run tests

```bash
pytest
```

## Run the UI locally

```bash
pip install -e ".[dev]"
streamlit run streamlit_app.py
```

## Generated and cached files

Do not commit files under `generated/` or downloaded wiki caches under
`sources/wiki_html/`, `sources/wiki_raw/`, or `sources/wiki_text/`.

Do not commit local GearCity installation files under `sources/game_files/`.

Keep editable sample data in `data/` and wiki URL configuration in
`sources/wiki_urls.json`.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution guidance.

## Scope

This project focuses on practical vehicle design guidance. Avoid large feature
expansions in cleanup PRs; prefer focused changes with tests.
