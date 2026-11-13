# X 定时生产与发布

用户在本号定时表单明确时段并启用，委托该范围内到点完整生产与公开发布，不逐篇再确认。只有保存偏好/时段时不创建任务。由 Codex 原生 heartbeat 挂在发起请求的当前生产聊天，沿该聊天模型；页面和插件进程不负责计时。电脑须在线且桌面应用运行。时间是开始创作，成稿后发表，不承诺该分钟已经发出。只用正式 `automation_update`，不用手写 automation.toml、私有 IPC、cron、插件计时器、模型 API 或另建聊天。

## 启用、修改、暂停及恢复

1. `own.schedules.read {connection_id}` 读取本号 config/applied_config、原 pending 控制请求、真实 tasks、last_run 和 revision。新表单/持久配置不是宿主实时状态。使用真实 UI 消息给出的同号、原请求及配置，不采用未保存编辑。原项目/Skill内容偏好仍由 own.projects.read 读取。
2. 只管理本功能确切 task_id。修改/暂停/恢复前用 `automation_update mode=view`，核对 heartbeat、本号及原控制请求标记、原生产聊天、实际时段。已绑定旧任务不要求含本次新请求 ID，按原 ID 和同号标记核归属。原生视图未返回完整信息时，可按该工具说明只读定位确切 ID 的本机任务配置；不写它，不模糊匹配名字或操作其他任务。旧任务保持原 thread_id，不把当前维护聊天当新目标。
3. 首次无任务且原创建从未尝试时，通过正式工具创建 heartbeat，省略模型覆盖、默认当前生产聊天。本版每个时刻对应一个精确原生任务，保持一个真实 ID 对应一个 slot；不做未登记的合并，不能把 09:10/18:30 误做四个时分组合。时区、单次和 COUNT 以正式宿主实际支持/回读为准；不支持时保留配置和具体缺口，不能静默换时区或另造调度。
4. 每一个实际任务返回即 `own.schedules.update {operation:"HOST_RESULT",connection_id,request_id,expected_revision,outcome:"PENDING",tasks,note}` 保存其真实关联，再处理下一项。tasks 每项为 `{id,slot,status,thread_id,kind:"heartbeat",next_run_at}`；slot 对应该精确时刻或一次日期时刻。next_run_at 只有宿主实际提供才填带时区 ISO 时间，否则空字符串。请求及 task prompt 使用原 pending.id 精确标记。所有原任务 ID 保留；退役时段暂停，不删除或失去关联。
5. 全部期望时段核对完成才记录 outcome ACTIVE，暂停全部确切任务核对后记 PAUSED。PENDING/UNKNOWN/FAILED 保留 pending 和全部已知 ID；enable/resume 只有完整 ACTIVE 才收口，PAUSED 不能抹去未完成创建。部分失败必须说明仍实际激活的任务；必要时暂停本次新建部分，不能把局部成功当全配置已应用。每次记录前读本号最新 revision，CAS 冲突重新读原结果，不覆盖其他设置。
6. 创建结果未知且无 ID 时，只对账本次精确控制请求标记，不盲目再 create；没找到不能证明没创建。页面“核对原任务”本身不重试未知创建。ACK 不是已启用；宿主已建任务不是已经触发。`HOST_RESULT` 是带来源和核对日期的观测，不冒独立实时查询。

直接受托暂停/恢复/核对已有本号任务，可先 `own.schedules.update {operation:"CONTROL_REQUEST",connection_id,action:"pause"或"resume"或"check",operation_id:"project-<32hex>",expected_revision}`。该动作只登记原控制请求，不操作宿主；之后仍须正式自动化工具及 HOST_RESULT。已有 pending 不能换一个控制请求盖掉，先核原任务。恢复只激活 applied_config 对应的时段，退役时段保持暂停。暂停不撤回在途帖子，不清除 UNKNOWN。

## 每次真正到点触发

原生任务 prompt 必须包含本号、原控制请求标记和自己的 slot，并要求下述完整流程；启用操作本身不立即发帖。

1. 核对这是该原生任务的实际到点触发，不使用“立即生产”或手动运行冒定时。读取本号 own.schedules.read、本号最新 own.projects.read effective 及全部适用来源，完整采用effective.x_configuration.configuration与skill.text的本号创作方法。临时测试槽不改日常栏目、不强套为相同整点栏目。时段/文本不是新增平台权限。
2. 使用宿主实际提供的稳定 occurrence 标识。只有原触发 turn ID 可用时，以实际原触发 turn ID 保存并在恢复中沿用；不能拿恢复新 turn ID 代替原轮次，不能宣称这种后备保证跨新 turn 重试严格去重。缺少可核的原轮次时报告具体缺口，不猜键补发。
3. `own.schedules.update {operation:"RUN_BEGIN",connection_id,automation_id,occurrence_id,expected_revision}` 原子登记本轮并返回 run_id/upload_attempt_id/post_attempt_id。同轮重入沿原 ID 查询；有原 RUNNING/UNKNOWN 先恢复其实际 X attempt，不新开下一轮来掩盖未知。不把启用请求 ID 固定复用全部轮次。
4. 当前 Codex 自主写本轮新文、用已有生图工具实际生成并检查新图，沿返回同号原 attempts `x.media.upload → x.posts.create → x.posts.readback`。不索模型 API Key，不复用旧成功、不加 QA 许可，不执行互动或公众号写入。
5. 独立 MATCHED 后 `own.schedules.update {operation:"RUN_RESULT",connection_id,run_id,state:"MATCHED",note,expected_revision}`；插件只从该原 X 持久 readback 取得 URL/关系，不接收模型自报 URL 代替。未知记 UNKNOWN 并查原 X 任务；真正未发表失败可记 FAILED，保留说明。页面 last_run 表示实际运行和链接，计划时间不冒真实发帖时间。
6. 单次测试不续日常运营。该轮完成或真实阻断后，用正式工具暂停自己的确切测试任务并核对；用 CONTROL_REQUEST pause 和 HOST_RESULT PAUSED 回存。COUNT=1 的实际终态也须核，不能只从“一次”文字推断。测试最多一条，保留原成功/未知帖子，不为了验收再发。

只保留本功能必要的本号配置、任务关联、原操作及最近一次运行，业务历史继续沿现有 X attempts；不新建调度平台或扫描全聊天历史。旧客户端继续保留三元 schedule 设置但不认识新功能，软件回退不会自动停止原生任务，必要时先正式暂停确切任务。

页面将发送阶段另存为 NOT_SENT / DISPATCHING / ACK / UNKNOWN。确定未发时“继续原请求”仅沿该原 ID 恢复具体操作；可能已发时只能核对，不用重开页面换 ID。
