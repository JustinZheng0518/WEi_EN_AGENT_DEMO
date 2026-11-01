# HA 资料包与数据库差异及补充导入

对照明确的87个资料包订货号（含36芯体），不是重做全目录OCR或推断配对。原数据库另有一个资料包未列的顶进线外壳，不删除。

来源分卷SHA-256、分卷内页码与数据库映射检查通过；实际应用前还核对源PDF字节。所有新增记录均pending，未覆盖旧身份、参数、来源或审核记录。

## 差异统计

| 分类 | 导入前 | 导入后 |
| --- | --- | --- |
| equivalent | 922 | 1032 |
| existing_identity | 79 | 87 |
| new_fact | 90 | 0 |
| new_identity | 8 | 0 |
| new_unknown | 20 | 0 |
| requires_review | 4 | 4 |
| schema_gap | 5 | 5 |

本次实际添加：{"known_facts":90,"products":8,"unknowns":20}。没有新增或批准适配关系，没有工程批准。

equivalent只表示与资料包记录对齐，不代表已审核。new_unknown降为0表示未知占位已写入，新增的20条unknown仍待确认，并非问题已解决。

## 仍需复核的逐项差异

| 型号 | 字段 | 状态 | 旧值 / 状态 | 资料包值 / 状态 | 文件页 |
| --- | --- | --- | --- | --- | --- |
| HA-003-M-V2 | tightening_test_torque | requires_review | 0.25 | unknown | 73 |
| HA-003-F-V2 | tightening_test_torque | requires_review | 0.25 | unknown | 73 |
| HA-004-M-V2 | tightening_test_torque | requires_review | 0.25 | unknown | 73 |
| HA-004-F-V2 | tightening_test_torque | requires_review | 0.25 | unknown | 73 |
| WNA-M20(D4-8) | wrench_size | schema_gap | 无同条件记录 | 22 | 1401 |
| WNA-M20(D6-12) | wrench_size | schema_gap | 无同条件记录 | 22 | 1401 |
| WNA-M20(D8-14) | wrench_size | schema_gap | 无同条件记录 | 24 | 1401 |
| WNA-M25(D9-16) | wrench_size | schema_gap | 无同条件记录 | 27 | 1401 |
| WNA-M25(D13-18) | wrench_size | schema_gap | 无同条件记录 | 30 | 1401 |

requires_review保留原记录，不自动判断哪一方正确；condition_difference不合并条件或重复断言；schema_gap待新增字段迁移后再导入。

## 审核与使用边界

- 本批只补目录事实和明确未知；HA-002普通/PE接点、HA-004-V2线径、V2工艺等仍待确认。unknown没有数值，不等于0或不需要。
- HA-032仍为真实HA-016半组编排；不创建独立HA-032订货号。原有配对/关系及工程结论不增加、不批准。
- 壳体规格、锁扣名称、入口标识仅为产品参数，不证明芯体/壳体或壳体/接头实际适配。
- 线径/剥线的条件保留；压接芯体的7.5mm只针对所列普通压接接触件，不能套给PE。
- 接头温度按static/dynamic分开，不套芯体温度；扳手SW暂列schema_gap，不擅自挪用其他字段。
- 旧批量转录脚本仍针对旧基线；补充后不应盲目重跑以覆盖unknown或工艺更正，应先使用此差异工具。

[下载逐项差异CSV](ha-reconciliation-diff.csv)。完整导入前后计划和校验摘要保存在本地忽略目录，避免把备份、PDF或私有路径提交Git。

## 复现

只读计划：`python -m wain.ha_reconcile plan`。应用：`python -m wain.ha_reconcile apply --expected-plan <计划摘要>`。
应用前备份；应用会重新核对来源、输入和数据库差异摘要，数据变化则拒绝过期计划。写入在事务内串行执行，任何插入/约束失败则整批回滚。
新家族导航关联使用`python -m wain.catalog import`，随后`python -m wain.catalog export`刷新目录报告；这只同步明确的导航映射，不批准适配。
导入会记录ingestion_runs，但不会覆盖等价记录的证据或审核；重跑不重复插入参数。
