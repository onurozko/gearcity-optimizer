"""Extract actual and predicted replay metric values for save calibration."""

from __future__ import annotations

from gearcity_optimizer.importers.save_db import SaveEngineRecord, SaveGearboxRecord
from gearcity_optimizer.prediction.backend import SaveEnginePrediction, SaveGearboxPrediction


def engine_actual_value(record: SaveEngineRecord, metric: str) -> float:
    mapping = {
        "length": record.length_in,
        "width": record.width_in,
        "weight": record.weight_lb,
        "torque": record.torque_lbft,
        "horsepower": record.horsepower,
        "power_rating": record.engine_power_rating,
        "fuel_rating": record.engine_fuel_rating,
        "reliability_rating": record.engine_reliability_rating,
        "overall_rating": record.overall_rating,
    }
    return float(mapping[metric])


def engine_predicted_value(prediction: SaveEnginePrediction, metric: str) -> float:
    result = prediction.predicted
    mapping = {
        "length": result.length,
        "width": result.width,
        "weight": result.weight,
        "torque": result.torque,
        "horsepower": result.horsepower,
        "power_rating": result.performance_rating,
        "fuel_rating": result.fuel_economy,
        "reliability_rating": result.reliability_rating,
        "overall_rating": result.overall_rating,
    }
    return float(mapping[metric])


def gearbox_actual_value(record: SaveGearboxRecord, metric: str) -> float:
    mapping = {
        "max_torque": record.max_torque_input_lbft,
        "weight": record.weight_lb,
        "power_rating": record.power_rating,
        "fuel_rating": record.fuel_rating,
        "performance_rating": record.performance_rating,
        "reliability_rating": record.reliability_rating,
        "overall_rating": record.overall_rating,
    }
    return float(mapping[metric])


def gearbox_predicted_value(prediction: SaveGearboxPrediction, metric: str) -> float:
    result = prediction.predicted
    if metric == "max_torque":
        return float(prediction.max_torque_support)
    mapping = {
        "weight": result.weight,
        "power_rating": result.power_rating,
        "fuel_rating": result.fuel_economy_rating,
        "performance_rating": result.performance_rating,
        "reliability_rating": result.reliability_rating,
        "overall_rating": result.overall_rating,
    }
    return float(mapping[metric])
