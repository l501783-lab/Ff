# 規格書 — Macro & Credit Monitor

版本 0.1 ・ 2026-09-18

---

## 1. 目的

把事先寫下的門檻，變成每週五分鐘能看完的一張表。

這個工具**不預測**任何事。它只回答一個問題：

> 我在事前設定的那些觸發條件，今天有沒有被觸發？

設計上刻意不提供買賣訊號、不做評分、不給結論。門檻由使用者事先寫在設定檔裡，工具只負責比對。

### 1.1 為什麼門檻要事先寫

指標轉向時，人會替自己找理由解釋為什麼「這次不算」。把門檻與檢視頻率固定在版本控制裡，改動會留下 commit 紀錄——你可以事後檢討自己是在什麼時候、用什麼理由放寬標準的。

這是本工具唯一的核心設計主張。

---

## 2. 非目標

明確不做以下事情：

- 不提供投資建議、部位規模或配置比例
- 不做預測、回測績效或最佳化
- 不串接券商、不執行交易
- 不儲存任何個人財務資料
- 不宣稱資料即時。多數指標為日頻，部分為月頻或季頻

---

## 3. 架構

無伺服器、無費用、無需自架環境。

```
  GitHub Actions (排程)
        │
        │  1. 抓取 FRED 等公開 API
        │  2. 併入 data/manual.json（人工維護的指標）
        │  3. 依 config/indicators.yaml 比對門檻
        │  4. 寫入 docs/data.json 與 data/history/YYYY-MM-DD.json
        │  5. 若有觸發 → 開 / 更新 GitHub Issue（信箱會收到通知）
        ▼
  git commit → push
        │
        ▼
  GitHub Pages（讀 docs/data.json 的靜態頁）
```

選這個架構的三個理由：

| 問題 | 解法 |
|---|---|
| 瀏覽器直接呼叫 FRED 會被 CORS 擋 | 由 Actions 在伺服器端抓，前端只讀靜態 JSON |
| API key 不能寫在前端 | 放 GitHub Secrets |
| 沒有推播管道 | GitHub Issue 通知即為信箱通知 |

### 3.1 排程

| 工作 | 頻率 | Cron (UTC) |
|---|---|---|
| 抓取與評估 | 每個工作日 | `0 22 * * 1-5` |
| 每週摘要 Issue | 週一 | `0 23 * * 1` |

FRED 多數序列在美東時間下午更新，故設在 UTC 22:00（台北隔日 06:00）。

---

## 4. 資料來源

### 4.1 自動（FRED API）

需要免費 API key：<https://fredaccount.stlouisfed.org/apikeys>

| 代號 | 內容 | 頻率 |
|---|---|---|
| `BAMLH0A0HYM2` | 高收益債 OAS | 日 |
| `BAMLH0A3HYC` | CCC 級 OAS | 日 |
| `BAMLH0A1HYBB` | BB 級 OAS | 日 |
| `BAMLC0A0CM` | 投資級 OAS | 日 |
| `DGS2` `DGS10` `DGS30` | 公債殖利率 | 日 |
| `DFII10` | 10 年期 TIPS 實質殖利率 | 日 |
| `T10YIE` | 10 年期損益兩平通膨率 | 日 |
| `DFF` | 有效聯邦資金利率 | 日 |
| `DTWEXBGS` | 廣義美元指數 | 日 |
| `DEXJPUS` | 美元兌日圓 | 日 |
| `CPIAUCSL` `CPILFESL` | CPI / 核心 CPI | 月 |
| `IRLTLT01JPM156N` | 日本 10 年期公債 | 月 |

### 4.2 人工維護（`data/manual.json`）

沒有穩定免費 API 的指標。每筆需填 `value`、`as_of`、`source`。

工具會依 `stale_after_days` 標示過期，過期不會消失，只會標記為 `stale`。

| 指標 | 來源 | 建議更新 |
|---|---|---|
| 台灣 CPI 年增率 | 主計總處 | 每月 |
| 央行重貼現率 | 中央銀行 | 每季 |
| 一年期定存牌告利率 | 台銀 | 每季 |
| 銀行不動產放款占總放款比 | 央行理監事會新聞稿 | 每季 |
| M1B 年增率 | 央行 | 每月 |
| 融資餘額 | 證交所 | 每月 |
| 外銷訂單年增率 | 經濟部 | 每月 |
| MOVE 指數 | 公開行情 | 每週 |
| 超大規模業者債券覆蓋倍數 | 券商發行報告 | 每季 |
| CLO AAA 利差 | 券商研究 | 每月 |
| 含 LME 之實質違約率 | 惠譽／穆迪／標普 | 每季 |
| 信用型基金贖回狀態 | 新聞 | 事件驅動 |
| 央行季度淨購金量 | 世界黃金協會 | 每季 |
| 日本對外證券投資淨額 | 日本財務省 | 每週 |

---

## 5. 指標與門檻

完整定義見 `config/indicators.yaml`。此處說明狀態機與衍生指標。

### 5.1 三種狀態

| 狀態 | 意義 |
|---|---|
| `ok` | 未達觀察值 |
| `watch` | 已過觀察值，未過觸發值 |
| `triggered` | 已過觸發值 |
| `stale` | 資料過期，狀態未知 |

### 5.2 衍生指標

| 名稱 | 計算 | 說明 |
|---|---|---|
| `ccc_bb_spread` | CCC OAS − BB OAS | 分散度。指數會把尾部壓力平均掉 |
| `hy_1m_change` | HY OAS 今日 − 21 交易日前 | 2007 年的訊號是六週 187bp，看的是速度不是水準 |
| `real_overnight` | DFF − CPI 年增率 | 判斷是否進入負實質利率 |
| `curve_direction` | (DGS2 20 日變動) − (DGS10 20 日變動) | 正值＝短端主導（貨幣政策重新定價）；負值＝長端主導（財政風險溢價） |
| `usd_yield_corr` | DTWEXBGS 與 DGS10 日變動的 60 日相關係數 | 正＝正常化；負＝市場對主權要求風險補償 |
| `tw_real_deposit` | 一年期定存 − 台灣 CPI 年增率 | 台灣儲蓄者的實質報酬 |

`curve_direction` 與 `usd_yield_corr` 是本工具最重要的兩個衍生指標。它們不是水準值，而是**形狀**——用來區分「市場恢復定價功能」與「政府失去定價權」，兩者在單一數字上長得一模一樣。

### 5.3 門檻格式

```yaml
- id: hy_oas
  name: 高收益債 OAS
  group: credit
  source: fred
  series: BAMLH0A0HYM2
  unit: bp
  direction: higher_is_worse   # or lower_is_worse
  scale: [200, 1200]           # 顯示軌道的兩端
  watch: 450
  trigger: 600
  cadence: weekly
  note: 300 以下為自滿；600 以上為壓力；800 以上歷史上伴隨衰退
```

`direction` 決定比較方向。`scale` 只影響畫面上的軌道長度，不影響判定。

---

## 6. 輸出

### 6.1 `docs/data.json`

```json
{
  "generated_at": "2026-09-18T22:00:11Z",
  "summary": { "triggered": 2, "watch": 3, "ok": 19, "stale": 1 },
  "groups": [
    {
      "id": "credit",
      "name": "信用市場",
      "indicators": [
        {
          "id": "hy_oas",
          "name": "高收益債 OAS",
          "value": 275.0,
          "unit": "bp",
          "as_of": "2026-09-17",
          "status": "ok",
          "watch": 450, "trigger": 600,
          "scale": [200, 1200],
          "pct_to_trigger": 0.54,
          "change_1w": -3.0,
          "change_1m": 8.0,
          "sparkline": [271, 274, 269, 275],
          "note": "...",
          "stale": false
        }
      ]
    }
  ]
}
```

### 6.2 歷史快照

`data/history/YYYY-MM-DD.json` 每次執行寫一份，內容同上。由於進版控管，可用 `git log` 回溯任何一天的判定，也能看出門檻何時被改過。

### 6.3 觸發通知

任一指標由非 `triggered` 轉為 `triggered` 時，開一個 GitHub Issue：

```
標題：[觸發] 高收益債 OAS 突破 600bp
標籤：triggered
內文：指標、當前值、門檻、前值、資料日期、設定檔連結
```

已存在的未關閉 Issue 不重複開，改為留言更新。狀態回到 `ok` 時自動關閉並留言。

---

## 7. 前端

單頁靜態，無框架、無建置步驟。`docs/index.html` + `app.js` + `style.css`，讀同目錄的 `data.json`。

### 7.1 核心元件：門檻軌道

每個指標畫成一條軌道，標出觀察值與觸發值的位置，游標是當前值。

```
高收益債 OAS                              275 bp
├────●───────────┊──────────┊─────────────┤
200              450        600        1200
                觀察        觸發
```

這是本工具的主要視覺主張：**重要的不是數值，是距離門檻還有多遠**。

### 7.2 狀態摘要

頁首以一行純文字呈現：`2 項觸發 ・ 3 項接近 ・ 19 項正常 ・ 1 項資料過期`。不使用儀表板式的大數字卡片。

### 7.3 顏色

介面其餘部分全為單色。顏色只用於狀態，不用於裝飾——看到顏色就代表有事。

---

## 8. 安裝

```bash
# 1. Fork 或 clone
git clone https://github.com/<you>/macro-monitor.git
cd macro-monitor

# 2. 設定 FRED API key
#    GitHub → Settings → Secrets and variables → Actions → New repository secret
#    Name: FRED_API_KEY

# 3. 開啟 Pages
#    GitHub → Settings → Pages → Source: Deploy from a branch
#    Branch: main / docs

# 4. 允許 Actions 寫入
#    Settings → Actions → General → Workflow permissions → Read and write

# 5. 本機測試
pip install -r requirements.txt
export FRED_API_KEY=xxxx
python scripts/fetch.py
python -m http.server -d docs 8000
```

---

## 9. 已知限制

1. **FRED 序列會改名或停止更新。** 抓取失敗時保留前值並標記 `stale`，不會讓整份資料消失。
2. **人工指標會過期。** 這是設計上的取捨——與其接一個會壞掉的爬蟲，不如明確標示資料多舊。
3. **`usd_yield_corr` 需要 60 個交易日才有意義**，初次執行後約三個月才穩定。
4. **月頻資料（CPI、JGB）有發布落差**，`as_of` 會誠實反映。
5. **本工具未經實際 API 回應測試。** 首次執行請檢查 Actions log。

---

## 10. 授權與免責

MIT 授權。

本工具輸出的一切內容僅為公開資料的整理與門檻比對，不構成投資建議、買賣要約或任何形式的財務、稅務或法律意見。門檻由使用者自行設定，其合理性由使用者自行負責。資料可能延遲、錯誤或中斷。投資有風險，可能損失全部本金。
