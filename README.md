# WorkBuddy 自动签到 · Gitee Go 流水线

把签到搬到 Gitee Go 上定时执行，**不依赖你自己的电脑开机或睡眠**。

---

## 一、目录结构

```
workbuddy-checkin-gitee/
├── .workflow/
│   └── checkin.yml        # Gitee Go 流水线定义（定时 09:00 签到）
├── scripts/               # 核心脚本（纯标准库，无需 pip 安装）
│   ├── rt_auth.py         # 主入口：长效令牌通道
│   └── ...
└── README.md
```

---

## 二、配置步骤（约 5 分钟）

**1. 新建一个私有仓库**（务必私有）

**2. 把本目录推上去**

```bash
cd workbuddy-checkin-gitee
git init
git add -A
git commit -m "init: workbuddy checkin pipeline"
git remote add origin https://gitee.com/<你的用户名>/<仓库名>.git
git push -u origin master
```

**3. 取出长效令牌**

打开本机文件 `~/.workbuddy/checkin-rt.json`，复制其中 `"rt"` 字段的值（一长串 `eyJ...` 的 JWT，**不含引号**）。

> ⚠️ **关于「存成 env」**：脚本**只认** `~/.workbuddy/checkin-rt.json` 这个 **JSON 文件**（结构为 `{"rt": "..."}`），**既不读 `.env`，也不读环境变量**。所以正确姿势是：令牌放进环境变量 / CI Secret（如 `WORKBUDDY_RT`），运行时再用官方命令 `python scripts/rt_auth.py --setup-rt "$WORKBUDDY_RT"` 写入 JSON 文件。
> **千万别**把裸令牌直接写进 `checkin-rt.json`——脚本会 JSON 解析失败并静默忽略（实测 `read_rt()` 返回 `None`）。

**4. 在 Gitee 里配环境变量**

仓库 → 管理 → **环境变量 / 密钥管理** → 新增：

| 变量名 | 值 | 说明 |
|---|---|---|
| `WORKBUDDY_RT` | 上一步的令牌 | 建议勾选「私密」，不要把值提交进仓库 |
| `SERVERCHAN_SENDKEY` | Server酱的 SendKey | 勾选「私密」；签到结果推送到微信 |

> **Server酱**：到 [sct.ftqq.com](https://sct.ftqq.com) 用微信扫码登录，在「SendKey」页复制 `SCT...` 开头的密钥（服务号「方糖」收推送）。流水线签到后会自动推送「签到成功 +N 积分」或「今日已签到」，失败也会告警。多人可把多个 SendKey 用英文逗号隔开（各自独立额度）。
>
> 想接钉钉 / 飞书 / 企微等其他 12 类渠道：再加一个私密变量 `WORKBUDDY_NOTIFY_CONFIG`（完整 `notify_config.json` 内容，模板用 `python scripts/workbuddy_checkin.py --init-config` 生成），它存在时优先于 `SERVERCHAN_SENDKEY`。

**5. 启用流水线并测试**

进入 **Gitee Go → 流水线**，选择 `.workflow/checkin.yml`，先点「**测试运行**」跑一次，看日志里出现 `"status": "ok"` 或 `"action": "skip_already_signed"` 即为成功。

---

## 三、cron 说明

```yaml
schedule:
- cron: "0 0 9 * * ?"
```

Gitee 的 cron 是 **6 段**：`秒 分 时 日 月 周`。上面这条 = **每天 09:00**（北京时间）。

常用改法：

| 需求 | cron |
|---|---|
| 每天 09:00 | `0 0 9 * * ?` |
| 每天 09:00 和 21:00 | `0 0 9,21 * * ?` |
| 每 2 小时 | `0 0 */2 * * ?` |

> 云端 7×24 在线，正常情况下**每天一次就够**，不必像本地那样高频兜底。

---

## 四、⚠️ 关键风险：长效令牌是「轮转制」

这是本方案最容易踩的坑，务必先读：

签到脚本每次运行，都会用旧令牌**换出一个新令牌**（我们本地实测 `rt_rotated: true`）。但 **Gitee 流水线每次都是一台全新的临时容器**，新令牌会随容器销毁而丢失——下次运行仍旧用 Secret 里的**旧令牌**。

- 如果服务端**没有立即作废旧令牌** → 没问题，简单版（当前 `checkin.yml`）直接可用。
- 如果服务端**立即作废**（Keycloak 开启 refresh token rotation 时就是如此）→ **第二次运行会失败**，甚至可能触发会话失效。

**请先做这个实测**：连续点两次「测试运行」。
- 两次都成功 → 保持现状即可，无需改动。
- 第二次失败（或提示令牌失效）→ 换用下面的**自续期增强版**。

### 自续期增强版（把新令牌写回仓库）

用下面的内容替换 `.workflow/checkin.yml` 里的 `steps` 与 `global`，并**额外配置 4 个环境变量** `GT_TOKEN`（有仓库写权限的 Gitee 私人令牌）、`GT_OWNER`（用户名/组织名）、`GT_REPO`（仓库名）、`GT_BRANCH`（分支，如 `master`）：

```yaml
  - step: build@python
    name: run-checkin
    displayName: 复用令牌并签到，回写轮转后的新令牌
    pythonVersion: "3.10"
    commands:
    - mkdir -p "$HOME/.workbuddy"
    - |
      if [ -f .state/rt.json ]; then
        cp .state/rt.json "$HOME/.workbuddy/checkin-rt.json"
      else
        python scripts/rt_auth.py --setup-rt "$WORKBUDDY_RT"
      fi
    - python scripts/rt_auth.py --no-travel --no-notify || true
    - mkdir -p .state
    - cp "$HOME/.workbuddy/checkin-rt.json" .state/rt.json
    - 'git config user.email "checkin-bot@gitee.local"'
    - 'git config user.name "checkin-bot"'
    - 'git add .state/rt.json'
    - 'git commit -m "chore: rotate checkin token [skip ci]" || true'
    - "git push \"https://oauth2:${GT_TOKEN}@gitee.com/${GT_OWNER}/${GT_REPO}.git\" \"HEAD:${GT_BRANCH}\" || true"
```

```yaml
global:
- WORKBUDDY_RT
- GT_TOKEN
- GT_OWNER
- GT_REPO
- GT_BRANCH
```

> 注意：这会把令牌落到**私有仓库**的 `.state/rt.json` 里（每次运行自动更新）。私有仓库 + 令牌本就是账号钥匙，风险可接受；若你不接受，就只能走「自建服务器」路线（容器可持久化磁盘）。
> `[skip ci]` 是为了防止这次提交再次触发流水线造成死循环。

---

## 五、常见问题

| 现象 | 处理 |
|---|---|
| 日志里 `长效令牌刷新失败` / 提示令牌失效 | 令牌已失效：重新在本机导出，更新 Gitee 的 `WORKBUDDY_RT`；若用增强版，同日删除 `.state/rt.json` |
| `getaddrinfo failed` / 连接超时 | Gitee Runner 网络无法访问 `copilot.tencent.com` / `www.codebuddy.cn`，换个 Runner 或机房 |
| 没收到微信推送 | 确认 `SERVERCHAN_SENDKEY` 已配且私密生效；看流水线日志里的 `[push] 推送结果`；再检查微信服务号「方糖」是否被免打扰 |
| 想用别的推送渠道 | 见上文 `WORKBUDDY_NOTIFY_CONFIG` 说明，配一个完整 notify_config.json 即可 |
| 想跑派猫猫旅行 | 把 `--no-travel` 换成 `--travel-auto`（属写操作，注意每日上限保护） |
| 找不到流水线入口 | 需仓库已开通 Gitee Go，且 `.workflow/` 目录在**默认分支**上 |

---

## 六、与「自建服务器」的取舍

| | Gitee Go | 自建 VPS |
|---|---|---|
| 成本 | 免费额度（定时能力可能需付费版） | 需买机器 |
| 令牌轮转 | 容器无状态，需上文增强版回写 | 磁盘持久，天然支持自续期 |
| 可控性 | 一般 | 最高 |
| 维护 | 几乎为零 | 需运维 |

> 若 Gitee 的定时触发在你的版本里不可用，或轮转回写折腾不顺，自建 VPS 反而更省心。
