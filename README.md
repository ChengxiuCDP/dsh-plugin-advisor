# dsh-plugin-advisor

**质量感知的 DeepSeek Harness 插件发现**：在 DSH 里直接用自然语言问你的 agent，得到带质量分、风险徽章与安装命令的插件推荐。

- 零额外 API 费用：排序是纯规则引擎，推荐理由由 agent 自己那一轮思考完成，不调用任何 LLM 接口
- 全量覆盖：内置索引是 dsh-plugin topic 全量仓库（4700+）的每日快照，含质量分（可安装声明 / 精选收录 / 星标 / 活跃度 / 许可证）与功能簇
- 新鲜度兜底：本机有 `gh` CLI 时，每次查询再叠加一次实时 GitHub 搜索

## 安装

```sh
dsh plugin --profile web add -w github:ChengxiuCDP/dsh-plugin-advisor
```

（若 pnpm 未报 workspace root 提示，可去掉 `-w`。）重启 `dsh web` 后生效。

## 使用

直接在对话里说需求：

> 帮我找一个给纯文本模型读图的插件
> 我想在手机上查看会话进度
> 有没有 Claude Code 风格的终端界面？

agent 会调用 `find_dsh_plugins` 工具，给出 Top 匹配、匹配理由、风险提示（NOASSERTION / 无许可证 / 停更）与安装命令。**安装前请自行审阅源码**——推荐 ≠ 安全审计。

## 在线体验

想先看看它能推荐出什么？打开公开站点 **https://dsh-plugin-hub-3t7.pages.dev**（同一套数据与排名引擎，浏览器里直接搜）。

## 数据与更新

- `data/index.json`：全量索引快照（每日由 CI 更新，见 `dsh-plugin-hub` 仓库的数据管道）
- `lib/score.js`：排名引擎（功能位别名表 + 质量分 + 星标对数权重），与公开站点 dsh-plugin-hub 共用同一套逻辑

## 安全声明

安装插件 = 在本机以你的权限运行第三方代码。本工具只做推荐与提示，绝不自动安装。

## License

MIT
