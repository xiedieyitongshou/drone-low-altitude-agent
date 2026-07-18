# Day29 知识库字段设计与样例条目

## 1. 文档目的

本文档用于定义 `Day 29` 第一版“建议型 RAG 知识库”的最小结构。

当前目标不是让知识库参与硬判断，而是：

- 基于规则引擎已经给出的结果
- 检索对应风险、任务类型、预警类型的建议条目
- 为后续前端展示和 LLM 建议生成提供稳定知识输入

## 2. 当前知识库定位

第一版知识库只做三件事：

- 风险建议召回
- 任务执行建议召回
- 预警场景建议召回

不做的内容：

- 不替代规则引擎判断
- 不负责输出 `适飞 / 慎飞 / 禁飞`
- 不直接参与推荐窗口排序
- 不直接参与多地点比选排序

## 3. 第一版知识库结构设计

建议先采用 **结构化 JSON 条目库**，后续再做 embedding、向量化和复杂索引。

### 3.1 顶层字段

每条知识建议建议包含以下字段：

| 字段名 | 类型 | 是否必填 | 含义 |
|---|---|---:|---|
| `id` | `string` | 是 | 知识条目唯一标识 |
| `category` | `string` | 是 | 条目类别 |
| `risk_type` | `string[]` | 否 | 对应风险类型标签 |
| `task_type` | `string[]` | 否 | 对应任务类型标签 |
| `warning_type` | `string[]` | 否 | 对应预警类型标签 |
| `warning_level` | `string[]` | 否 | 对应预警等级标签 |
| `decision_scope` | `string[]` | 否 | 适用的总体结论范围 |
| `title` | `string` | 是 | 建议标题 |
| `advice_text` | `string` | 是 | 建议正文 |
| `priority` | `string` | 是 | 建议优先级 |
| `action_type` | `string` | 否 | 建议动作类型 |
| `keywords` | `string[]` | 否 | 检索辅助关键词 |
| `source` | `string` | 否 | 资料来源名称 |
| `source_url` | `string` | 否 | 来源链接 |
| `notes` | `string` | 否 | 备注 |

### 3.2 字段取值约束建议

#### `category`

建议第一版限定为：

- `risk_advice`
- `warning_advice`
- `task_advice`
- `execution_advice`

#### `risk_type`

建议第一版先统一成内部标签，而不是直接复用原始天气文案：

- `high_wind`
- `rainfall`
- `thunderstorm`
- `high_humidity`
- `low_visibility`
- `general_caution`

#### `task_type`

与当前项目内部任务类型保持一致：

- `cruise`
- `inspection`
- `hover`
- `survey`
- `all`

#### `warning_type`

建议先与当前预警修正集合对齐：

- `雷电`
- `雷雨大风`
- `暴雨`
- `大风`
- `强对流`
- `短时强降水`
- `大雾`

#### `warning_level`

建议值：

- `yellow`
- `orange`
- `red`
- `blue`

#### `decision_scope`

用于指定这条建议适用于哪类规则结论：

- `allow`
- `caution`
- `reject`

与当前系统大致可映射为：

- `适飞` -> `allow`
- `慎飞` -> `caution`
- `禁飞` -> `reject`

#### `priority`

建议值：

- `high`
- `medium`
- `low`

#### `action_type`

建议值：

- `delay`
- `reschedule`
- `change_task`
- `prepare_equipment`
- `reduce_risk`
- `cancel`

## 4. 第一版建议检索策略

在还没做向量库前，可以先按规则检索：

1. 先按 `decision_scope` 过滤
2. 再按 `risk_type` / `warning_type` / `warning_level` 过滤
3. 再按 `task_type` 过滤
4. 最后按 `priority` 排序

也就是说，第一版检索不是语义搜索，而是 **结构化匹配**。

后续进入复杂 RAG 时，再把：

- `title`
- `advice_text`
- `keywords`
- `notes`

作为 embedding 文本源。

## 5. 样例条目清单

下面给出可直接落地的第一版样例条目。

### 5.1 雷暴 / 强对流类

```json
{
  "id": "advice-thunderstorm-delay-001",
  "category": "risk_advice",
  "risk_type": ["thunderstorm"],
  "task_type": ["all"],
  "decision_scope": ["caution", "reject"],
  "title": "延后执行并避开强对流窗口",
  "advice_text": "出现雷暴或强对流风险时，不建议继续按原窗口执行任务。优先延后或切换到更稳定时段，避免在对流活跃时段起飞。",
  "priority": "high",
  "action_type": "reschedule",
  "keywords": ["雷暴", "强对流", "改期", "延后执行"],
  "source": "FAA thunderstorm guidance",
  "source_url": "https://www.faa.gov/blog/clearedfortakeoff/steering-around-storm-ga-guide-thunderstorms"
}
```

```json
{
  "id": "advice-thunderstorm-cancel-002",
  "category": "execution_advice",
  "risk_type": ["thunderstorm"],
  "task_type": ["hover", "survey"],
  "decision_scope": ["reject"],
  "title": "高敏感任务建议直接取消当前窗口",
  "advice_text": "悬停拍摄和测绘任务对气流稳定性要求更高，遇到雷暴或强对流时不应勉强执行，应直接取消当前窗口。",
  "priority": "high",
  "action_type": "cancel",
  "keywords": ["悬停拍摄", "测绘", "取消", "强对流"],
  "source": "DJI / FAA weather safety guidance"
}
```

### 5.2 高风速类

```json
{
  "id": "advice-high-wind-reduce-risk-001",
  "category": "risk_advice",
  "risk_type": ["high_wind"],
  "task_type": ["all"],
  "decision_scope": ["caution"],
  "title": "优先缩短任务窗口并降低暴露时长",
  "advice_text": "在风速偏高但尚未达到绝对禁飞条件时，应优先缩短任务窗口，减少悬停和长距离暴露时段，并重新确认返航余量。",
  "priority": "high",
  "action_type": "reduce_risk",
  "keywords": ["高风速", "缩短窗口", "返航余量"],
  "source": "DJI flight safety guidance",
  "source_url": "https://support.dji.com/help/content?customId=en-us03400006768&lang=en&re=US&spaceId=34"
}
```

```json
{
  "id": "advice-high-wind-change-task-002",
  "category": "task_advice",
  "risk_type": ["high_wind"],
  "task_type": ["hover", "survey"],
  "decision_scope": ["caution"],
  "title": "必要时切换到更低敏感任务类型",
  "advice_text": "若必须在当前时段执行，应优先选择对稳定性要求相对较低的任务，避免进行悬停拍摄或高精度测绘。",
  "priority": "medium",
  "action_type": "change_task",
  "keywords": ["切换任务", "悬停拍摄", "测绘", "高风速"],
  "source": "Operational best practice"
}
```

### 5.3 降水 / 潮湿类

```json
{
  "id": "advice-rainfall-delay-001",
  "category": "risk_advice",
  "risk_type": ["rainfall"],
  "task_type": ["all"],
  "decision_scope": ["caution", "reject"],
  "title": "降水条件下优先改期或后移窗口",
  "advice_text": "降水会增加姿态稳定、镜头成像和设备防护风险，出现持续降水时应优先改期，避免在降水窗口中继续执行任务。",
  "priority": "high",
  "action_type": "reschedule",
  "keywords": ["降水", "小雨", "改期", "后移窗口"],
  "source": "DJI flight safety guidance"
}
```

```json
{
  "id": "advice-humidity-equipment-002",
  "category": "execution_advice",
  "risk_type": ["high_humidity"],
  "task_type": ["survey", "hover"],
  "decision_scope": ["caution"],
  "title": "高湿环境下加强设备与镜头检查",
  "advice_text": "高湿环境下应重点检查镜头结露、电池状态和设备外部防护，必要时在起飞前增加短时待机观察。",
  "priority": "medium",
  "action_type": "prepare_equipment",
  "keywords": ["高湿", "结露", "镜头", "电池检查"],
  "source": "Operational best practice"
}
```

### 5.4 预警类

```json
{
  "id": "advice-warning-yellow-caution-001",
  "category": "warning_advice",
  "warning_type": ["雷电", "雷雨大风", "强对流", "短时强降水"],
  "warning_level": ["yellow"],
  "task_type": ["all"],
  "decision_scope": ["caution"],
  "title": "黄色高风险预警下不建议按原计划执行",
  "advice_text": "即使当前仍存在局部可执行窗口，黄色高风险预警也意味着环境不稳定，建议优先转向推荐窗口或降低任务强度。",
  "priority": "high",
  "action_type": "reduce_risk",
  "keywords": ["黄色预警", "降低任务强度", "推荐窗口"],
  "source": "Project rule explanation"
}
```

```json
{
  "id": "advice-warning-orange-cancel-002",
  "category": "warning_advice",
  "warning_type": ["雷电", "暴雨", "大风", "强对流"],
  "warning_level": ["orange", "red"],
  "task_type": ["all"],
  "decision_scope": ["reject"],
  "title": "橙色及以上高风险预警建议取消当前任务",
  "advice_text": "橙色及以上高风险预警对应明显危险环境，不应继续执行当前任务，应直接取消当前窗口并重新规划任务时间。",
  "priority": "high",
  "action_type": "cancel",
  "keywords": ["橙色预警", "红色预警", "取消任务"],
  "source": "Project warning override policy"
}
```

### 5.5 任务类型类

```json
{
  "id": "advice-hover-sensitive-001",
  "category": "task_advice",
  "task_type": ["hover"],
  "decision_scope": ["caution", "reject"],
  "title": "悬停拍摄任务优先选择更稳定窗口",
  "advice_text": "悬停拍摄对风和姿态稳定性更敏感，遇到中等偏高风速或不稳定天气时，应优先等待更平稳窗口，而不是勉强执行。",
  "priority": "high",
  "action_type": "delay",
  "keywords": ["悬停拍摄", "稳定窗口", "风敏感"],
  "source": "Task profile guidance"
}
```

```json
{
  "id": "advice-survey-precision-002",
  "category": "task_advice",
  "task_type": ["survey"],
  "decision_scope": ["caution"],
  "title": "测绘任务应优先保证连续稳定时段",
  "advice_text": "测绘任务比一般巡航更依赖连续稳定时段。若当前仅存在碎片化可飞小时，建议优先等待更长的连续低风险窗口。",
  "priority": "medium",
  "action_type": "reschedule",
  "keywords": ["测绘", "连续窗口", "稳定时段"],
  "source": "Task profile guidance"
}
```

### 5.6 推荐与比选增强类

```json
{
  "id": "advice-recommend-window-001",
  "category": "execution_advice",
  "task_type": ["all"],
  "decision_scope": ["allow", "caution"],
  "title": "优先按系统推荐窗口执行",
  "advice_text": "若系统已给出推荐窗口，应优先使用推荐窗口而非原始计划时段，以减少执行阶段的天气不确定性。",
  "priority": "medium",
  "action_type": "reschedule",
  "keywords": ["推荐窗口", "执行时段", "优先使用"],
  "source": "Project recommendation policy"
}
```

```json
{
  "id": "advice-compare-topk-002",
  "category": "execution_advice",
  "task_type": ["all"],
  "decision_scope": ["allow", "caution"],
  "title": "多地点任务优先按排序前列依次规划",
  "advice_text": "在多地点场景下，不建议只依赖单一首选地点，应同时保留 Top-K 备选地点，便于根据实时环境变化快速切换任务次序。",
  "priority": "medium",
  "action_type": "reduce_risk",
  "keywords": ["多地点", "Top-K", "备选地点", "快速切换"],
  "source": "Project comparison policy"
}
```

## 6. 推荐的本地存储格式

第一版建议直接存成：

- `data/knowledge/advice_rules.json`

建议结构：

```json
{
  "version": "v1",
  "items": [
    {
      "id": "advice-thunderstorm-delay-001",
      "category": "risk_advice",
      "risk_type": ["thunderstorm"],
      "task_type": ["all"],
      "decision_scope": ["caution", "reject"],
      "title": "延后执行并避开强对流窗口",
      "advice_text": "出现雷暴或强对流风险时，不建议继续按原窗口执行任务。",
      "priority": "high",
      "action_type": "reschedule",
      "keywords": ["雷暴", "强对流", "改期"],
      "source": "FAA thunderstorm guidance",
      "source_url": "https://www.faa.gov/blog/clearedfortakeoff/steering-around-storm-ga-guide-thunderstorms"
    }
  ]
}
```

## 7. 下一步建议

完成这份字段设计后，`Day 29-30` 的下一步建议是：

1. 先把这批条目录入 JSON
2. 先做结构化匹配检索
3. 再接 embedding 和向量索引
4. 最后在 `evaluate / recommend / compare / agent` 中挂 `advice` 字段

这样可以先把建议型 RAG 的底座跑通，再逐步升级成复杂 RAG。
