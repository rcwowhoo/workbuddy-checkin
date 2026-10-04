#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多账号签到结果汇总推送。

把循环签到落盘的多个结果 JSON（rt_auth.py 的输出结构）拼成一条消息，
经 push_message 一次发出——多账号只占 Server酱一条额度，微信一眼看全。

用法：
  python push_summary.py .results/*.json          # 汇总并推送
  python push_summary.py .results/*.json --dry-run  # 只打印不发送

账号名取结果文件的主名（如 1.json -> 账号1）。退出码：
  0 全部签到成功且推送成功；1 有账号失败或推送失败；2 参数错误。
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import push_message  # noqa: E402  同目录复用多渠道推送


def _load_result(path):
    with open(path, "r", encoding="utf-8") as f:
        res = json.load(f)
    if not isinstance(res, dict):
        raise ValueError("结果不是 JSON 对象")
    return res


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        sys.stderr.write("用法: python push_summary.py <结果.json> [...] [--dry-run]\n")
        return 2

    lines = []
    any_fail = False
    for path in sorted(files):
        name = os.path.splitext(os.path.basename(path))[0]
        label = ("账号%s" % name) if name.isdigit() else (name or path)
        try:
            res = _load_result(path)
            ok = res.get("status") == "ok"
            icon = "✅" if ok else "❌"
            msg = res.get("msg") or res.get("action") or "未知结果"
        except Exception as exc:  # noqa: BLE001
            ok, icon, msg = False, "❌", "结果读取失败：%s" % exc
        lines.append("**%s** %s %s" % (label, icon, msg))
        if not ok:
            any_fail = True

    title = "WorkBuddy 签到 · %s" % time.strftime("%Y-%m-%d")
    content = "\n\n".join(lines)
    print("==== 汇总 ====\n%s\n\n%s" % (title, content))
    if dry_run:
        return 1 if any_fail else 0

    try:
        result = push_message.send_message(title, content, content_type="markdown")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("汇总推送异常：%s\n" % exc)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    push_ok = bool(result.get("ok"))
    return 0 if (push_ok and not any_fail) else 1


if __name__ == "__main__":
    sys.exit(main())
