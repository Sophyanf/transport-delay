from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSet:
    name: str
    version: str
    feature_names: tuple[str, ...]


class FeatureSetRegistry:
    # Создаёт пустой реестр наборов признаков.
    def __init__(self) -> None:
        self._items: dict[str, FeatureSet] = {}

    # Регистрирует новый набор признаков.
    def register(self, feature_set: FeatureSet) -> None:
        if feature_set.name in self._items:
            raise ValueError(f"Feature set already exists: {feature_set.name}")
        self._items[feature_set.name] = feature_set

    # Возвращает набор признаков по имени.
    def get(self, name: str) -> FeatureSet:
        try:
            return self._items[name]
        except KeyError as error:
            raise KeyError(f"Unknown feature set: {name}") from error

    # Возвращает имена зарегистрированных наборов.
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


FEATURE_SET_V1 = FeatureSet(
    name="feature_set_v1",
    version="1.0.0",
    feature_names=(
        "cur_dev_s",
        "horizon_s",
        "hour",
        "minute",
        "day_of_week",
        "is_weekend",
        "seconds_from_midnight",
        "telemetry_age_s",
        "last_speed",
        "last_heading",
        "last_altitude",
        "last_location_valid",
        "last_is_historical",
        "last_receive_lag_s",
        "packet_count_1m",
        "packet_count_3m",
        "packet_count_5m",
        "packet_count_10m",
        "packet_count_15m",
        "speed_mean_1m",
        "speed_mean_3m",
        "speed_mean_5m",
        "speed_mean_10m",
        "speed_mean_15m",
        "speed_median_5m",
        "speed_min_5m",
        "speed_max_5m",
        "speed_std_5m",
        "speed_trend_5m",
        "speed_change_1m",
        "speed_change_3m",
        "stopped_ratio_1m",
        "stopped_ratio_5m",
        "invalid_location_ratio_5m",
        "historical_packet_ratio_5m",
        "receive_lag_mean_5m",
        "max_packet_gap_5m",
        "distance_travelled_5m",
        "coordinate_speed_5m",
        "distance_to_target_m",
        "required_speed_kmh",
        "speed_to_required_ratio",
        "eta_delay_s",
        "previous_stop_gap_s",
        "next_stop_gap_s",
        "target_stop_sequence",
    ),
)


# Создаёт реестр стандартных наборов признаков.
def create_feature_registry() -> FeatureSetRegistry:
    registry = FeatureSetRegistry()
    registry.register(FEATURE_SET_V1)
    return registry
