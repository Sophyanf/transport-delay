import pandas as pd
import pytest
from transport_features import FEATURE_SET_V1, build_features

BASE_TIME = pd.Timestamp("2025-01-15T10:00:00Z")


# Создаёт синтетическую телеметрию до момента прогноза.
def create_test_traffic() -> pd.DataFrame:
    times = pd.date_range(
        end=BASE_TIME,
        periods=20,
        freq="15s",
    )
    return pd.DataFrame(
        {
            "tr_id": "1",
            "event_time": times,
            "speed": [20.0] * 10 + [10.0] * 10,
            # Исправлено: применяем смещение к каждому индексу через list comprehension
            "lon": [37.6 + 0.0001 * i for i in range(20)],
            "lat": 55.75,
            "alt": 150.0,
            "heading": 90.0,
            "location_valid": True,
            "is_hist_data": False,
        }
    )


# Создаёт синтетическое расписание с WKT-остановками.
def create_test_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tr_id": ["1", "1", "1"],
            "tt_action_item_id": ["stop-1", "stop-2", "stop-3"],
            "time_begin": [
                BASE_TIME - pd.Timedelta(minutes=5),
                BASE_TIME + pd.Timedelta(minutes=12),
                BASE_TIME + pd.Timedelta(minutes=20),
            ],
            "geom": [
                "POINT (37.61 55.75)",
                "POINT (37.62 55.755)",
                "POINT (37.63 55.76)",
            ],
        }
    )


# Создаёт одну прогнозную точку.
def create_test_points() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["sample-1"],
            "tr_id": ["1"],
            "T": [BASE_TIME],
            "target_stop_id": ["stop-2"],
            "target_time_begin": [BASE_TIME + pd.Timedelta(minutes=12)],
            "cur_dev_s": [45.0],
        }
    )


# Проверяет полноту и порядок признаков результата.
def test_build_features_returns_full_feature_set() -> None:
    frame = build_features(
        create_test_points(),
        create_test_traffic(),
        create_test_schedule(),
    )
    expected = ["sample_id", *FEATURE_SET_V1.feature_names, "last_lon", "last_lat"]
    assert list(frame.columns) == expected
    assert len(frame) == 1


# Проверяет расчёт ключевых значений признаков.
def test_build_features_computes_core_values() -> None:
    features = build_features(
        create_test_points(),
        create_test_traffic(),
        create_test_schedule(),
    ).iloc[0]
    assert features["cur_dev_s"] == 45.0
    assert features["horizon_s"] == 720.0
    assert features["telemetry_age_s"] == 0.0
    assert features["last_speed"] == 10.0
    assert features["distance_to_target_m"] > 0
    assert features["required_speed_kmh"] > 0
    assert features["target_stop_sequence"] == 1.0
    assert features["previous_stop_gap_s"] == 1020.0


# Проверяет корректную работу при отсутствии телеметрии.
def test_build_features_survives_empty_traffic() -> None:
    empty_traffic = create_test_traffic().iloc[0:0]
    features = build_features(
        create_test_points(),
        empty_traffic,
        create_test_schedule(),
    ).iloc[0]
    assert features["packet_count_5m"] == 0.0
    # Проверка на NaN: сравнение NaN != NaN всегда True
    assert features["last_speed"] != features["last_speed"]


# Проверяет запрет дубликатов прогнозных точек.
def test_build_features_rejects_duplicate_samples() -> None:
    points = pd.concat(
        [create_test_points(), create_test_points()],
        ignore_index=True,
    )
    with pytest.raises(ValueError):
        build_features(points, create_test_traffic(), create_test_schedule())
