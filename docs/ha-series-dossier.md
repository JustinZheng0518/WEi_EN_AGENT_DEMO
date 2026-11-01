# HA 全系列资料与链路总表

范围：2025 英文目录 HA 本章（文件第 72–79 页）。本批查看 20 页原图，整理日期：2026-10-31（America/Denver）。

**36 个芯体订货号、18 种变体链路均已纳入资料包；所有型号、关系和总成仍待独立审核与工程确认。** 未把目录整理称为完整自动选型或真实硬件验收。

## 交付入口

- [36 个型号逐项资料卡](ha-series-models.md)：参数、来源、端接工艺、图纸定位、可选件及缺项。
- [型号参数 CSV](ha-series-models.csv) · [18 条链路 CSV](ha-series-routes.csv) · [43 条附件/工具 CSV](ha-series-accessories.csv) · [问题清单 CSV](ha-series-issues.csv)。CSV 用 Excel 按文本导入，订货号保持文本。
- [完整 JSON](../data/ha_series_dossier.json) · [可编辑补充转录](../data/ha_dossier_supplement.json)；不包含原 PDF、原图或凭证。

## 范围和数量口径

36 个芯体包括 6 个 (17-32) 编号半组。18 条链路是 15 种普通变体加 3 种 HA-032 组合，属于明确的资料分组，不是 18 个已批准搭配。

HA-032 每套含 4 个芯体：公端 1–16 和 17–32 各一个，母端同样两个；不存在独立 HA-032 订货号。32 路压接全装时普通公、母接触件各 32 个，PE 另核实，不能简单把半组 PE 数相加作为总成定义。

壳体仅整理四种规格的标准金属侧进线到面板候选，共 8 个订货号；未穷举塑料、EMC、耐腐蚀、高构型、顶进线、电缆对电缆等全部变体。电缆接头按 M20/M25 列 5 个候选，需实际外径和螺纹/密封依据才能选定。

这份资料包生成器不写数据库，也不扩展原网页选型服务：网页仍限定 HA-010。单独的来源核对和待审核补充导入见 [数据库差异与导入结果](ha-reconciliation.md)，没有新增已批准配对。

## 参数与工艺中容易混淆的地方

- HA-002/003/004：10 A；230 V 导体对地、400 V 导体对导体。替代标识及 UL 600 V 单独保留，不能统一取最大值。
- HA-010/016：16 A、250 V、污染等级 3；污染等级 2 的 250/400 V 标识另列，实际工况及降额未批准。HA-032 组合页另标 250 V、16 A，但没有独立 HA-032 降额曲线。
- 螺钉普通 HA-003：0.75–1.5 mm²、0.25 N·m；HA-003-V2 线径为 0.75–2.5 mm²，但 V2 扭矩/剥线需变体确认。HA-004-V2 线径保持未知。
- 螺钉 HA-010/016：0.75–2.5 mm²、0.5 N·m；工艺页 00-09 给 HA-003/004 剥线 4.5 mm、HA-010/016/032 为 7.5 mm。通用表未单列 V2；不据此覆盖专用参数或批准 PE 紧固点。
- 普通弹簧：0.14–2.5 mm²；HA 普通弹簧剥线仍未知。00-14 页列的是 HE/HVE 等，不能直接套其 7–9 mm。Quick-in 为 0.5–2.5 mm²、剥线 10±0.5 mm，独立记录。
- 压接接触件：32 个订货号，分公母、银/金镀层、8 档线径；最小档 0.14–0.37 mm²，其余按明确规格，不把相邻规格插值为连续适用。剥线 7.5 mm。
- 0.14–0.37 mm² 按 HA 页选 TL02；工具页明确 TL02G 不适合 16 A、0.37 mm² 接触件。小于 0.75 mm² 推荐 TL15 辅助装针；TL01 用于退针。工具不计入成品数量。
- CODE-Q3 仅列于 HA-003-V2 和 HA-003 Quick-in；CODE-Q5 仅列于 HA-004 Quick-in。不把编码件认定为所有 HA 的必需件。
- 芯体 −40～125 ℃不代表总成范围；接头静态 −40～100 ℃、动态 −20～80 ℃。接头 IP68（with O-sealing）不提升金属壳体总成为 IP68。

## 四种壳体规格的候选主件

| 规格 | 侧进线外壳 / 订货号 | 面板底座 / 订货号 | 文件页 | 入口标识 |
| --- | --- | --- | --- | --- |
| 3A | H3A-SE-2B-M20 / 1100035101002 | H3A-BK-1L/W / 1100033241001 | 454 / 454 | M20 |
| 10A | H10A-SE-2B-M20 / 1100105101002 | H10A-BK-1L/SC / 1100103211001 | 469 / 470 | M20 |
| 16A | H16A-SE-2B-M20 / 1100165101002 | H16A-BK-1L/SC / 1100163211001 | 472 / 473 | M20 |
| 32A | H32A-SE-4B-M25 / 1100325301003 | H32A-BK-2L/SC / 1100323411001 | 474 / 474 | M25 |

“3A / 10A / 16A / 32A”在此为壳体规格代号，不是额定电流。每条链路外壳和面板底座候选各 1 个；芯体装配、锁扣与随件仍需核实。

## 18 条链路逐项清单

下列公母分组来自同变体订货行，暂不固定供电侧和安装性别；不得视为已审核 mates_with。压接接触件数量按一套、普通孔位全装计算，型号需另按线径与镀层选定。

### HA003-SCREW

- 端接：螺钉；每端普通接点：3；壳体规格：3A。
- 公端：HA-003-M（1210030110001）×1。
- 母端：HA-003-F（1210030210001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA003-V2

- 端接：螺钉；每端普通接点：3；壳体规格：3A。
- 公端：HA-003-M-V2（1210030110505）×1。
- 母端：HA-003-F-V2（1210030210505）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：CODE-Q3。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL、V2-PROCESS。

### HA004-V2

- 端接：螺钉；每端普通接点：4；壳体规格：3A。
- 公端：HA-004-M-V2（1210040110002）×1。
- 母端：HA-004-F-V2（1210040210002）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA004V2-WIRE、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL、V2-PROCESS。

### HA002-SPRING

- 端接：普通弹簧；每端普通接点：待确认；壳体规格：3A。
- 公端：HA-002-MS（1210020120001）×1。
- 母端：HA-002-FS（1210020220001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA-SPRING-STRIP、HA002-CONTACTS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA003-SPRING

- 端接：普通弹簧；每端普通接点：3；壳体规格：3A。
- 公端：HA-003-MS（1210030120001）×1。
- 母端：HA-003-FS（1210030220001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA-SPRING-STRIP、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA004-SPRING

- 端接：普通弹簧；每端普通接点：4；壳体规格：3A。
- 公端：HA-004-MS（1210040120001）×1。
- 母端：HA-004-FS（1210040220001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA-SPRING-STRIP、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA003-QUICK

- 端接：Quick-in；每端普通接点：3；壳体规格：3A。
- 公端：HA-003-MQ（1210030010001）×1。
- 母端：HA-003-FQ（1210030020001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：CODE-Q3。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA004-QUICK

- 端接：Quick-in；每端普通接点：4；壳体规格：3A。
- 公端：HA-004-MQ（1210040010001）×1。
- 母端：HA-004-FQ（1210040020001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：CODE-Q5。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA010-SCREW

- 端接：螺钉；每端普通接点：10；壳体规格：10A。
- 公端：HA-010-M（1210100110001）×1。
- 母端：HA-010-F（1210100210001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA010-PROTECT

- 端接：螺钉；每端普通接点：10；壳体规格：10A。
- 公端：HA-010-M/B（1210100110503）×1。
- 母端：HA-010-F/B（1210100210503）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA010-CRIMP

- 端接：压接；每端普通接点：10；壳体规格：10A。
- 公端：HA-010-MC（1210100100001）×1。
- 母端：HA-010-FC（1210100200001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 普通公、母压接接触件各 10 个，PE 另核实；候选工具 TL02/TL02G/TL01/TL15 按条件选用。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：CRIMP-PROCESS、DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA010-SPRING

- 端接：普通弹簧；每端普通接点：10；壳体规格：10A。
- 公端：HA-010-MS（1210100120001）×1。
- 母端：HA-010-FS（1210100220001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA-SPRING-STRIP、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA016-SCREW

- 端接：螺钉；每端普通接点：16；壳体规格：16A。
- 公端：HA-016-M（1210160110001）×1。
- 母端：HA-016-F（1210160210001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA016-PROTECT

- 端接：螺钉；每端普通接点：16；壳体规格：16A。
- 公端：HA-016-M/B（1210160110505）×1。
- 母端：HA-016-F/B（1210160210505）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA016-CRIMP

- 端接：压接；每端普通接点：16；壳体规格：16A。
- 公端：HA-016-MC（1210160100001）×1。
- 母端：HA-016-FC（1210160200001）×1。
- 电缆接头候选：WNA-M20(D4-8)、WNA-M20(D6-12)、WNA-M20(D8-14)；尚未选定。
- 普通公、母压接接触件各 16 个，PE 另核实；候选工具 TL02/TL02G/TL01/TL15 按条件选用。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：CRIMP-PROCESS、DERATING、DRAWINGS、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA032-SCREW

- 端接：螺钉；每端普通接点：32；壳体规格：32A。
- 公端：HA-016-M（1210160110001）×1；HA-016-M(17-32)（1210160110002）×1。
- 母端：HA-016-F（1210160210001）×1；HA-016-F(17-32)（1210160210002）×1。
- 电缆接头候选：WNA-M25(D9-16)、WNA-M25(D13-18)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA032-PE、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA032-PROTECT

- 端接：螺钉；每端普通接点：32；壳体规格：32A。
- 公端：HA-016-M/B（1210160110505）×1；HA-016-M/B(17-32)（1210160110504）×1。
- 母端：HA-016-F/B（1210160210505）×1；HA-016-F/B(17-32)（1210160210504）×1。
- 电缆接头候选：WNA-M25(D9-16)、WNA-M25(D13-18)；尚未选定。
- 不另购压接接触件；PE及导线端头工艺另核对。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：DERATING、DRAWINGS、HA032-PE、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

### HA032-CRIMP

- 端接：压接；每端普通接点：32；壳体规格：32A。
- 公端：HA-016-MC（1210160100001）×1；HA-016-MC(17-32)（1210160100002）×1。
- 母端：HA-016-FC（1210160200001）×1；HA-016-FC(17-32)（1210160200002）×1。
- 电缆接头候选：WNA-M25(D9-16)、WNA-M25(D13-18)；尚未选定。
- 普通公、母压接接触件各 32 个，PE 另核实；候选工具 TL02/TL02G/TL01/TL15 按条件选用。
- 可选编码件：本章无此变体的明确编码件适用声明。
- 待确认：CRIMP-PROCESS、DERATING、DRAWINGS、HA032-PE、MATING、OPTIONAL-SUPPLY、PE-WIRING、THREAD-SEAL。

## 未解事项与技术确认

| ID | 事项 | 需要取得的依据 | 文件页 |
| --- | --- | --- | --- |
| HA002-CONTACTS | HA-002普通接点及PE定义 | 订货行存在，但技术页接点清单无2且页头3/4+PE；需要厂家明确，数量不按型号数字推断 | 73 / 74 |
| HA004V2-WIRE | HA-004-V2线径 | 需要V2专用线径范围，不能套HA-003-V2或HA-004普通款 | 73 / 75 |
| V2-PROCESS | V2端接工艺 | 核实扭矩、剥线、导体和端头；通用工艺页未单列V2 | 64 / 73 / 75 |
| HA-SPRING-STRIP | HA普通弹簧剥线与端头 | 00-14工艺表只列HE/HVE等；需HA专用剥线长度，核对Not suitable for connecting terminal含义 | 69 / 73 / 74 / 76 |
| HA032-PE | HA-032组合PE与安装 | 每端2个16接点半组；不能简单把两个PE相加当成已核实总成定义；核对方向、编号和32A安装 | 73 / 78 / 474 |
| DERATING | 降额与实际工况 | 确认AC/DC、标准、电位关系、同时载流数量、线径和温度；HA032没有独立载流曲线，不直接照搬HA016 | 73 / 78 |
| DRAWINGS | 尺寸、针位与安装审核 | 已定位各款视图及开孔，但未完整数字化全部尺寸；核对基准、单位、板厚、紧固件、干涉；裸芯体开孔不能套给底座 | 74 / 75 / 76 / 77 / 78 / 454 / 470 / 473 / 474 |
| MATING | 真实配对与公母位置 | 目录同行是候选分组，不是已批准mates_with；核实供电侧、防触电、编码、针位和芯体装壳 | 74 / 75 / 76 / 77 / 78 |
| THREAD-SEAL | 螺纹、锁扣与总成密封 | M20/M25字样不证明螺距和啮合长度；核实锁扣、O形圈、面板垫片、螺母和随件，再判断目标IP | 445 / 454 / 469 / 470 / 472 / 473 / 474 / 1401 |
| PE-WIRING | PE、线缆和外部供料 | 核实两侧PE端接及壳体接地连续性、导线长度/绝缘/线色/线序、设备端子和剥线；未知数量不记0 | 73 / 74 / 75 / 76 / 77 / 78 |
| CRIMP-PROCESS | 压接接触件与工具工艺 | 按线径/镀层选择接触件，普通孔位数量不含PE；小线径工具、压模定位、拉力与压接质量需确认 | 76 / 77 / 78 / 1396 / 1399 |
| OPTIONAL-SUPPLY | 选配、随件和采购 | 编码/保护盖按需求选择；确认螺钉、垫片、锁扣等是否随件，缺失件补订货号/数量；确认MOQ及整包装规则 | 74 / 75 / 445 / 454 / 470 / 473 / 474 / 1401 |

所有链路还需确认实际电压、电流、同时载流、线径、外径、温度、用途、防护、公母安装方向、PE、紧固件、密封及随件范围。线缆/面板内导线/设备端子/保护盖等未选定项数量保持未知，不当作不需要。

向厂家或公司技术人员询问时，应带上链路 ID、全部候选订货号及真实工况，要求逐项提供配对、安装图、端接工艺、PE、降额与附件清单依据。本批未对外发送信息。

## 来源与复现

| 文件页 | 印刷页 | 来源分卷 | 分卷内页 |
| --- | --- | --- | --- |
| 64 | 00-09 | 2025 WAIN Complete Product Catalog_51-100.pdf | 14 |
| 69 | 00-14 | 2025 WAIN Complete Product Catalog_51-100.pdf | 19 |
| 72 | 01-01 | 2025 WAIN Complete Product Catalog_51-100.pdf | 22 |
| 73 | 01-02 | 2025 WAIN Complete Product Catalog_51-100.pdf | 23 |
| 74 | 01-03 | 2025 WAIN Complete Product Catalog_51-100.pdf | 24 |
| 75 | 01-03.1 | 2025 WAIN Complete Product Catalog_51-100.pdf | 25 |
| 76 | 01-04 | 2025 WAIN Complete Product Catalog_51-100.pdf | 26 |
| 77 | 01-05 | 2025 WAIN Complete Product Catalog_51-100.pdf | 27 |
| 78 | 01-06 | 2025 WAIN Complete Product Catalog_51-100.pdf | 28 |
| 79 | 01-07 | 2025 WAIN Complete Product Catalog_51-100.pdf | 29 |
| 445 | 15-02 | 2025 WAIN Complete Product Catalog_401-450.pdf | 45 |
| 454 | 15-08 | 2025 WAIN Complete Product Catalog_451-500.pdf | 4 |
| 469 | 15-17 | 2025 WAIN Complete Product Catalog_451-500.pdf | 19 |
| 470 | 15-18 | 2025 WAIN Complete Product Catalog_451-500.pdf | 20 |
| 472 | 15-19 | 2025 WAIN Complete Product Catalog_451-500.pdf | 22 |
| 473 | 15-20 | 2025 WAIN Complete Product Catalog_451-500.pdf | 23 |
| 474 | 15-21 | 2025 WAIN Complete Product Catalog_451-500.pdf | 24 |
| 1396 | 32-03 | 2025 WAIN Complete Product Catalog_1351-1400.pdf | 46 |
| 1399 | 32-05 | 2025 WAIN Complete Product Catalog_1351-1400.pdf | 49 |
| 1401 | 32-07 | 2025 WAIN Complete Product Catalog_1401-1424.pdf | 1 |

本章 72/79 为封面及应用图，不作为新增订货号来源。JSON 保存各分卷 SHA-256；本批所有来源均查看原图，未以 OCR 单独批准事实。

生成：`python scripts/ha_dossier.py`；检查：`python scripts/ha_dossier.py --check`。修改既有资料后应重建并核对；数据审核和真实工程批准继续走审核流程。
