---
name: x-developer-app-setup
description: Help users create or configure their own X Developer Native App for OpenAhoy in the Codex in-app browser. Use for Developer Console setup, OAuth Client ID, callback, or migrating an existing X connection to the user's app. For ordinary X publishing or balance checks, use the OpenAhoy account skill.
---

# X 开发者应用设置

从 OpenAhoy「X → 账号授权 → 让 Codex 协助创建 X 应用」或用户在聊天中的明确委托开始。页面发来的现有连接 ID 只用于定位用户所选账号。用 `x.connections.list` 取得该连接的公开名称、用户名和用户 ID；没有绑定时，以用户已登录的 X 官方页面和当前委托为准。在插件内绑定是创建应用后的 OAuth 步骤。已有社交账号信息不能证明其开发者账户归属、项目权限或付款身份。

## 在官方控制台完成表单

1. 用 Codex 内置浏览器打开 [X Developer Console](https://console.x.com/)，复用已有标签。读取页面可见的账号与项目，匹配用户选定的 X 身份。登录、身份验证与条款由用户本人处理。开发者账户或项目归属不明确时，请用户确定后继续。不要从 Cookie、浏览器储存或内部 API 取得会话。
2. 首次加入 X Developer Program 时，表单可见后先预填公开的 **Account Name** 和 **用途说明**。Account Name 建议 `OpenAhoy - <当前 X 账号名称>`。用途符合本次委托时使用下面的英文。填完请用户核对表单，亲自完成需要的登录确认、协议勾选和开户提交。已有开发者账户直接进入 Apps。

   **Developer Program 用途说明**

   > I use OpenAhoy to read posts from my own X account, publish text with images or video, verify links to published posts, and check my X API credit balance.

   首次开户表单的用途说明至少填写 100 字符。若按用户的实际用途调整，填写后核对页面字符计数与校验提示。上面这段也在 200 字符以内。

3. 在 Apps 中优先复用已确认属于同一用途的应用，包括 X 自动创建的应用。确需新建时，**App Name** 建议 `OpenAhoy - <当前 X 账号名称>`，控制在 32 字符内，过长或重名优先用唯一的 `OpenAhoy - @username`。有可见图标上传入口且用户同意时，才使用已核实的该 X 账号公开头像。网站字段使用用户提供或已核实归属的公开网站。若表单有 **App Description**，按应用实际用途填写下列描述，控制在 200 字符内。

   > OpenAhoy helps me read my X posts, publish text with images or video, verify links to published posts, and check my X API credit balance.

4. 依 [X 官方 OAuth 指南](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code) 和实际表单设置 **OAuth 2.0、Native App、Read and write**。使用 OpenAhoy「账号授权」显示的回调，由插件维护源提供。当前回调为 `http://127.0.0.1:62197/x/callback`。当宿主能读到面板时优先取页面值，遇到不一致停止核对。当前浏览器工具或站点必须由用户确认时，先把公开字段填好，再明确指出剩余要点。保持同一应用进行创建和保存。提交结果不明先查 Apps，避免再次点击。购买额度、支付和消费上限不属于创建流程。
5. 核对当前官方应用、开发者账户及 X 账号。用浏览器定点读取明确标为 **OAuth 2.0 Client ID** 的公开字段，只返回其值。页面可能含 Client Secret 时，不截屏、不读取整页文本或快照、不使用剪贴板读取。不确定字段时由用户在原页面复制公开 ID。已绑定账号用 `x.connections.list` 核对官方可见的 @用户名和稳定用户 ID。新账号只有在官方界面提供可验证用户 ID 时才走自动回填，不能凭显示名猜 ID。
6. 当前聊天若收到原面板的一次性回填标识，且账号身份、应用和公开 ID 都已确认，调用 `x.setup.draft.submit`，仅传该标识、X 用户 ID、应用名和公开 Client ID。成功只代表提交草稿，原面板在账号未切换且输入框为空时才会接收。缺标识、原面板不可用、过期或值不可靠时，保留现有内容，指引用户粘贴公开 Client ID。已确认且应用名为空时可协助填名称。标识只用于本次调用，不回显。原账号从「连接自己的 X 开发者应用」或「管理自己的 X 开发者应用」进入，新号从「绑定 X 账号」进入。两种情况均在同一引导中选择「前往 X 授权」。X 官方授权由用户本人确认，回调核对原用户 ID。成功后按当前授权核对本号资料，并在内嵌「账单与余额」刷新，核对总额、免费额度和来源。账单不可读时报告 X 的实际状态。
7. 回报已填、已创建、OAuth 设置及插件绑定分别处于什么状态。用户或工具实际授权不足时保留已填写的表单或原应用。浏览器能力缺失时提供 [控制台入口](https://console.x.com/) 和本次已知字段，让用户继续，不自行换用其他浏览器、私有 API 或凭据。

只带入公开表单信息。应用创建和设置保存按本次委托与浏览器确认执行。密码、验证码、Client Secret、API Key、Bearer Token、回调 code、OAuth verifier 均由官方安全流程处理或保留在原处。不会因创建委托自动发帖。
