# 归档格式与离线数值端口

本项目的两个 SDK 均有完整源码，仅依赖 Python 标准库。归档当前版本为 1，业务执行调用 SDK1。

## SDK1：vendor.trend1

seed(normalized_model) 返回可持久化的 trend1.initial/1：
mean 是水平、斜率的两个有理函数；covariance 是 2×2 有理函数矩阵；process 保存两个规范有理数字符串。正常方向方差有限，未知方向的方差为形式变量 D。每个 RF 编码为 [分子系数列表, 分母系数列表]，系数为 Fraction 字符串，按常数项到最高次排列，分母首一。这里的 D 不取任何有限大数。

condition(initial_state, observations, horizon) 构造 0..horizon 全部水平的联合轨迹，并按序条件化有效观测。输入为 trend.codec 规范化后的模型/观测数据。调用方保证 horizon 覆盖全部观测时点且为非负整数。返回 trend1.trajectory/1，包含 horizon、mean 和 covariance；维数均对应 0..horizon。所有内部运算都在 Fraction 多项式的有理函数域完成。

project(checkpoint, queries) 在联合轨迹上直接投影组合，再取 D→正无穷的精确极限。方差发散的组合标记 unidentified，有限组合返回 Fraction 均值及完整交叉协方差。它不会逐时点拒绝组合。零条件方差且残差非零时 condition 抛 trend1.Inconsistent；相容冗余条件不影响结果。缺测不产生条件。

示例：初始两方向未知，无过程噪声，t=0 确定观测为5。x(2) 未识别；x(2)-2x(1)+x(0) 确定为0。增加 t=1 确定观测7后，x(2)=9。再增加 t=2 确定观测10则矛盾。

## SDK2：vendor.gaussian2

Normal(mean, covariance) 创建有限正常向量，允许奇异与零维，拒绝非对称或非半正定矩阵。所有值必须为 int、Fraction 或有理数字符串。

- independent(other)：按输入顺序合并两个独立正常向量。
- affine(rows, offset=None, noise=None)：返回 A·X+b+E，E 为独立 Normal；默认偏移和噪声均为零。
- project(rows)：零偏移、零噪声的联合线性投影。
- condition(rows, values, noise=None)：条件化 A·X+E=values，保留 E 的完整噪声协方差；相容冗余约束允许，矛盾的确定条件抛 gaussian2.Inconsistent。返回原 X 的有限正常后验。
- dump()/load(value)：gaussian2.normal/1 的有理数字符串序列化。

SDK2 不接受平坦初始方向，不含趋势模型、弥散极限、归档转换、任务解释或兼容接口。正常端口的独立使用例子：

~~~python
from vendor.gaussian2 import Normal

state = Normal([2, 1], [[4, 0], [0, 1]])
advanced = state.affine([[1, 1], [0, 1]],
                        noise=Normal([0, 0], [[1, 0], [0, 0]]))
assert advanced.mean == (3, 1)
assert advanced.covariance == ((6, 1), (1, 1))
~~~

## SQLite v1

trend.db.SCHEMA 是可执行的唯一 Schema 定义。外键启用。

- metadata：version=1。
- revisions：全局不可变整数 revision 主键、series、payload、sdk1_state。payload 包含 series、完整规范 model 和 observations；sdk1_state 是真实 SDK1 初始状态。
- heads：每序列当前 revision。
- apply_receipts：全局 request 主键、规范请求 payload、接纳 revision、原 receipt。
- tasks：task 主键、固定 revision、prefix、原序 queries、pending/done/error 及错误文本。
- reports：成功 task 主键、result、实际参与计算的 sdk1_checkpoint。
- task_receipts：终态 task 主键与固定回执。

JSON 对象键排序，紧凑编码。Fraction 输出用 {"$fraction":"分子/分母"} 无损编码；trend.codec.loads 会恢复 Fraction。输入规范模型、观测和查询的数值本身以有理数字符串存储；时间和主键保留整数，None 保留 JSON null。

trend.samples.build(store) 使用真实 apply/create_task/analyze 构造完整旧样本。既包含没有执行的冻结任务，也包含成功 SDK1 状态与错误回执；SDK1 状态不是只有 JSON 原文而未使用的占位字段。

reports、任务成功终态、task_receipts 在 publish 事务中同时写入。失败时三者全部回滚。矛盾观测只发布错误终态及回执，不产生 reports 行。修订接纳和头/请求回执也在同一事务。所有历史报告保持其原来源绑定。
