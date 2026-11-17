# 精确趋势归档

Python 3.11 标准库产品库：接纳监测序列的完整观测修订，冻结观测前缀和预测组合，执行精确分析，保存可复查的联合报告。无需安装依赖。

运行完整回归与演示：

~~~sh
python3.11 -B -m unittest discover -s tests -t . -v
python3.11 -B -m trend.demo
~~~

演示在测试临时目录构造 SQLite 归档，关闭后重开，展示历史绑定、未识别量、确定组合、混合初始分布及拒绝的矛盾观测。建立可保留的有限旧库样本：

~~~sh
python3.11 -B -m trend.samples example.sqlite
~~~

该命令只创建指定的项目内数据库。重复调用使用相同请求和任务身份，不追加重复修订，不倒退序列头。

## 业务 API

~~~python
from trend import Store

model = {"initial": [None, None], "process": [0, 0]}
with Store("example.sqlite") as store:
    receipt = store.apply("station-a", "observations-1", model, [[0, 5, 0]])
    revision = receipt["revision"]
    store.create_task("forecast-1", revision, 1, [
        {"id": "future", "terms": [[2, 1]]},
        {"id": "curvature", "terms": [[2, 1], [1, -2], [0, 1]]},
    ])
    report = store.analyze("forecast-1")
    assert report["report"]["items"][0]["status"] == "unidentified"
    assert report["report"]["mean"] == [0]
    assert store.read_report("forecast-1") == report
~~~

初始水平、斜率各自为 None（未知平坦方向），或 [均值, 方差]（独立正常方向）。初始零方差代表确定值。过程参数为 [水平创新方差, 斜率创新方差]。每个整数步执行：

    level(t+1) = level(t) + slope(t) + level_noise(t+1)
    slope(t+1) = slope(t) + slope_noise(t+1)

所有创新相互独立，且独立于初始正常方向。观测行是 [非负整数时间, 值或None, 测量噪声方差]，观测水平，时间严格递增。缺测占前缀的一行，模型仍推进时间，但不构成测量。输入数值接受 int、Fraction、精确有理数字符串；拒绝 bool、float 和负方差。

apply 保存完整替换修订，并移动序列头；不把新行追加到旧修订。同请求同规范内容返回原回执，同请求不同内容抛 Conflict，重放旧请求不会倒退头。可用 head(series) 和 revision(revision_id) 复查依据。任务必须显式给出修订，不会隐式追随头。

create_task(task, revision, prefix, queries) 的 prefix 是观测行数，范围为零至该修订行数。查询为有序具名水平线性组合，每个 terms 元素是 [时间, 系数]。允许重复时间、零系数、空组合、空查询列表和任意非负整数时点，包括历史时点。组合 ID 必须唯一。任务身份重复只接受同一绑定。

analyze(task) 使用冻结前缀计算，并原子保存结果、SDK1 联合状态、成功终态与回执。read_report(task) 返回 source、status、error、report、receipt。source 包含序列、修订、前缀与查询顺序。未知身份抛 Unknown；已建未执行任务返回 pending，report 和 receipt 均为 None。成功重复执行返回相同归档报告。

report.items 按查询原序返回 estimable 或 unidentified。report.estimable 给出可估计组合的原序 ID；mean 为对应 Fraction 列表；covariance 为该列表的完整联合协方差。未识别组合不进入数值矩阵。不能从未识别单点推断其全部差值也未识别。

确定约束矛盾抛 Inconsistent，同时原子记录 error 终态和错误回执；不保存任何数值报告或轨迹。重复执行该错误任务仍抛同一业务错误。非法输入、未知修订或越界前缀不产生接纳回执或新任务。存储或提交钩子异常原样传播，当前事务全部回滚，未发布任务可重试。

Store 是单工作者、维护窗口使用的连接对象。transaction(label) 提供真实 SQLite 原子事务；maintenance(callable) 在同一事务中调用维护函数。可选 before_commit(label) 钩子在 apply、create_task、publish 或 maintenance 提交前执行，抛异常将回滚；没有进程终止恢复或多工作者协调承诺。

## 文件职责

- trend/series.py：完整修订、头与请求回执。
- trend/tasks.py：固定任务与组合身份。
- trend/analysis.py：SDK1 精确分析。
- trend/reports.py：数值报告、终态、回执的整笔发布和读取。
- trend/calibration.py：共享校准修订、校准头与校准请求回执。
- trend/joint.py：固定联合任务的整批校验、冻结绑定与来源读取。
- trend/joint_math.py：共享单个 Z 的全量精确联合核（形式 D 弥散极限）。
- trend/joint_analysis.py：按冻结绑定执行联合分析。
- trend/joint_reports.py：联合报告、终态与回执的整笔发布和读取。
- trend/db.py：SQLite Schema、事务、公开 Store 门面。
- trend/samples.py：通过公开接口构造五个修订、六个任务，包含 pending/done/error。
- vendor/trend1.py、vendor/rational.py：实际使用的旧数值端口和精确弥散运算。
- vendor/gaussian2.py：可独立使用的正常高斯端口，不接入当前归档。
- tests/：完整原业务回归、数值端口对照与独立联合核账。
- JOINT.md、JOINT_HANDOFF.md：共享校准联合任务的业务规范与交接说明。

共享校准联合能力（`apply_calibration`、`create_joint_task`、`analyze_joint` 等）的完整接口、数值语义、固定身份与原子边界见 JOINT.md，实现到发布的传递链与核验入口见 JOINT_HANDOFF.md；手算数据见 joint_examples.py。

状态格式、表关系与数值端口见 PORTS.md。当前产品不做模型拟合、季节模型、在线迁移或可视化。
