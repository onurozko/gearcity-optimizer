"""Stable design keys, deduplication, and train/test splits for save holdout."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

SPLIT_MODE_EXPLICIT = "explicit_train_test"
SPLIT_MODE_SINGLE_SAVE = "single_save_row_split"
SPLIT_MODE_SAVES_DIR = "saves_dir_row_split"


def collect_save_paths_recursive(save_dir: str | Path) -> list[Path]:
    """Collect .db files directly under a directory and one level of subfolders."""
    root = Path(save_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Save directory not found: {root}")

    paths: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(path)

    for path in sorted(root.glob("*.db")):
        add(path)
    for path in sorted(root.glob("*/*.db")):
        add(path)

    return paths


def canonical_design_key(
    *,
    kind: str,
    company_id: object,
    design_id: object,
    name: object,
    year: object,
) -> str:
    """Stable per-row design identity for holdout splitting."""
    return "|".join(
        [
            str(kind),
            str(company_id),
            str(design_id),
            str(name or ""),
            str(year or ""),
        ]
    )


def cross_save_dedup_key(row: pd.Series) -> str:
    """Hash-like key for deduplicating the same design across multiple saves."""
    if row["kind"] == "engine":
        parts = [
            str(row["kind"]),
            str(row.get("company_id", "")),
            str(row.get("name", "")),
            str(row.get("year", "")),
            str(row.get("layout", "")),
            str(row.get("fuel_type", "")),
            str(row.get("cylinders", "")),
            str(row.get("induction", "")),
            str(row.get("valve", "")),
            str(row.get("displacement", "")),
        ]
    else:
        parts = [
            str(row["kind"]),
            str(row.get("company_id", "")),
            str(row.get("name", "")),
            str(row.get("year", "")),
            str(row.get("gears", "")),
            str(row.get("gearbox_type", "")),
            str(row.get("reverse", "")),
            str(row.get("overdrive", "")),
        ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def add_design_keys(engine_df: pd.DataFrame, gearbox_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach canonical and dedup keys to dataset frames."""
    engine_out = engine_df.copy()
    gearbox_out = gearbox_df.copy()
    if not engine_out.empty:
        engine_out["design_key"] = engine_out.apply(
            lambda row: canonical_design_key(
                kind="engine",
                company_id=row.get("company_id", ""),
                design_id=row["design_id"],
                name=row.get("name", ""),
                year=row.get("year", ""),
            ),
            axis=1,
        )
        engine_out["dedup_key"] = engine_out.apply(cross_save_dedup_key, axis=1)
    if not gearbox_out.empty:
        gearbox_out["design_key"] = gearbox_out.apply(
            lambda row: canonical_design_key(
                kind="gearbox",
                company_id=row.get("company_id", ""),
                design_id=row["design_id"],
                name=row.get("name", ""),
                year=row.get("year", ""),
            ),
            axis=1,
        )
        gearbox_out["dedup_key"] = gearbox_out.apply(cross_save_dedup_key, axis=1)
    return engine_out, gearbox_out


def dedupe_design_frames(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Drop duplicate designs, keeping the first occurrence per dedup key."""
    engine_out, gearbox_out = add_design_keys(engine_df, gearbox_df)
    removed = 0
    if not engine_out.empty:
        before = len(engine_out)
        engine_out = engine_out.drop_duplicates(subset=["dedup_key"], keep="first")
        removed += before - len(engine_out)
    if not gearbox_out.empty:
        before = len(gearbox_out)
        gearbox_out = gearbox_out.drop_duplicates(subset=["dedup_key"], keep="first")
        removed += before - len(gearbox_out)
    return engine_out, gearbox_out, removed


def split_dedup_keys(
    keys: list[str],
    *,
    split_ratio: float,
    seed: int,
) -> tuple[set[str], set[str]]:
    """Split dedup keys into train/test sets with a stable seeded hash."""
    if not keys:
        return set(), set()
    if not 0.0 < split_ratio < 1.0:
        raise ValueError("split_ratio must be between 0 and 1.")

    train: set[str] = set()
    test: set[str] = set()
    for key in sorted(keys):
        digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        if bucket < split_ratio:
            train.add(key)
        else:
            test.add(key)

    if not train or not test:
        ordered = sorted(keys)
        split_index = max(1, int(len(ordered) * split_ratio))
        split_index = min(split_index, len(ordered) - 1) if len(ordered) > 1 else split_index
        train = set(ordered[:split_index])
        test = set(ordered[split_index:])
        if not test and ordered:
            test = {ordered[-1]}
            train.discard(ordered[-1])

    return train, test


def split_design_frames(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    split_ratio: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, int, set[str], set[str]]:
    """Deduplicate designs and split rows into train/test frames."""
    engine_deduped, gearbox_deduped, duplicates_removed = dedupe_design_frames(engine_df, gearbox_df)
    keys: list[str] = []
    if not engine_deduped.empty:
        keys.extend(engine_deduped["dedup_key"].astype(str).tolist())
    if not gearbox_deduped.empty:
        keys.extend(gearbox_deduped["dedup_key"].astype(str).tolist())
    unique_keys = sorted(set(keys))
    train_keys, test_keys = split_dedup_keys(unique_keys, split_ratio=split_ratio, seed=seed)

    train_engine = (
        engine_deduped[engine_deduped["dedup_key"].isin(train_keys)]
        if not engine_deduped.empty
        else engine_deduped
    )
    test_engine = (
        engine_deduped[engine_deduped["dedup_key"].isin(test_keys)]
        if not engine_deduped.empty
        else engine_deduped
    )
    train_gearbox = (
        gearbox_deduped[gearbox_deduped["dedup_key"].isin(train_keys)]
        if not gearbox_deduped.empty
        else gearbox_deduped
    )
    test_gearbox = (
        gearbox_deduped[gearbox_deduped["dedup_key"].isin(test_keys)]
        if not gearbox_deduped.empty
        else gearbox_deduped
    )
    return (
        train_engine,
        test_engine,
        train_gearbox,
        test_gearbox,
        duplicates_removed,
        train_keys,
        test_keys,
    )


def train_test_overlap(train_keys: set[str], test_keys: set[str]) -> set[str]:
    """Return overlapping dedup keys between train and test."""
    return train_keys & test_keys
