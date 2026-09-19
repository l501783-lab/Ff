#!/usr/bin/env python3
"""
狀態轉換 → GitHub Issue。Issue 通知就是信箱通知，不需要額外服務。

規則:
  轉為 triggered   → 開 Issue（同名未關閉的改為留言）
  離開 triggered   → 留言並關閉
  其他轉換         → 不開 Issue，只寫進 Actions log
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
TRANSITIONS = ROOT / "data" / "transitions.json"
API = "https://api.github.com"
LABEL = "triggered"


def gh(method, path, token, body=None):
    req = Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "macro-monitor",
        },
    )
    try:
        with urlopen(req, timeout=30) as r:
            return json.load(r)
    except HTTPError as exc:
        print(f"  ! GitHub API {method} {path} -> {exc.code}: {exc.read()[:200]}",
              file=sys.stderr)
        return None


def find_open_issue(repo, token, title):
    q = quote(f'repo:{repo} is:issue is:open in:title "{title}"')
    res = gh("GET", f"/search/issues?q={q}", token)
    if not res:
        return None
    for item in res.get("items", []):
        if item.get("title") == title:
            return item
    return None


def fmt(t):
    val = "—" if t["value"] is None else f"{t['value']} {t['unit']}".strip()
    trg = "—" if t["trigger"] is None else t["trigger"]
    return (
        f"| 項目 | 內容 |\n| --- | --- |\n"
        f"| 指標 | {t['name']} (`{t['id']}`) |\n"
        f"| 當前值 | **{val}** |\n"
        f"| 觸發門檻 | {trg} |\n"
        f"| 狀態變化 | `{t['from']}` → `{t['to']}` |\n"
        f"| 資料日期 | {t['as_of'] or '—'} |\n\n"
        f"門檻定義見 [`config/indicators.yaml`](../blob/main/config/indicators.yaml)。\n\n"
        f"> 這是事先寫下的門檻被觸碰的通知，不是買賣訊號。"
        f"單一數據點不構成訊號——請確認是否連續兩期以上同方向。\n"
    )


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY，略過通知。")
        return
    if not TRANSITIONS.exists():
        print("沒有 transitions.json，略過。")
        return

    transitions = json.loads(TRANSITIONS.read_text(encoding="utf-8"))
    if not transitions:
        print("本次無狀態變動。")
        return

    for t in transitions:
        title = f"[觸發] {t['name']}"
        existing = find_open_issue(repo, token, title)

        if t["to"] == "triggered":
            if existing:
                gh("POST", f"/repos/{repo}/issues/{existing['number']}/comments",
                   token, {"body": "狀態再次確認為觸發。\n\n" + fmt(t)})
                print(f"  留言更新 #{existing['number']} {t['name']}")
            else:
                created = gh("POST", f"/repos/{repo}/issues", token, {
                    "title": title, "body": fmt(t), "labels": [LABEL],
                })
                if created:
                    print(f"  開立 #{created['number']} {t['name']}")

        elif t["from"] == "triggered" and existing:
            gh("POST", f"/repos/{repo}/issues/{existing['number']}/comments",
               token, {"body": f"已回到 `{t['to']}`，關閉。\n\n" + fmt(t)})
            gh("PATCH", f"/repos/{repo}/issues/{existing['number']}",
               token, {"state": "closed"})
            print(f"  關閉 #{existing['number']} {t['name']}")

        else:
            print(f"  {t['name']}: {t['from']} → {t['to']}（不開 Issue）")


if __name__ == "__main__":
    main()
