# 联合校准能力交接说明

本说明配合 README.md、JOINT.md、PORTS.md 使用；原 SDK1 单站接口、SQLite v1 表与全部原测试保持不变，新增内容只追加。

## 新增模块与固定身份的传递链

- `trend/calibration.py`：`apply_calibration / calibration_head / calibration_revision`。校准修订号来自独立的 `calibration_revisions` 自增主键空间，与序列 `revisions` 主键空间互不影响。request 幂等、冲突与头不倒退的规则与原 `apply` 同构，但使用独立的 `calibration_receipts`。
- `trend/joint.py`：`create_joint_task / joint_task`。整批校验通过后，把校准修订号、原序 bindings（含 series 名、序列修订号、前缀行数、规范有理 loading 字符串）和原序 queries 一次性冻结进 `joint_tasks`。任务只保存整数修订号，不保存任何头引用，因此后续校准或序列更正都无法重绑旧任务。
- `trend/joint_math.py`：独立联合核（全量重算，不读取旧 SDK1 checkpoint）。`build_joint` 按冻结的 binding 顺序把各站 0..8 水平轨迹与唯一一个共享 Z 堆叠成一个联合向量；各站初态/创新块间协方差为零，Z 仅在末位出现一次。`condition_joint` 用各绑定冻结前缀的有效观测逐条条件化，观测行为 `level + a·Z + 独立测量误差`；缺测只推进时间不产生条件。`project_joint` 在同一个后验向量上投影全部跨站、跨时查询，再取 D→+∞ 的精确极限，从不存在“各站分别后验再拼接”的路径。
- `trend/joint_analysis.py`：`analyze_joint`。pending 任务从归档读取冻结的校准修订与每个绑定的序列修订（取其真实 `sdk1_state` 和冻结前缀观测），调用联合核；done 直接回读已发布报告，error 重抛同一 `Inconsistent`。
- `trend/joint_reports.py`：`publish_joint / read_joint_report`。成功在 `publish_joint` 单事务内同时写 `joint_reports`（数值报告＋联合 checkpoint）、done 终态和 `joint_task_receipts`（`joint-analysis:<task>`）；确定矛盾只写 error 终态、错误说明和 error 回执，不写数值报告。提交钩子或存储异常原样传播、整笔回滚，任务保持 pending 且可重试，不会被转成 `Inconsistent`。

## 弥散与可估计性

平坦初态沿用 SDK1 的形式变量 D（`vendor/rational.py` 的 RF），所有联合条件化和投影都在有理函数域完成，最后才取极限。因此共享 Z 把多个平坦站点关联后，单个未来水平仍可能未识别，而确定性恒等式（曲率、差值、空组合）方差为零且可估计；零观测方差的确定条件相容则接纳、矛盾则整次拒绝，空查询也照样核验全部观测。

## 持久化与隔离

- 新表：`calibration_revisions / calibration_heads / calibration_receipts / joint_tasks / joint_reports / joint_task_receipts`，外键开启；旧库重开时由 `CREATE TABLE IF NOT EXISTS` 平滑补齐，不重写任何旧行。
- 联合任务身份与单站任务身份分开（`joint_tasks` 与 `tasks` 独立主键），校准 request 与序列 request 分开。
- 所有写入载荷经 `codec.dumps` 规范化，读取经 `codec.loads` 产生全新对象；输入对象和返回值的后续修改不触及归档。
- 限额：1..4 个绑定、每绑定前缀 0..min(8, 修订行数)、被选时点与查询时点均在 0..8、至多 12 个查询；bool 不被当作整数。

## 核验与演示入口

- `python3.11 -B -m unittest discover -s tests -t . -v`：原 29 个回归加新增 26 个联合核验。
  - `tests/test_joint_audit.py`：手算三场景、独立原始噪声高斯核账（`vendor.gaussian2` 搭建，与联合核无共享代码）、不同载荷与校准均值、正常/平坦混合、过程创新、缺测、相容冗余、确定矛盾、跨时组合及大有限 D 极限对照。
  - `tests/test_joint_archive.py`：校准登记/重放/冲突、联合任务校验与限额、更正后重开的旧 pending/旧 done/error 行为、返回值隔离、`apply_calibration`/`create_joint_task`/`publish_joint` 三个原子边界回滚。
- `python3.11 -B -m trend.demo`：先建原单站样本，再登记校准与联合任务，随后更正校准和两个序列、关闭重开，执行旧 pending 联合任务并展示真实联合报告与冻结来源，同时用更正后的修订建立新联合任务。
