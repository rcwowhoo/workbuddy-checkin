# WorkBuddy 自动签到 · GitHub Actions

把签到搬到 GitHub Actions 上定时执行，**不依赖你自己的电脑开机或睡眠**。

---

## 一、目录结构

```
workbuddy-checkin/
├── .github/
│   └── workflows/
│       └── checkin.yml    # GitHub Actions 工作流（定时 09:00 签到）
├── scripts/               # 核心脚本（纯标准库，无需 pip 安装）
│   ├── rt_auth.py         # 主入口：长效令牌通道
│   ├── push_summary.py    # 多账号结果汇总推送
│   └── ...
└── README.md
```

---

## 二、配置步骤（约 5 分钟）

**1. 新建一个私有仓库**（务必私有）

**2. 把本目录推上去**

```bash
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

**3. 取出长效令牌**

打开本机文件 `~/.workbuddy/checkin-rt.json`，复制其中 `"rt"` 字段的值（一长串 `eyJ...` 的 JWT，**不含引号**）。

> ⚠️ **关于「存成 env」**：脚本**只认** `~/.workbuddy/checkin-rt.json` 这个 **JSON 文件**（结构为 `{"rt": "..."}`），**既不读 `.env`，也不读环境变量**。所以正确姿势是：令牌放进 CI Secret（如 `WORKBUDDY_RT`），运行时再用官方命令 `python scripts/rt_auth.py --setup-rt "$WORKBUDDY_RT"` 写入 JSON 文件。
> **千万别**把裸令牌直接写进 `checkin-rt.json`——脚本会 JSON 解析失败并静默忽略（实测 `read_rt()` 返回 `None`）。

**4. 在 GitHub 里配 Secrets**

仓库 → **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名 | 值 | 说明 |
|---|---|---|
| `WORKBUDDY_RT` | 长效令牌 | **多账号用英文逗号拼接**，如 `令牌A,令牌B` |
| `SERVERCHAN_SENDKEY` | Server酱的 SendKey | 签到结果推送到微信 |

> **Server酱**：到 [sct.ftqq.com](https://sct.ftqq.com) 用微信扫码登录，在「SendKey」页复制 `SCT...` 开头的密钥（服务号「方糖」收推送）。工作流会把所有账号的签到结果**汇总成一条**推送（多账号不占多条额度），失败账号带 ❌ 一眼可见。多人可把多个 SendKey 用英文逗号隔开（各自独立额度）。
>
> **多账号**：`WORKBUDDY_RT` 里把各账号令牌用英文逗号拼接（如 `令牌A,令牌B`，令牌本身不含逗号；别加空格），工作流逐个签到，汇总推送形如：
>
> ```
> WorkBuddy 签到 · 2026-10-05
> **账号1** ✅ 领取成功，+100 积分，余额 500
> **账号2** ✅ 今日已签到，余额 320
> ```
>
> 任一账号失败则 job 变红、退出码 1，方便发现令牌失效要续。
>
> 想接钉钉 / 飞书 / 企微等其他 12 类渠道：再加一个 Secret `WORKBUDDY_NOTIFY_CONFIG`（完整 `notify_config.json` 内容，模板用 `python scripts/workbuddy_checkin.py --init-config` 生成），它存在时优先于 `SERVERCHAN_SENDKEY`。

**5. 测试运行**

进入仓库 **Actions → WorkBuddy 自动签到 → Run workflow**（手动触发），看日志里出现 `"status": "ok"` 或 `"action": "skip_already_signed"` 即为成功。

> 手动触发不会产生保活提交，这是刻意的——保活只在定时运行时发生。

---

## 三、cron 说明

```yaml
on:
  schedule:
    - cron: "0 1 * * *"
```

⚠️ **GitHub 的 cron 是 5 段（分 时 日 月 周），且一律按 UTC 计算**，与 Gitee 的 6 段北京时间写法不同。上面这条 = **UTC 01:00 = 北京时间 09:00**。

常用改法（记得减 8 小时换算成 UTC）：

| 需求（北京时间） | cron（UTC） |
|---|---|
| 每天 09:00 | `0 1 * * *` |
| 每天 09:00 和 21:00 | `0 1,13 * * *` |
| 每 2 小时 | `0 */2 * * *` |

> 云端 7×24 在线，正常情况下**每天一次就够**，不必像本地那样高频兜底。
>
> 另外 GitHub 官方明确说明：定时任务在高负载时段**可能延迟几分钟到几十分钟**才启动。签到场景无所谓，不必为此调整。

---

## 四、⚠️ 两个关键风险

### 1. 长期无活动，定时任务会被 GitHub 自动停用

GitHub 会在仓库**连续一段时间没有提交活动**时自动禁用定时任务（官方文档写的是公开仓库 60 天，但私有仓库同样有被停用的报告），届时 Actions 页面会提示：

> *This scheduled workflow is disabled because there hasn't been activity in this repository for at least 60 days.*

**本工作流已在最后一步内置「保活提交」**：每次定时运行都会写一个日期到 `.last-run` 并提交一次，保证仓库始终有活动，不会踩这个坑（手动触发不保活，只有定时运行才保活）。

如果你不希望仓库里出现这类自动提交，可以删掉 `checkin.yml` 末尾的「保活提交」步骤——代价是需要自己每隔一两个月去 Actions 页面点一次 `Enable workflow`。

### 2. 长效令牌是「轮转制」

签到脚本每次运行，都会用旧令牌**换出一个新令牌**（我们本地实测 `rt_rotated: true`）。但 **CI 每次都是一台全新的临时容器**，新令牌会随容器销毁而丢失——下次运行仍旧用 Secret 里的**旧令牌**。

- 如果服务端**没有立即作废旧令牌** → 没问题，当前 `checkin.yml` 直接可用（在 Gitee 上实测通过）。
- 如果服务端**立即作废**（Keycloak 开启 refresh token rotation 时就是如此）→ **第二次运行会失败**，甚至可能触发会话失效。

**验证方法**：连续手动触发两次，两次都成功就无需改动。

如果确实需要自续期，见下方增强版。

### 自续期增强版（把新令牌写回仓库）

用下面的内容替换 `checkin.yml` 里的「逐账号签到」之后的全部步骤，并**额外配置一个 Secret** `WORKBUDDY_RT` 之外的 `GH_PAT`（有 `contents: write` 权限的 GitHub 个人访问令牌；也可以直接用内置 `GITHUB_TOKEN`，但那样可靠性取决于仓库设置）。

```yaml
      - name: 复用令牌并签到，回写轮转后的新令牌
        run: |
          mkdir -p "$HOME/.workbuddy"
          if [ -f .state/rt.json ]; then
            cp .state/rt.json "$HOME/.workbuddy/checkin-rt.json"
          else
            python scripts/rt_auth.py --setup-rt "$WORKBUDDY_RT"
          fi
          python scripts/rt_auth.py --no-travel --no-notify || true
          mkdir -p .state
          cp "$HOME/.workbuddy/checkin-rt.json" .state/rt.json
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"
          git add -f .state/rt.json
          git commit -m "chore: rotate checkin token [skip ci]" || true
          git push || true
```

> 注意：这会把令牌落到**私有仓库**的 `.state/rt.json` 里（每次运行自动更新）。私有仓库 + 令牌本就是账号钥匙，风险可接受；若你不接受，就只能走「自建服务器」路线（容器可持久化磁盘）。
> **必须用 `git add -f`（强制添加）**：本项目 `.gitignore` 里有 `.state/` 规则，普通 `git add` 会被拒绝、新令牌提交不上去，增强版就白配了。`-f` 只放行这一个文件，其余 `.state/` 内容仍被忽略。
> `[skip ci]` 是保险；GitHub 本身不会用 `GITHUB_TOKEN` 推送的提交触发新工作流，不存在死循环风险。

---

## 五、常见问题

| 现象 | 处理 |
|---|---|
| 日志里 `长效令牌刷新失败` / 提示令牌失效 | 令牌已失效：重新在本机导出，更新 GitHub 的 `WORKBUDDY_RT`；若用增强版，同日删除 `.state/rt.json` |
| `getaddrinfo failed` / 连接超时 | Runner 网络无法访问 `copilot.tencent.com` / `www.codebuddy.cn`。GitHub 的机器在海外，多试几次；持续不通则考虑自建 runner |
| 没收到微信推送 | 确认 `SERVERCHAN_SENDKEY` 已配；看日志里的 `[push] 推送结果`；再检查微信服务号「方糖」是否被免打扰 |
| 定时任务不跑了 | 大概率是被自动停用，去 Actions 页面看是否有 "disabled because there hasn't been activity" 提示，点 `Enable workflow`（本项目默认已内置保活提交，正常情况下不会发生） |
| 想用别的推送渠道 | 见上文 `WORKBUDDY_NOTIFY_CONFIG` 说明，配一个完整 notify_config.json 即可 |
| 想跑派猫猫旅行 | 把 `--no-travel` 换成 `--travel-auto`（属写操作，注意每日上限保护） |
| 手动触发按钮找不到 | `workflow_dispatch` 需在**默认分支**上才显示，确认文件已推到默认分支 |

---

## 六、与「自建服务器」的取舍

| | GitHub Actions | 自建 VPS |
|---|---|---|
| 成本 | 私有仓库每月 2000 分钟免费额度（本工作流每次约 1 分钟，一个月约 30 分钟） | 需买机器 |
| 令牌轮转 | 容器无状态，需上文增强版回写 | 磁盘持久，天然支持自续期 |
| 定时可靠性 | 免费且稳定，但高峰可能延迟；长期无活动会被停用（已内置保活） | 完全自主 |
| 网络 | Runner 在海外，访问国内服务可能不稳 | 国内机房最稳 |
| 维护 | 几乎为零 | 需运维 |