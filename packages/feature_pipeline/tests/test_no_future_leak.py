import pandas as pd
from test_builder import (
    BASE_TIME,
    create_test_points,
    create_test_schedule,
    create_test_traffic,
)
from transport_features import build_features


# Проверяет устойчивость признаков к будущей телеметрии.
def test_future_traffic_does_not_change_features() -> None:
    points = create_test_points()
    traffic_before = create_test_traffic()
    features_clean = build_features(
        points,
        traffic_before,
        create_test_schedule(),
    )

    future_row = pd.DataFrame(
        {
            "tr_id": ["1"],
            "event_time": [BASE_TIME + pd.Timedelta(minutes=5)],
            "speed": [0.0],
            "lon": [37.7],
            "lat": [55.8],
            "alt": [150.0],
            "heading": [0.0],
            "location_valid": [True],
            "is_hist_data": [False],
        }
    )
    traffic_polluted = pd.concat(
        [traffic_before, future_row],
        ignore_index=True,
    )
    features_polluted = build_features(
        points,
        traffic_polluted,
        create_test_schedule(),
    )

    pd.testing.assert_frame_equal(features_clean, features_polluted)
