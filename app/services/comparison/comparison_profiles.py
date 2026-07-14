from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonWeightProfile:
    mode: str
    display_name: str
    flyable_hour_count_weight: float
    max_continuous_flyable_hours_weight: float
    earliest_flyable_time_weight: float
    window_quality_weight: float


COMPARISON_WEIGHT_PROFILES: dict[str, ComparisonWeightProfile] = {
    "default": ComparisonWeightProfile(
        mode="default",
        display_name="默认模式",
        flyable_hour_count_weight=0.30,
        max_continuous_flyable_hours_weight=0.30,
        earliest_flyable_time_weight=0.20,
        window_quality_weight=0.20,
    ),
    "fast_dispatch": ComparisonWeightProfile(
        mode="fast_dispatch",
        display_name="快速执行模式",
        flyable_hour_count_weight=0.20,
        max_continuous_flyable_hours_weight=0.20,
        earliest_flyable_time_weight=0.40,
        window_quality_weight=0.20,
    ),
    "stable_execution": ComparisonWeightProfile(
        mode="stable_execution",
        display_name="稳定执行模式",
        flyable_hour_count_weight=0.20,
        max_continuous_flyable_hours_weight=0.40,
        earliest_flyable_time_weight=0.10,
        window_quality_weight=0.30,
    ),
}


def get_comparison_weight_profile(mode: str = "default") -> ComparisonWeightProfile:
    normalized_mode = (mode or "default").strip().lower()
    return COMPARISON_WEIGHT_PROFILES.get(normalized_mode, COMPARISON_WEIGHT_PROFILES["default"])
