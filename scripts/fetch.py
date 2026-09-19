#!/usr/bin/env python3
"""
抓取公開資料、併入人工指標、依 config/indicators.yaml 比對門檻。

輸出:
  docs/data.json                 前端讀這個
  data/history/YYYY-MM-DD.json   每次執行的快照
  data/state.json                上次的狀態，用來偵測狀態轉換

不預測、不評分、不給建議。只比對事先寫下的門檻。
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "indicators.yaml"
MANUAL = ROOT / "data" / "manual.json"
STATE = ROOT / "data" / "state.json"
HISTORY = ROOT / "data" / "history"
OUT = ROOT / "docs" / "data.json"

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
LOOKBACK_DAYS = 400          # 夠算 60 日相關性與年變動
SPARK_POINTS = 40
RETRIES = 3


# ---------------------------------------------------------------- FRED

def fred_series(series_id: str, api_key: str) -> list[tuple[str, float]]:
    """回傳 [(date, value)]，由舊到新。抓不到就回空陣列，不丟例外。"""
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    url = FRED_BASE + "?" + urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
    })
    for attempt in range(RETRIES):
        try:
            with urlopen(url, timeout=30) as r:
                payload = json.load(r)
            out = []
            for obs in payload.get("observations", []):
                raw = obs.get("value", ".")
                if raw in (".", "", None):
                    continue          # FRED 用 "." 表示缺值
                try:
                    out.append((obs["date"], float(raw)))
                except ValueError:
                    continue
            return out
        except (URLError, HTTPError, json.JSONDecodeError, KeyError) as exc:
            wait = 2 ** attempt
            print(f"  ! {series_id} 第 {attempt + 1} 次失敗 ({exc})，{wait}s 後重試",
                  file=sys.stderr)
            time.sleep(wait)
    print(f"  ! {series_id} 放棄", file=sys.stderr)
    return []


# ---------------------------------------------------------------- 小工具

def last(series, n=1):
    return series[-n][1] if len(series) >= n else None


def value_on_or_before(series, target_iso):
    """取 target 當天或之前最近的一筆。"""
    chosen = None
    for d, v in series:
        if d <= target_iso:
            chosen = v
        else:
            break
    return chosen


def nth_back(series, n):
    """往回數 n 個觀測點（不是 n 個日曆日）。"""
    return series[-(n + 1)][1] if len(series) > n else None


def yoy(series):
    """月頻序列的年增率（%）。"""
    if len(series) < 13:
        return None
    now, then = series[-1][1], series[-13][1]
    return (now / then - 1) * 100 if then else None


def pearson(xs, ys):
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else None


def aligned_diffs(a, b, window):
    """兩個日頻序列按日期對齊後的日變動，取最後 window 筆。"""
    da, db = dict(a), dict(b)
    common = sorted(set(da) & set(db))
    if len(common) < window + 2:
        return [], []
    common = common[-(window + 1):]
    xs, ys = [], []
    for prev, cur in zip(common, common[1:]):
        xs.append(da[cur] - da[prev])
        ys.append(db[cur] - db[prev])
    return xs, ys


# ---------------------------------------------------------------- 衍生指標

def compute_derived(formula, fred, manual):
    """回傳 (value, as_of, sparkline)。算不出來就回 (None, None, [])。"""

    if formula == "ccc_bb_spread":
        ccc, bb = fred.get("BAMLH0A3HYC", []), fred.get("BAMLH0A1HYBB", [])
        dc, db = dict(ccc), dict(bb)
        common = sorted(set(dc) & set(db))
        if not common:
            return None, None, []
        pts = [(d, (dc[d] - db[d]) * 100) for d in common]
        return pts[-1][1], pts[-1][0], [round(v, 1) for _, v in pts[-SPARK_POINTS:]]

    if formula == "hy_1m_change":
        hy = fred.get("BAMLH0A0HYM2", [])
        if len(hy) < 22:
            return None, None, []
        pts = [(hy[i][0], (hy[i][1] - hy[i - 21][1]) * 100)
               for i in range(21, len(hy))]
        return pts[-1][1], pts[-1][0], [round(v, 1) for _, v in pts[-SPARK_POINTS:]]

    if formula == "curve_direction":
        s2, s10 = fred.get("DGS2", []), fred.get("DGS10", [])
        if len(s2) < 22 or len(s10) < 22:
            return None, None, []
        d2 = (last(s2) - nth_back(s2, 20)) * 100
        d10 = (last(s10) - nth_back(s10, 20)) * 100
        return d2 - d10, s2[-1][0], []

    if formula == "real_overnight":
        dff, cpi = fred.get("DFF", []), fred.get("CPIAUCSL", [])
        rate, infl = last(dff), yoy(cpi)
        if rate is None or infl is None:
            return None, None, []
        return rate - infl, dff[-1][0], []

    if formula == "usd_yield_corr":
        usd, y10 = fred.get("DTWEXBGS", []), fred.get("DGS10", [])
        xs, ys = aligned_diffs(usd, y10, 60)
        c = pearson(xs, ys)
        if c is None:
            return None, None, []
        return c, usd[-1][0] if usd else None, []

    if formula == "tw_real_deposit":
        dep = manual.get("tw_deposit_rate_1y", {})
        cpi = manual.get("tw_cpi", {})
        if dep.get("value") is None or cpi.get("value") is None:
            return None, None, []
        as_of = min(filter(None, [dep.get("as_of"), cpi.get("as_of")]), default=None)
        return dep["value"] - cpi["value"], as_of, []

    return None, None, []


# ---------------------------------------------------------------- 判定

def classify(value, spec):
    """回傳 ok | watch | triggered | unknown。"""
    if value is None:
        return "unknown"
    trigger, watch = spec.get("trigger"), spec.get("watch")
    if trigger is None and watch is None:
        return "ok"
    worse_high = spec.get("direction", "higher_is_worse") == "higher_is_worse"

    def past(limit):
        if limit is None:
            return False
        return value >= limit if worse_high else value <= limit

    if past(trigger):
        return "triggered"
    if past(watch):
        return "watch"
    return "ok"


def pct_to_trigger(value, spec):
    """0 = 在起點，1 = 已達觸發。純為畫面用。"""
    if value is None:
        return None
    lo, hi = (spec.get("scale") or [None, None])
    trigger = spec.get("trigger")
    if trigger is None or lo is None or hi is None or hi == lo:
        return None
    worse_high = spec.get("direction", "higher_is_worse") == "higher_is_worse"
    start = lo if worse_high else hi
    span = trigger - start
    if span == 0:
        return None
    return max(0.0, min(1.5, (value - start) / span))


def days_old(as_of):
    if not as_of:
        return None
    try:
        return (date.today() - date.fromisoformat(as_of[:10])).days
    except ValueError:
        return None


# ---------------------------------------------------------------- 主流程

def main():
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        print("缺少 FRED_API_KEY，自動指標將全部標記為 unknown。", file=sys.stderr)

    # 上一次的輸出：抓取失敗時沿用前值並標記過期，而不是讓指標消失
    previous = {}
    if OUT.exists():
        try:
            for g in json.loads(OUT.read_text(encoding="utf-8")).get("groups", []):
                for ind in g.get("indicators", []):
                    previous[ind["id"]] = ind
        except (json.JSONDecodeError, KeyError):
            previous = {}

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    manual_doc = json.loads(MANUAL.read_text(encoding="utf-8"))
    manual = manual_doc.get("indicators", {})
    stale_rules = manual_doc.get("_stale_after_days", {})

    # 收集需要的 FRED 序列（含衍生指標依賴的）
    needed = {"DFF", "CPIAUCSL", "DTWEXBGS", "DGS2", "DGS10",
              "BAMLH0A0HYM2", "BAMLH0A3HYC", "BAMLH0A1HYBB"}
    for g in cfg["groups"]:
        for ind in g["indicators"]:
            if ind.get("source") == "fred":
                needed.add(ind["series"])

    fred = {}
    if api_key:
        for sid in sorted(needed):
            print(f"  抓取 {sid}")
            fred[sid] = fred_series(sid, api_key)

    groups_out = []
    summary = {"triggered": 0, "watch": 0, "ok": 0, "stale": 0, "unknown": 0}

    for g in cfg["groups"]:
        inds = []
        for spec in g["indicators"]:
            src = spec.get("source")
            value = as_of = None
            spark, ch1w, ch1m = [], None, None
            stale = False

            if src == "fred":
                series = fred.get(spec["series"], [])
                if series:
                    mult = 100 if spec.get("transform") == "pct_to_bp" else 1
                    value = series[-1][1] * mult
                    as_of = series[-1][0]
                    spark = [round(v * mult, 3) for _, v in series[-SPARK_POINTS:]]
                    p5, p21 = nth_back(series, 5), nth_back(series, 21)
                    if p5 is not None:
                        ch1w = value - p5 * mult
                    if p21 is not None:
                        ch1m = value - p21 * mult
                else:
                    prev = previous.get(spec["id"])
                    if prev and prev.get("value") is not None:
                        value = prev["value"]
                        as_of = prev.get("as_of")
                        spark = prev.get("sparkline", [])
                        stale = True

            elif src == "derived":
                value, as_of, spark = compute_derived(spec["formula"], fred, manual)
                if value is None:
                    prev = previous.get(spec["id"])
                    if prev and prev.get("value") is not None:
                        value = prev["value"]
                        as_of = prev.get("as_of")
                        spark = prev.get("sparkline", [])
                        stale = True

            elif src == "manual":
                entry = manual.get(spec["id"], {})
                value, as_of = entry.get("value"), entry.get("as_of")
                limit = stale_rules.get(spec.get("cadence", "monthly"), 45)
                age = days_old(as_of)
                stale = value is None or age is None or age > limit

            status = classify(value, spec)
            if stale and status != "triggered":
                status = "stale"          # 觸發優先於過期，過期不能掩蓋已觸發

            summary[status] = summary.get(status, 0) + 1

            inds.append({
                "id": spec["id"],
                "name": spec["name"],
                "value": None if value is None else round(value, 3),
                "unit": spec.get("unit", ""),
                "type": spec.get("type", "number"),
                "as_of": as_of,
                "status": status,
                "watch": spec.get("watch"),
                "trigger": spec.get("trigger"),
                "scale": spec.get("scale"),
                "direction": spec.get("direction", "higher_is_worse"),
                "cadence": spec.get("cadence", ""),
                "pct_to_trigger": pct_to_trigger(value, spec),
                "change_1w": None if ch1w is None else round(ch1w, 2),
                "change_1m": None if ch1m is None else round(ch1m, 2),
                "sparkline": spark,
                "note": spec.get("note", ""),
                "source": src,
                "stale": stale,
                "age_days": days_old(as_of),
            })

        groups_out.append({
            "id": g["id"], "name": g["name"],
            "blurb": g.get("blurb", ""), "indicators": inds,
        })

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "groups": groups_out,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    HISTORY.mkdir(parents=True, exist_ok=True)
    (HISTORY / f"{date.today().isoformat()}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # 狀態轉換：給 notify.py 用
    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}

    now_state, transitions = {}, []
    for g in groups_out:
        for ind in g["indicators"]:
            now_state[ind["id"]] = ind["status"]
            before = prev.get(ind["id"])
            if before != ind["status"] and before is not None:
                transitions.append({
                    "id": ind["id"], "name": ind["name"],
                    "from": before, "to": ind["status"],
                    "value": ind["value"], "unit": ind["unit"],
                    "trigger": ind["trigger"], "as_of": ind["as_of"],
                })
    STATE.write_text(json.dumps(now_state, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    (ROOT / "data" / "transitions.json").write_text(
        json.dumps(transitions, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完成：{summary['triggered']} 觸發 / {summary['watch']} 接近 / "
          f"{summary['ok']} 正常 / {summary['stale']} 過期 / {summary['unknown']} 無資料")
    for t in transitions:
        print(f"  變動 {t['name']}: {t['from']} → {t['to']}")


if __name__ == "__main__":
    main()
