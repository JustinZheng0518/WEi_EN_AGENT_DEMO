# HA-010 选型试验

当前范围：10 个普通接点另加 PE，电缆端外壳至面板底座；用户提供线缆。
不覆盖完整线束制造、其他系列或库存/交期查询。所有结果均说明范围。

## 输入与结果

在工作台切换到“HA-010 选型试验”，输入电压、每接点电流、普通接点数量、端接方式、
导线截面、线缆外径、环境温度和套数。未知工况可留空，但最终结果会待确认。

```json
{
  "voltage": 24,
  "current": 3,
  "contacts": 10,
  "termination": "screw",
  "wire_mm2": 1,
  "cable_diameter_mm": 8,
  "ambient_c": 25,
  "quantity": 1
}
```

`POST /selection/ha010` 返回 `bom`、`checks`、`scope` 和 `can_finalize`。
结果只有三类：`passed`、`failed`、`needs_confirmation`。有任何待确认项就不能最终确认。
默认侧进线、压接端子镀银；可通过 `entry_direction` 和 `plating` 明确选择。
`components` 可覆盖特定角色的产品 ID，适合验证错误组合、替换或缺件，不会跳过检查。

当前真实数据全部待审核，因此正常工况也会得到候选方案和具体待办，而非已批准 BOM。
超过候选额定值、超出已记录线径/温度范围、产品类别或接点不符时明确标记不符合。
无足够数据时不把未知当通过。

## 逐项校验

- 芯体公母端、普通接点与 PE、端接方式和外壳规格。
- 参数来源、单位、唯一性和审核状态；多条件值不随便取最大值。
- 线径、接头夹紧范围和材料温度边界；带载能力另需降额核对。
- 产品级配对、芯体与壳体、壳体与接头、压接芯体与端子的关系。
- 额外 `requires_accessory` 依赖递归检查，未知数量/适用条件阻止完整性确认。
- 实际数量和包装取整分别显示；包装数据未经审核时采购数量也不能当作已确认。

主要组件齐全不能替代工程核对，尤其是 PE、接线工艺、密封、锁扣、防呆和安装空间。

## 新增有来源的关系和工程核对

审核页面可查看、编辑和确认已有关系与工程记录。新增使用相应 POST 接口，所有新记录均 pending，
不能通过创建接口直接设置 reviewed。写入同样要求同源 `X-Wain-Review: 1`、审核人标识和依据。
这些是本地工程工具，不是公开可用的多用户认证系统。

适配关系记录需提供两个真实产品 ID、关系类型、明确条件和 `evidence_id`。
确认适配关系前要求两端产品身份和来源已审核；不能依据尺寸相似直接确认。

工程记录需提供 `check_code`、选择报告原样的 `scope`、`findings`、来源证据及依据。
`scope` 包含实际请求工况和每个组件 ID；套数、环境或组件变化后，原结论不再匹配。

| check_code | findings 必需字段 |
| --- | --- |
| derating | `capacity_a`、`voltage_v`，为已核对工况下的数值 |
| mechanical_sealing | `thread_compatible`、`thread_engagement`、`seal_complete`、`locking_compatible`、`ip65_verified`、`all_accessories_accounted_for` |
| pe_termination | `pe_complete` |
| pinout_mounting | `pinout_verified`、`polarization_verified`、`mounting_clearance` |

布尔项只有字面值 `true` 才算肯定结论；数值项必须是正且有限的数字。
来源必须已审核，工程记录本身也必须经审核。相同范围的新冲突覆盖旧批准。
目录关键事实变动会撤回现有工程批准，避免沿用过期结论。
不得为了测试页面显示“通过”而向业务数据库填入虚构结论。

## 验证边界

集成测试既覆盖真实待审核结构的拒绝/待确认路径，也覆盖隔离测试数据全部获审后的放行路径。
测试 schema 在结束时回滚，不会把测试中的批准写进业务数据库。
实际硬件方案需要审核者逐项核对原图和必要的厂家/工程资料，当前没有已确认的硬件组合。
