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
    # 任务特征说明，便于后续文档、界面或 Agent 做解释。
    description: str
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
        description="覆盖范围较大，强调整体可执行性，对风速和降水敏感度适中。",
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
        description="通常靠近设施和目标物，要求相对稳定，风速和湿度阈值比巡航更严格。",
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
            caution_humidity_percent=80,
        ),
        warning=COMMON_WARNING_RULES,
    ),
    "hover": MissionRuleProfile(
        task_type="hover",
        display_name="定点悬停拍摄",
        description="强调悬停稳定性，对风速、降水和湿度最敏感，是当前四类任务中最严格的一类。",
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
        description="强调连续稳定窗口，对轻度降水和中高风速较敏感，严格程度介于巡检和悬停之间。",
        hourly=HourlyRuleThresholds(
            prohibited_weather_texts=frozenset({"雷阵雨", "雷雨", "大雨", "暴雨"}),
            caution_weather_texts=frozenset({"小雨", "阴"}),
            prohibited_precip_mm=0.22,
            prohibited_pop_percent=60,
            prohibited_wind_speed_ms=8.0,
            prohibited_wind_scale_upper=4,
            caution_precip_min_mm=0.0,
            caution_precip_max_mm=0.22,
            caution_pop_min_percent=20,
            caution_pop_max_percent=60,
            caution_wind_speed_min_ms=5.0,
            caution_wind_speed_max_ms=8.0,
            caution_wind_scale_upper=3,
            caution_humidity_percent=78,
        ),
        warning=COMMON_WARNING_RULES,
    ),
}


SUPPORTED_TASK_TYPES: tuple[str, ...] = tuple(MISSION_RULE_PROFILES.keys())


def normalize_task_type(task_type: str | None) -> str:
    return (task_type or "cruise").strip().lower()


def get_mission_rule_profile(task_type: str = "cruise") -> MissionRuleProfile:
    # 未识别任务类型时，默认回退到巡航规则。
    normalized_task_type = normalize_task_type(task_type)
    return MISSION_RULE_PROFILES.get(normalized_task_type, MISSION_RULE_PROFILES["cruise"])


def is_supported_task_type(task_type: str | None) -> bool:
    return normalize_task_type(task_type) in MISSION_RULE_PROFILES


def list_supported_task_types() -> tuple[str, ...]:
    return SUPPORTED_TASK_TYPES
