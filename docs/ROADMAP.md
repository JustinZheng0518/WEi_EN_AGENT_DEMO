# 项目完整路线图

状态更新：2026-10-31（America/Denver）。

根据中英文自然语言需求，基于可追溯产品数据生成完整搭配和 BOM；未知、冲突、缺件或未经审核的工程条件不能判定通过。当前优先英文目录。

本文件由 `data/project_progress.json` 生成；修改进度源后运行 `python scripts/project_progress.py`。
“已完成”只对应该任务写明的验收范围。软件测试、订货号转录、数据审核与真实硬件批准不能互相替代。
不以任务勾选数计算全项目或全目录完成百分比。中文资料属于后续范围，当前先完成英文。

## 状态和更新方式

- 已完成：有可检查的交付和验证证据，且满足本条验收条件。
- 进行中：只完成了一部分；即使功能可演示，数据/工程审核未完成也保持部分状态。
- 待做：尚未开展或尚无完成证据，不自动等同于外部阻塞。
- 外部条件阻塞：必须写明具体缺少的资料、凭证或决策；继续其他独立工作。
- 持续维护：每批更新都要执行，不用一次性勾选成永久完成。

## 任务清单

### 目标、基线与进度管理

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| BASE-01 | 已完成（限定验收范围） | 核对现状及有边界的成果 | 明确 OCR、转录、审核和工程批准四层状态；保留本次基线和历史提交。 | — | [docs/worklog.md](../docs/worklog.md)、[docs/ha-coverage.md](../docs/ha-coverage.md) |
| BASE-02 | 已完成（限定验收范围） | 建立路线图、项目记忆和逐条进度表 | 仓库有单一进度源、可再生成文档和 73 条目录跟踪记录；AGENTS 要求每次更新。 | — | [data/project_progress.json](../data/project_progress.json)、[scripts/project_progress.py](../scripts/project_progress.py)、[docs/PROJECT_MEMORY.md](../docs/PROJECT_MEMORY.md) |
| BASE-03 | 待做 | 确认业务范围和录入优先级 | 记录常用型号、典型需求、连接范围及业务优先级；未知销量不自造排名。 | BASE-01 | 待补交付证据 |
| BASE-04 | 持续维护 | 每次交付同步进度和 GitHub | 每批工作更新状态、指标、缺项、证据和历史；验证后提交推送并核对远程 SHA。 | — | [AGENTS.md](../AGENTS.md) |

### 原始资料、定位与版本

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| SOURCE-01 | 已完成（限定验收范围） | 英文 PDF 分卷索引及文件一致性 | 32 份、1424 页连续范围，文件校验值和原始路径可追溯。 | — | [wain/ingest.py](../wain/ingest.py)、[docs/progress.md](../docs/progress.md) |
| SOURCE-02 | 已完成（限定验收范围） | 英文全文 OCR 与断点续跑 | 1424 页保存文字、坐标和引擎信息；失败可重试；不将 OCR 当审核。 | — | [wain/ingest.py](../wain/ingest.py)、[docs/worklog.md](../docs/worklog.md) |
| SOURCE-03 | 已完成（限定验收范围） | 总目录条目与类别导航 | 73 个条目、13 类带来源，区分系列、规格、附件、服务和参考内容。 | — | [data/catalog_sections.json](../data/catalog_sections.json)、[docs/catalog-map.md](../docs/catalog-map.md) |
| SOURCE-04 | 进行中 / 部分完成 | 核对正文页码和定位冲突 | 逐条处理缺失/冲突锚点，不用统一偏移猜页码；明确候选与确认依据。 | — | [wain/catalog.py](../wain/catalog.py)、[docs/catalog-map.md](../docs/catalog-map.md) |
| SOURCE-05 | 待做 | 核实 P33 索引资料引用 | 找到对应版本正文或记录已确认的版本差异；未找到时持续列缺口。 | SOURCE-03 | 待补交付证据 |
| SOURCE-06 | 待做 | 建立目录更新与资料修订流程 | 新版本保留历史、差异、来源和有效性；参数变化使相关审核失效。 | SOURCE-01, DATA-01 | 待补交付证据 |
| SOURCE-07 | 待做 | 接入中文目录并做跨语言对齐（后续范围） | 用户提供资料后独立索引、OCR、对照型号与冲突；不阻塞当前英文试验。 | SOURCE-01, DATA-02 | 待补交付证据 |

### 数据库与参数规范

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| DATA-01 | 已完成（限定验收范围） | 建立产品、参数、证据和关系数据结构 | PostgreSQL 主键/外键、来源、条件、状态和本地连接可用。 | — | [schema.sql](../schema.sql)、[wain/db.py](../wain/db.py) |
| DATA-02 | 进行中 / 部分完成 | 规范字段、单位、中英文术语及电气语义 | 明确普通接点/PE、AC/DC、每接点电流、标准、导体电位关系、降额条件及单位换算。 | — | [wain/ha_series.py](../wain/ha_series.py)、[docs/database.md](../docs/database.md) |
| DATA-03 | 进行中 / 部分完成 | 可重复批量导入和冲突处理 | 除 HA 外建立按版式/系列复用流程；冲突回滚、保护人工更正、保留重复页来源。 | — | [wain/ha_series.py](../wain/ha_series.py)、[tests/test_ha_series.py](../tests/test_ha_series.py) |
| DATA-04 | 待做 | 清理 OCR 候选并建立型号总数基准 | 逐章节建立人工可追溯的预期行数、唯一订货号和遗漏清单；不把候选出现数当产品数。 | SOURCE-03, DATA-03 | 待补交付证据 |
| DATA-05 | 待做 | 完善可追踪的数据库迁移与回滚 | 有版本化迁移、保留审核数据的升级步骤及独立恢复验证。 | DATA-01 | 待补交付证据 |

### HA 完整数据与疑点闭环

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| HA-01 | 已完成（限定验收范围） | 转录 HA 本章全部订货表身份 | 文件 72–79 页登记 36 个芯体、72 个不同订货号、147 行来源；不虚构 HA-032 SKU。 | — | [data/ha_series.json](../data/ha_series.json)、[docs/ha-coverage.md](../docs/ha-coverage.md)、[tests/test_ha_series.py](../tests/test_ha_series.py) |
| HA-02 | 进行中 / 部分完成 | 完善 HA 参数及适用条件 | 逐型号核对电压/电流、线径、剥线、扭矩、材质、温度等，保留明确条件和未知。 | HA-01, DATA-02 | [wain/ha_series.py](../wain/ha_series.py)、[docs/ha-coverage.md](../docs/ha-coverage.md) |
| HA-03 | 待做 | 转录并核对尺寸与安装图 | 区分长宽高、视图、开孔、安装状态和单位；数值关联图中区域并审核。 | HA-01 | 待补交付证据 |
| HA-04 | 待做 | 处理 HA-002、HA-004-V2 等明确疑点 | 通过原图、补充资料或厂家依据核实；未解决项保持未知，不以型号猜测。 | HA-01 | 待补交付证据 |
| HA-05 | 进行中 / 部分完成 | 完成 HA 端子、编码件、工具及外壳关联 | 逐型号关联实际适用的产品、数量和条件；可选与必需分别记录。 | HA-01, COMMON-01, COMMON-02 | [docs/ha010-line01.md](../docs/ha010-line01.md)、[wain/ha_series.py](../wain/ha_series.py)、[wain/ha010_seed.py](../wain/ha010_seed.py) |
| HA-06 | 待做 | 完成 HA 数据独立审核及章节验收 | 审核身份、参数、来源、关系和遗漏；有未解问题则明确列出，不能声称参数全完。 | HA-02, HA-03, HA-04, HA-05, REVIEW-04 | 待补交付证据 |
| HA-07 | 已完成（限定验收范围） | 整理第一条 HA-010 螺钉端接样板链路资料 | 5类主件有候选订货号、每套用量、目录页与适用边界；列未选定供料、未解事项和技术确认问题。只验收资料包，不代表配对、完整线束或工程批准。 | HA-01 | [docs/ha010-line01.md](../docs/ha010-line01.md)、[docs/ha010-line01-bom.csv](../docs/ha010-line01-bom.csv)、[data/ha010_line01.json](../data/ha010_line01.json) |

### 共用端子、外壳与附件

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| COMMON-01 | 进行中 / 部分完成 | 完整录入共用压接端子 | P13 各电流/结构条目逐行盘点，核对适用芯体、线径、镀层、装配和工具。 | — | [wain/seed.py](../wain/seed.py)、[wain/ha_series.py](../wain/ha_series.py) |
| COMMON-02 | 进行中 / 部分完成 | 完整录入外壳、底座、锁扣及密封件 | 覆盖目录规格和变体，核对真实订货号、配对、进线、开孔和防护成立条件。 | — | [docs/ha010-line01.md](../docs/ha010-line01.md)、[wain/ha010_seed.py](../wain/ha010_seed.py) |
| COMMON-03 | 进行中 / 部分完成 | 录入编码、支架、框架、接地及其他附件 | 按原文建立实际适用关系和必需条件，避免只列主件。 | — | [wain/ha_series.py](../wain/ha_series.py) |
| COMMON-04 | 进行中 / 部分完成 | 录入电缆接头、工具及辅助装配要求 | 核对螺纹/螺距、夹紧范围、密封、工具线径和辅助件要求，成品与工具分开。 | — | [docs/ha010-line01.md](../docs/ha010-line01.md)、[wain/ha010_seed.py](../wain/ha010_seed.py)、[wain/ha_series.py](../wain/ha_series.py) |
| COMMON-05 | 待做 | 处理可选线缆、线束和外部供料范围 | 明确连接器组件与完整线束的边界；需要线束时补线材规格、长度、端接和测试要求。 | BASE-03 | 待补交付证据 |

### 全目录型号级扩展

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| EXPAND-01 | 待做 | 扩展 HE 与 HD/HDD 型号数据 | 按逐条目录进度表转录型号、参数、来源、配套和缺项，分别完成章节验收。 | DATA-03, HA-01 | 待补交付证据 |
| EXPAND-02 | 待做 | 扩展其余矩形芯体系列 | 覆盖 HVE/HVES、HEE/HEEE、HSB、HK、HE/HD AV、HQ、HC、HCM 等目录范围。 | DATA-03 | 待补交付证据 |
| EXPAND-03 | 待做 | 细化 HM 模块和组合依赖 | 拆分电气、光纤、气动等内部模块，核对框架、槽位、键位和数量约束。 | DATA-03, COMMON-03 | 待补交付证据 |
| EXPAND-04 | 待做 | 扩展圆形连接器和接口条目 | 覆盖 M8、M12 各编码及其余接口/接线盒，记录编码、线序、配对和线缆条件。 | DATA-02, DATA-03 | 待补交付证据 |
| EXPAND-05 | 待做 | 扩展 PCB、EC、高温及特殊产品 | 按目录逐条处理其专有参数、用途限制、配套和来源，不套用 HA 规则。 | DATA-03 | 待补交付证据 |
| EXPAND-06 | 待做 | 全目录范围对账和遗漏验收 | 每个适用目录条目都有型号基准、录入/审核数量、遗漏和未解事项；不以页数代替 SKU 完整性。 | EXPAND-01, EXPAND-02, EXPAND-03, EXPAND-04, EXPAND-05, COMMON-01, COMMON-02, COMMON-03, COMMON-04 | 待补交付证据 |

### 搭配求解与完整性规则

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| RULE-01 | 进行中 / 部分完成 | 需求字段和硬约束校验 | 除 HA-010 试验外支持所选范围，明确标准、电位、环境、电流语义和必需追问。 | — | [wain/selection.py](../wain/selection.py) |
| RULE-02 | 进行中 / 部分完成 | 电气、机械及环境兼容规则 | 用来源支持的额定/降额、编码、针位、尺寸、锁扣、螺纹、密封及温度校验组合。 | DATA-02 | [wain/selection.py](../wain/selection.py) |
| RULE-03 | 进行中 / 部分完成 | 必需依赖闭合与完整 BOM 求解 | 从主件递归展开依赖，正确处理条件附件、缺件、循环和未知数量；不只阻止缺件，还能生成支持范围内的组合。 | — | [wain/selection.py](../wain/selection.py)、[tests/test_selection.py](../tests/test_selection.py) |
| RULE-04 | 进行中 / 部分完成 | 数量、PE、包装和装配工具规则 | 按套数和接点计算数量，独立核对 PE，区分使用量、采购量、工具及外部供料。 | — | [wain/selection.py](../wain/selection.py) |
| RULE-05 | 待做 | 多方案、替代及无解解释 | 先满足硬约束再排序；区分可行、待确认、无解，替代关系有依据，库存/价格只在有数据时使用。 | RULE-01, RULE-02, RULE-03 | 待补交付证据 |
| RULE-06 | 待做 | 扩展可复用系列模板与规则版本 | 新系列可通过明确模板接入，规则变更有版本和回归用例，不能使用永久假定通过的开关。 | RULE-02, RULE-03 | 待补交付证据 |

### 审核与真实工程验证

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| REVIEW-01 | 已完成（限定验收范围） | 原图对照和分层审核工作台 | 身份、参数、关系、来源和工程记录分别审核；有字段更正和历史可查。 | — | [wain/review.py](../wain/review.py)、[tests/test_review.py](../tests/test_review.py) |
| REVIEW-02 | 已完成（限定验收范围） | 更正保护、版本冲突和审核失效 | 冲突阻止覆盖；资料变动撤回相关批准；旧工况结论不能套用新组合。 | — | [wain/review.py](../wain/review.py)、[tests/test_review.py](../tests/test_review.py)、[tests/test_selection.py](../tests/test_selection.py) |
| REVIEW-03 | 待做 | 明确审核责任与证据等级 | 区分自动转录、原图复核、厂家依据和工程批准；有真实责任人/权限及变更记录。 | BASE-03, REVIEW-01 | 待补交付证据 |
| REVIEW-04 | 待做 | 逐项开展真实数据独立审核 | 对照原文审核产品、参数及关系并留依据；不为了展示通过批量批准。 | REVIEW-01, REVIEW-03 | 待补交付证据 |
| REVIEW-05 | 待做 | 取得首个真实 HA-010 完整方案验收 | 在明确工况下，配对、PE、降额、密封、螺纹、安装和所有附件有依据，真实用例通过；测试假数据不算。 | HA-05, REVIEW-04, RULE-02, RULE-03 | 待补交付证据 |
| REVIEW-06 | 待做 | 按系列和场景扩展真实批准范围 | 每个上线范围有真实批准用例和限制；不把一个方案通过推广到所有型号或工况。 | REVIEW-05, RULE-06 | 待补交付证据 |

### 自然语言 Agent 与模型 API

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| AGENT-01 | 进行中 / 部分完成 | 选择模型 API 与安全配置 | 确认供应商、模型、费用预算和数据发送范围；凭证只通过安全配置提供，不能入聊天或 Git。 | — | [docs/NEXT_SESSION.md](../docs/NEXT_SESSION.md)、[docs/PROJECT_MEMORY.md](../docs/PROJECT_MEMORY.md) |
| AGENT-02 | 待做 | 中英文自然语言转结构化需求 | 处理单位、针数/芯数/PE、AC/DC、电流语义、场景和硬约束；歧义保持未知。 | DATA-02, AGENT-01 | 待补交付证据 |
| AGENT-03 | 待做 | 封装模型工具调用接口 | 检索、产品详情、搭配求解、完整性校验、证据查询工具有固定 schema；模型不直接执行 SQL。 | AGENT-01, RULE-01, RULE-03 | 待补交付证据 |
| AGENT-04 | 待做 | 多轮追问与需求修订 | 只追问影响决策的未知项，保留用户回答和偏好；修改需求后重算方案。 | AGENT-02, AGENT-03 | 待补交付证据 |
| AGENT-05 | 待做 | 生成可追溯方案说明和 BOM | 所有型号来自数据库，结论对应校验与证据；明确待确认、缺件、无解及替代条件。 | AGENT-03, AGENT-04 | 待补交付证据 |
| AGENT-06 | 待做 | 约束幻觉、注入及工具越权 | 目录/OCR 仅作为数据；模型不能虚构型号或修改批准，最终放行由后端控制并有回归用例。 | AGENT-03 | 待补交付证据 |
| AGENT-07 | 待做 | 模型端到端验证与费用观测 | 真实 API 的成功、失败、超时、重试、上下文和费用有测试记录；未连接不描述为已运行。 | AGENT-05, AGENT-06, QA-02 | 待补交付证据 |

### 用户工作台与方案交付

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| APP-01 | 已完成（限定验收范围） | 本地资料审核及 HA-010 试验页面 | 目录搜索、原图、审核和结构化试验在浏览器可用，支持手机布局。 | — | [wain/static/index.html](../wain/static/index.html)、[scripts/check_ui.py](../scripts/check_ui.py) |
| APP-02 | 进行中 / 部分完成 | 面向用户的自然语言会话与方案页面 | 输入需求、追问、展示 BOM、检查状态、原文与待办，产品流程不堆内部实现字段。 | AGENT-04, AGENT-05 | [wain/static/trial/index.html](../wain/static/trial/index.html)、[wain/static/trial/core.js](../wain/static/trial/core.js)、[docs/web-trial.md](../docs/web-trial.md) |
| APP-03 | 进行中 / 部分完成 | 导出与方案交付 | 完善 BOM CSV/Excel/JSON、依据报告和方案版本；文件不混淆样板与已批准结果。 | — | [scripts/export.py](../scripts/export.py)、[wain/static/trial/trial.js](../wain/static/trial/trial.js) |
| APP-04 | 待做 | 用户验收与可用性修正 | 用目标用户的真实需求验证操作、中文说明、错误提示、恢复和可访问性。 | APP-02, REVIEW-05 | 待补交付证据 |
| APP-05 | 已完成（限定验收范围） | 交付 HA-010 可测试网页原型与单文件演示 | 明确限定 10 普通接点加 PE；有限参数识别、人工核对、候选 BOM、缺项/超额定、来源、CSV 和手机布局可测试；提供数据库与自包含 HTML 两版，未接模型/完整工程校验保持明确。 | — | [wain/static/trial/index.html](../wain/static/trial/index.html)、[demo/index.html](../demo/index.html)、[wain/trial.py](../wain/trial.py)、[scripts/build_trial.py](../scripts/build_trial.py)、[scripts/check_trial_ui.py](../scripts/check_trial_ui.py)、[docs/web-trial.md](../docs/web-trial.md) |

### 数据质量和系统验收

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| QA-01 | 已完成（限定验收范围） | 基础数据库/API 与本地浏览器回归 | 本批 67 项数据库/API 测试和 7 项参数识别测试通过；新旧网页 Chromium 验收通过，覆盖未知、边界、依赖、数量和原图/页面操作，不改业务批准。 | — | [tests/test_ha_series.py](../tests/test_ha_series.py)、[tests/test_selection.py](../tests/test_selection.py)、[scripts/check_ui.py](../scripts/check_ui.py)、[docs/worklog.md](../docs/worklog.md)、[tests/test_trial.py](../tests/test_trial.py)、[tests/trial_core.test.cjs](../tests/trial_core.test.cjs)、[scripts/check_trial_ui.py](../scripts/check_trial_ui.py) |
| QA-02 | 待做 | 建立人工核验的代表性评测集 | 包含正常、缺件、错误配对、超额定、歧义、资料缺失、多语言和无解；与实际目录和工况对应。 | REVIEW-03, BASE-03 | 待补交付证据 |
| QA-03 | 待做 | 评估数据准确率与检索覆盖 | 对独立样本计算字段、型号关联、召回和遗漏；结果分系列/版式，不能用行数相等代替准确率。 | QA-02, DATA-03 | 待补交付证据 |
| QA-04 | 待做 | 完整性与规则反例验收 | 真实正向与负向硬件案例都验证，缺少任何必需件或依据不能误放行；有性能和重复性记录。 | QA-02, REVIEW-05 | 待补交付证据 |
| QA-05 | 待做 | 全链路性能、异常及恢复验收 | 覆盖数据规模、并发、模型故障、断线、恢复及权限；有目标范围内的可复现结果。 | AGENT-07, OPS-02, OPS-04 | 待补交付证据 |

### 部署、持久化与持续维护

| ID | 状态 | 要做什么 | 验收条件 | 前置任务 | 已有证据 |
| --- | --- | --- | --- | --- | --- |
| OPS-01 | 已完成（限定验收范围） | 当前云环境启动与独立备份恢复 | 已有安装、启动、导出、备份脚本和独立恢复验证；进程重启不依赖旧 PID。 | — | [scripts/setup.sh](../scripts/setup.sh)、[scripts/postgres.sh](../scripts/postgres.sh)、[docs/worklog.md](../docs/worklog.md) |
| OPS-02 | 待做 | 建立跨环境持久化与数据迁移方案 | 选定并验证数据库和 PDF/OCR/证据文件存储；不依赖 Git 源码或每次手动发布环境保存数据。 | DATA-05 | 待补交付证据 |
| OPS-03 | 待做 | 自动备份、保留周期和恢复演练 | 备份覆盖数据库及原始文件，定期自动运行、检查完整性并验证可恢复。 | OPS-02 | 待补交付证据 |
| OPS-04 | 待做 | 生产部署、鉴权与权限隔离 | 配置域名/TLS、真正身份认证、审核/查询权限、限流和网络边界；本地工具不直接裸露公网。 | REVIEW-03, OPS-02 | 待补交付证据 |
| OPS-05 | 待做 | 运行观测和运维文档 | 有健康检查、错误日志、数据/模型版本、审计、费用及告警；不记录凭证值。 | OPS-04, AGENT-01 | 待补交付证据 |
| OPS-06 | 待做 | 限定范围试点上线与发布回滚 | 用户验收、真实数据与工程批准、模型验证、部署恢复全部满足后上线；发布范围和回滚步骤明确。 | REVIEW-05, APP-04, QA-04, QA-05, OPS-03, OPS-05 | 待补交付证据 |
| OPS-07 | 持续维护 | 后续目录、规则和反馈维护 | 新资料、纠错和规则变更持续对账、复核、失效旧批准并补回归；每批更新进度和 GitHub。 | — | [AGENTS.md](../AGENTS.md) |

## 全目录逐条记录

型号级范围还需跟踪 [73 条目录进度表](series-progress.csv)。其中系列、规格、附件、服务及参考条目不能混为同一种产品验收。
除 HA 本章已建立 36 个芯体订货号基准外，多数类别尚不知道全部 SKU 数量，因此总数一栏保持未知。

## 对外试点的最低条件

必须明确上线系列和工况范围，并满足 REVIEW-05、AGENT-07、APP-04、QA-04、QA-05 和 OPS-06 对应验收。
不要求一次上线所有目录，但必须明确未覆盖的范围；不能把局部试验推广为整本目录可选型。
