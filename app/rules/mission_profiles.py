from dataclasses import dataclass

"""
规则配置模块。

职责：
1. 定义逐小时判断所需阈值结构。
2. 定义预警修正规则结构。
3. 为不同任务类型提供独立规则模板。

使用方式：
- 业务函数不要再写死阈值。
- 统一通过 `get_mission_rule_profile(task_type)` 读取当前任务类型配置。
"""


@dataclass(frozen=True)
class HourlyRuleThresholds:
    # 这些天气现象一旦出现，直接按禁飞处理。
    prohibited_weather_texts: frozenset[str]
    # 这些天气现象在未触发禁飞时，按慎飞处理。
    caution_weather_texts: frozenset[str]

    # 禁飞阈值：达到或超过即判禁飞。
    prohibited_precip_mm: float
    prohibited_pop_percent: float
    prohibited_wind_speed_ms: float
    prohibited_wind_scale_upper: int

    # 慎飞阈值：仅在未触发禁飞时生效。
    caution_precip_min_mm: float
    caution_precip_max_mm: float
    caution_pop_min_percent: float
    caution_pop_max_percent: float
    caution_wind_speed_min_ms: float
    caution_wind_speed_max_ms: float
    caution_wind_scale_upper: int
    caution_humidity_percent: float


@dataclass(frozen=True)
class WarningRuleThresholds:
    # 只有这些高风险预警事件会参与规则修正。
    high_risk_warning_types: frozenset[str]
    # 橙色/红色：直接整段禁飞。
    force_prohibited_levels: frozenset[str]
    # 黄色：仅将原本适飞的小时升级为慎飞。
    upgrade_to_caution_levels: frozenset[str]


@dataclass(frozen=True)
class MissionRuleProfile:
    # 任务类型唯一标识，例如 cruise / hover / inspection / survey。
    task_type: str
    # 面向文档或界面展示的任务类型名称。
    display_name: str
    # 逐小时天气判断阈值集合。
    hourly: HourlyRuleThresholds
    # 预警修正规则集合。
    warning: WarningRuleThresholds


COMMON_WARNING_RULES = WarningRuleThresholds(
    high_risk_warning_types=frozenset({"雷电", "雷雨大风", "暴雨", "大风", "强对流", "短时强降水", "大雾"}),
    force_prohibited_levels=frozenset({"orange", "red"}),
    upgrade_to_caution_levels=frozenset({"yellow"}),
)


MISSION_RULE_PROFILES: dict[str, MissionRuleProfile] = {
    "cruise": MissionRuleProfile(
        task_type="cruise",
        display_name="巡航",
        hourly=HourlyRuleThresholds(
            prohibited_weather_texts=frozenset({"雷阵雨", "雷雨", "大雨", "暴雨"}),
            caution_weather_texts=frozenset({"小雨", "阴"}),
            prohibited_precip_mm=0.3,
            prohibited_pop_percent=70,
            prohibited_wind_speed_ms=10,
            prohibited_wind_scale_upper=4,
            caution_precip_min_mm=0.0,
            caution_precip_max_mm=0.3,
            caution_pop_min_percent=30,
            caution_pop_max_percent=70,
            caution_wind_speed_min_ms=7,
            caution_wind_speed_max_ms=10,
            caution_wind_scale_upper=3,
            caution_humidity_percent=85,
        ),
        warning=COMMON_WARNING_RULES,
    ),
    "inspection": MissionRuleProfile(
        task_type="inspection",
        display_name="设备巡检",
        hourly=HourlyRuleThresholds(
            prohibited_weather_texts=frozenset({"雷阵雨", "雷雨", "大雨", "暴雨"}),
            caution_weather_texts=frozenset({"小雨", "阴"}),
            prohibited_precip_mm=0.3,
            prohibited_pop_percent=70,
            prohibited_wind_speed_ms=9,
            prohibited_wind_scale_upper=4,
            caution_precip_min_mm=0.0,
            caution_precip_max_mm=0.3,
            caution_pop_min_percent=30,
            caution_pop_max_percent=70,
            caution_wind_speed_min_ms=6,
            caution_wind_speed_max_ms=9,
            caution_wind_scale_upper=3,
            caution_humidity_percent=82,
        ),
        warning=COMMON_WARNING_RULES,
    ),
    "hover": MissionRuleProfile(
        task_type="hover",
        display_name="定点悬停拍摄",
        hourly=HourlyRuleThresholds(
            prohibited_weather_texts=frozenset({"雷阵雨", "雷雨", "大雨", "暴雨"}),
            caution_weather_texts=frozenset({"小雨", "阴"}),
            prohibited_precip_mm=0.2,
            prohibited_pop_percent=60,
            prohibited_wind_speed_ms=8,
            prohibited_wind_scale_upper=4,
            caution_precip_min_mm=0.0,
            caution_precip_max_mm=0.2,
            caution_pop_min_percent=20,
            caution_pop_max_percent=60,
            caution_wind_speed_min_ms=5,
            caution_wind_speed_max_ms=8,
            caution_wind_scale_upper=3,
            caution_humidity_percent=80,
        ),
        warning=COMMON_WARNING_RULES,
    ),
    "survey": MissionRuleProfile(
        task_type="survey",
        display_name="低空测绘",
        hourly=HourlyRuleThresholds(
            prohibited_weather_texts=frozenset({"雷阵雨", "雷雨", "大雨", "暴雨"}),
            caution_weather_texts=frozenset({"小雨", "阴"}),
            prohibited_precip_mm=0.25,
            prohibited_pop_percent=65,
            prohibited_wind_speed_ms=8.5,
            prohibited_wind_scale_upper=4,
            caution_precip_min_mm=0.0,
            caution_precip_max_mm=0.25,
            caution_pop_min_percent=25,
            caution_pop_max_percent=65,
            caution_wind_speed_min_ms=5.5,
            caution_wind_speed_max_ms=8.5,
            caution_wind_scale_upper=3,
            caution_humidity_percent=82,
        ),
        warning=COMMON_WARNING_RULES,
    ),
}


def get_mission_rule_profile(task_type: str = "cruise") -> MissionRuleProfile:
    # 未识别任务类型时，默认回退到巡航规则。
    normalized_task_type = (task_type or "cruise").strip().lower()
    return MISSION_RULE_PROFILES.get(normalized_task_type, MISSION_RULE_PROFILES["cruise"])
