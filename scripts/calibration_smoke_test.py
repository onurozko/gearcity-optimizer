"""Batch calibration smoke test across real save files."""

from __future__ import annotations

import sys
from pathlib import Path

from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_features import (
    delta_map,
    engine_fit_max_pct,
    fuel_family,
)

ROOT = Path(__file__).resolve().parents[1]
SAVES = [
    ROOT / "boloverse-lowbranch-1930.db",
    ROOT / "1913-First Insane Run.db",
]


def _pct(deltas: tuple, metric: str) -> float | None:
    for delta in deltas:
        if delta.metric == metric:
            return delta.pct_error
    return None


def summarize_save(path: Path, *, apply_corrections: bool) -> dict[str, object]:
    label = "defaults" if apply_corrections else "raw"
    report = calibrate_save_game(
        str(path),
        company_id=0,
        engine_limit=None,
        gearbox_limit=None,
        apply_corrections=apply_corrections,
    )
    gas = [
        item
        for item in report.engines
        if fuel_family(item.record.fuel_type) == "gasoline"
    ]
    fit_ok = sum(1 for item in gas if engine_fit_max_pct(item) <= 5.0)
    tq_ok = sum(
        1 for item in gas if (_pct(item.deltas, "torque_lbft") or 999.0) <= 10.0
    )
    gb_ok = sum(
        1
        for item in report.gearboxes
        if (_pct(item.deltas, "max_torque_lbft") or 999.0) <= 10.0
    )
    worst_gas = sorted(gas, key=engine_fit_max_pct, reverse=True)[:3]
    worst_gb = sorted(
        report.gearboxes,
        key=lambda item: _pct(item.deltas, "max_torque_lbft") or 0.0,
        reverse=True,
    )[:3]
    return {
        "save": path.name,
        "mode": label,
        "gas_count": len(gas),
        "gb_count": len(report.gearboxes),
        "fit_ok": fit_ok,
        "tq_ok": tq_ok,
        "gb_ok": gb_ok,
        "worst_gas": worst_gas,
        "worst_gb": worst_gb,
    }


def main() -> int:
    missing = [path for path in SAVES if not path.exists()]
    if missing:
        print("Missing saves:", ", ".join(path.name for path in missing))
        return 1

    failures: list[str] = []
    for path in SAVES:
        for apply_corrections in (False, True):
            result = summarize_save(path, apply_corrections=apply_corrections)
            print(
                f"\n{result['save']} [{result['mode']}] "
                f"gas fit<=5%: {result['fit_ok']}/{result['gas_count']} | "
                f"gas tq<=10%: {result['tq_ok']}/{result['gas_count']} | "
                f"gb max_tq<=10%: {result['gb_ok']}/{result['gb_count']}"
            )
            for item in result["worst_gas"]:
                record = item.record
                deltas = delta_map(item.deltas)
                print(
                    f"  worst gas id={record.engine_id} {record.layout}/"
                    f"{record.valve} mod={record.mod_amount} "
                    f"fit={engine_fit_max_pct(item):.1f}% "
                    f"tq={deltas.get('torque_lbft') or 0:.1f}%"
                )
            for item in result["worst_gb"]:
                record = item.record
                deltas = delta_map(item.deltas)
                print(
                    f"  worst gb id={record.gearbox_id} {record.gears}g mod={record.mod_amount} "
                    f"max_tq={deltas.get('max_torque_lbft') or 0:.1f}%"
                )

        raw = summarize_save(path, apply_corrections=False)
        defaults = summarize_save(path, apply_corrections=True)
        if path.name.startswith("boloverse"):
            if defaults["tq_ok"] < raw["tq_ok"]:
                failures.append(f"{path.name}: defaults worse on torque than raw")
            if defaults["gb_ok"] < raw["gb_ok"]:
                failures.append(f"{path.name}: defaults worse on gearbox torque than raw")

    if failures:
        print("\nREGRESSIONS:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("\nBatch smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
