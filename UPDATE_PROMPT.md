# 升级 OpenAhoy

本发行源为公开 https://github.com/OpenAhoy/OpenAhoy-Releases ，不访问私有开发仓库。内嵌页面发起升级只是向当前 Codex 发送请求，安装由宿主官方命令完成。

读取目标固定标签 README.md / RELEASE.json / SHA256SUMS / package-manifest.json 并核全部payload。当前固定发行 v0.6.28。先检查实际来源；官方 `codex plugin marketplace upgrade` 会保留已选Git ref，固定旧tag时应沿官方marketplace remove/add改到用户指定新tag，然后执行 `codex plugin add wechat-ecosystem@openahoy-distribution`。只移除旧marketplace登记，不卸载插件、不删除用户数据；核对官方当前命令实际行为，失败停止说明，不修改供应商缓存。

保留所有已有绑定、系统钥匙串、账号/项目配置、原稿、历史和UNKNOWN请求。未指定替换个人规则时不覆盖。不要复制他人的配置；不重绑、不代开平台授权、不以升级生产或发文。宿主重载确实不可用时再一次性提示用户，不无条件要求重启。

旧私有源安装不会被本公开Release自动改变；用户选择迁移到公开marketplace时再沿官方入口操作。技术插件ID wechat-ecosystem 与平台持久数据ID继续兼容。
