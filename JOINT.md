# 共享校准下的联合趋势报告

README.md、PORTS.md、原接口和原测试继续有效。本次新增能力只使用一个共享校准随机偏移，联合分析若干不同站点的真实水平；不做校准拟合、跨任务随机量联合推断或并行执行。以下入口均新增到 trend.Store。

## 业务模型

每个联合任务固定一个校准修订，其偏移 Z 服从均值 mu、方差 v 的正常分布，v 可以为零。每个站点沿用自己修订的二维趋势模型，初始正常方向、平坦方向和过程创新的语义见 README.md。不同站点的初始方向及创新相互独立，Z 与它们独立。不同站点即使模型、数值或请求文本相同也不因此共享初态或创新。

绑定项的 loading 为有理数 a，可以为负数或零。该项前缀中每条非缺测观测满足：

    observed(t) = level(t) + a * Z + measurement_error(t)

全部有效观测使用同一个 Z，测量误差的方差为原观测行第三项；这些误差逐行独立，并与其他随机量独立。loading 对该绑定的所有观测相同。缺测占一行但不产生观测条件。查询的是 level(t)，不包括 a*Z；查询须以全部绑定的有效观测共同为条件。不能分别求各站后验再合并。相容冗余的确定条件应接纳，确定矛盾应拒绝。

平坦初态沿用 SDK1 的精确弥散语义：每个平坦方向相互独立，以形式方差 D 表示，在完成全部联合条件化和查询投影后取 D 趋于正无穷的极限；不能用有限大方差代替或先丢掉未识别单点。允许复用任意现有数值端口，也允许全量重算；无须优化旧单站分析。

## 校准归档

    apply_calibration(calibration, request, mean, variance)
    calibration_head(calibration)
    calibration_revision(calibration_revision)

calibration 和 request 是非空字符串。mean 和 variance 接受与原接口一致的 int、Fraction 或精确有理字符串，排除 bool 和 float；variance 非负。

apply_calibration 接纳完整不可变校准修订并移动该校准的头，返回：

    {"request": request, "calibration": calibration,
     "calibration_revision": integer_id}

校准修订号为此 Store 内持久、全局唯一的正整数，与原序列修订号属于不同身份空间。校准 request 也与原 apply 的 request 分开；校准 request 在全部校准之间唯一。同 request 同规范内容返回原回执，重放不能倒退头；同 request 不同内容抛 Conflict。

calibration_head 返回当前校准修订号。calibration_revision 返回独立副本：

    {"calibration": name, "calibration_revision": integer_id,
     "mean": canonical_rational_string, "variance": canonical_rational_string}

规范有理字符串使用 str(Fraction(value))。不提供覆盖或删除历史校准修订的接口。未知校准或修订抛 Unknown，非法参数抛 Invalid；失败不改变校准修订、头或回执。

## 固定联合任务

    create_joint_task(task, calibration_revision, bindings, queries)
    joint_task(task)
    analyze_joint(task)
    read_joint_report(task)

task 为非空字符串，联合任务身份与原单站任务身份分开。calibration_revision 必须显式指定，不接受“当前头”之类的动态引用。bindings 是有序 list/tuple，包含 1 至 4 项，每项恰有：

    {"id": "a", "revision": sequence_revision_id,
     "prefix": observation_row_count, "loading": exact_rational}

id 为非空字符串且在任务内唯一；各项必须来自不同 series，不允许同一站点的两个修订或同一修订重复进入任务。revision 指原 apply 的修订，prefix 是冻结的行前缀长度，必须在 0 至 min(8, 该修订行数) 之间。被选前缀的全部时点须在 0 至 8；未选行不参与联合任务，允许它们的时点超过 8。整数身份、前缀、时间均排除 bool。

queries 是有序 list/tuple，至多 12 项，每项恰有：

    {"id": "difference", "terms": [["a", 0, 1], ["b", 0, -1]]}

组合 id 为非空字符串且在任务内唯一。每个 term 是 [绑定id, 时间, 系数]，绑定 id 必须已登记，时间为 0 至 8 的整数，系数沿用精确有理输入规则。允许历史及未来时点、重复项、零系数、空组合和空 queries；即使系数为零也验证绑定和时间。所有被选观测都须参与一致性核验，空 queries 也不例外。

create_joint_task 必须验证整批内容并冻结校准修订、原序 bindings、前缀、loading 和原序 queries，不追随任何头。规范化只转换有理数为标准字符串，保留列表顺序及重复 term。同 task 同规范绑定返回已有任务；不同绑定抛 Conflict，不改变已有任务。未知引用抛 Unknown，非法形状、重复身份、越界或重复 series 抛 Invalid，整次不创建任务。

create_joint_task 和 joint_task 返回下列来源结构，后者从归档读取独立副本：

    {"task": task,
     "calibration": {"calibration": name, "calibration_revision": integer_id,
                     "mean": canonical_string, "variance": canonical_string},
     "bindings": [{"id": binding_id, "series": series_name,
                   "revision": integer_id, "prefix": integer_count,
                   "loading": canonical_string}, ...],
     "queries": normalized_queries,
     "status": "pending" | "done" | "error",
     "error": None | nonempty_error_string}

校准修订、原序列修订和任务均须落在同一 Store 中。输入对象、上述返回对象及报告返回值的后续修改不能改变归档或后续执行。

## 数值成果和发布

analyze_joint 返回与 read_joint_report 相同的完整读取结构：

    {"source": joint_task_result, "status": status, "error": error,
     "report": None | numerical_report, "receipt": None | terminal_receipt}

未知任务抛 Unknown。新建任务为 pending，report 和 receipt 均为 None。成功数值报告沿用原单站结构：

    {"items": [{"id": query_id, "status": "estimable" | "unidentified"}, ...],
     "estimable": [estimable_query_id, ...],
     "mean": [Fraction, ...],
     "covariance": [[Fraction, ...], ...]}

items 保留全部查询原序；estimable 及数值矩阵保留其中可估计组合的相对顺序。必须给出可估计组合的完整联合协方差，包括跨站和跨时项。空组合确定为零。全部数值为精确 Fraction；不要求输出 Z 的后验或新增置信区间。

成功须在同一事务发布完整数值报告、done 状态和回执；回执为：

    {"task": task, "status": "done", "receipt": "joint-analysis:" + task}

确定矛盾抛 trend.Inconsistent，同时只发布 error 状态、非空错误说明和 status 为 error 的同格式回执，不保存数值报告；重复执行仍抛 Inconsistent，归档错误不改变。成功任务重复执行返回原成果，不重新解释当前头。read_joint_report 只读，不触发执行。

新增事务延续 before_commit(label) 的原样异常及整笔回滚规则，label 分别为 apply_calibration、create_joint_task、publish_joint。提交钩子或存储异常不得被转成 Inconsistent；publish_joint 失败后任务仍 pending，报告和回执均不存在，可重试。无需新增进程终止恢复、多工作者或跨库事务协议。

现有归档可以直接重开并使用新能力；保留原业务数据、原接口行为及全部原测试，不重写旧 SDK1 状态或历史报告。后续校准与序列更正不能重绑旧任务。尚未执行的旧联合任务在更正后或关闭重开后仍使用原输入；既有报告保持不变。新联合任务可以绑定新的校准和序列修订。

## 手算示例与交付

joint_examples.py 只提供数据和手算预期，不包含新增能力的实现。每个场景单独建库；先用 apply_calibration 和原 apply 接纳输入，把示例 bindings 中的 series 替换成接纳回执给出的 revision，再创建并分析联合任务。

shared-proper：两个站点初始水平分别独立 N(0,1)，斜率确定为零，无过程噪声；共享 Z~N(0,4)，loading 均为 1。两站零测量噪声下观测 5、7。真实水平 a、b 及 a-b 的后验均值为 -1/3、5/3、-2，前两项方差与交叉协方差均为 4/9，差值方差及其交叉项为零。

shared-diffuse：两站初始水平和斜率都平坦，其他输入不变。t=0 水平均值为 5、7，其方差与交叉协方差均为 4；差值确定为 -2。a 的 t=1 水平未识别，但 a(2)-2*a(1)+a(0) 确定为零。

shared-contradiction：两站真实水平和斜率都确定为零，观测仍为 5、7，同一个 Z 无法同时满足，空查询也须抛 Inconsistent。

交付新增实现及简短交接说明，说明固定身份如何传到联合解释和数值发布。补独立核账，覆盖手算样例、不同载荷和校准均值、正常/平坦混合、过程创新、缺测、相容冗余、确定矛盾及跨时组合；联合验证校准和序列更正后的旧 pending 任务、旧 done 报告、返回值隔离和提交失败回滚。

沿用已有 .pointwise-runtime.json 的运行约定：verify 应执行全部原回归及新增联合核验；demo 应实际建库、登记输入和旧联合任务，更正校准及序列后关闭重开，再执行旧任务并展示真实联合报告及来源。setup 继续记录实际需要的准备命令。核验及演示入口由交付者提供，必须可重跑且实际检查、展示上述业务结果。
