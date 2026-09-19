# Macro & Credit Monitor

把事先寫下的門檻，變成每週五分鐘能看完的一張表。

這個工具不預測、不評分、不給建議。它只回答一個問題：**我事前設定的觸發條件，今天有沒有被碰到。**

門檻寫在 `config/indicators.yaml`，改動會留下 commit 紀錄——你可以事後檢討自己是在什麼時候、用什麼理由放寬標準的。這是整個專案唯一的核心主張。

完整規格見 [SPEC.md](SPEC.md)。

---

## 架構

無伺服器、無費用。GitHub Actions 每個工作日抓資料、比對門檻、commit 結果；GitHub Pages 讀同一份 JSON。

```
Actions（排程）→ FRED API + data/manual.json → 比對門檻
      → docs/data.json + data/history/ → commit
      → 有觸發就開 GitHub Issue（信箱會收到通知）
Pages → 讀 docs/data.json 的靜態頁
```

瀏覽器不能直接打 FRED（CORS），API key 也不能放前端——所以抓取放在 Actions，前端只讀靜態檔。

---

## 安裝

**1. 建立自己的 repo**

```bash
git clone https://github.com/<you>/macro-monitor.git
cd macro-monitor
```

**2. 申請 FRED API key（免費）**

<https://fredaccount.stlouisfed.org/apikeys>

存到 GitHub → Settings → Secrets and variables → Actions → New repository secret，名稱 `FRED_API_KEY`。

**3. 允許 Actions 寫入**

Settings → Actions → General → Workflow permissions → **Read and write permissions**

**4. 開啟 Pages**

Settings → Pages → Source: Deploy from a branch → Branch `main`、資料夾 `/docs`

**5. 手動跑一次**

Actions → `update` → Run workflow。跑完後打開 Pages 網址。

`docs/data.json` 裡已經放了一份 2026-09-17 前後的種子資料，所以在你設定完 API key 之前，頁面就能正常顯示。第一次成功抓取後會被覆蓋。

---

## 本機測試

```bash
pip install -r requirements.txt
export FRED_API_KEY=xxxx
python scripts/fetch.py
python -m http.server -d docs 8000   # 開 http://localhost:8000
```

沒有 API key 也跑得動：自動指標會標記為無資料，人工指標照常比對。

---

## 每週要做的事

打開頁面，看第一行。沒有紅字就關掉，大約三十秒。

有觸發時，`notify.py` 會開一個 GitHub Issue，你的信箱會收到。

## 每月要做的事

編輯 `data/manual.json`，更新沒有免費 API 的指標。每筆填 `value`、`as_of`、`source`。超過 `stale_after_days` 的會標示為過期——**過期不會消失，只會被標記**，因為「資料多舊」本身就是資訊。

目前尚未填入的有：CLO AAA 利差、MOVE 指數、M1B 年增率、融資餘額、外銷訂單年增率。其中**外銷訂單年增率是台灣組裡最重要的一項**——1988 到 89 年台灣出口成長只剩 1.4% 與 0.9%，股市又漲了 18 個月才見頂。基本面先垮，市場後跌，中間的落差是一年半。

---

## 調整門檻

改 `config/indicators.yaml`，push，下次執行就生效。

```yaml
- id: hy_oas
  watch: 450        # 接近
  trigger: 600      # 觸發
  direction: higher_is_worse
  scale: [200, 1200]   # 只影響畫面軌道，不影響判定
```

`watch` 與 `trigger` 都留空的指標只顯示、不判定。

**建議在市場平靜時改，不要在觸發當下改。** 這正是版本控制存在的意義。

---

## 六組指標

| 組別 | 在看什麼 |
|---|---|
| 信用市場 | HY / CCC / BB / IG OAS 與 CCC−BB 分散度。信用循環從最邊緣的借款人開始裂，指數會把它平均掉 |
| 利率與曲線 | 壓力在短端（貨幣政策）還是長端（財政風險）。看形狀不看水準 |
| 美元與日本 | 美元與殖利率的相關性；日本的美債與 CLO 買盤 |
| AI 建設融資 | 覆蓋倍數、CLO 利差、含 LME 的實質違約率、基金贖回狀態 |
| 台灣 | CPI、實質存款利率、不動產放款占比、M1B、融資餘額、外銷訂單 |
| 黃金與主權需求 | 央行購金、日本對外證券投資 |

兩個最重要的衍生指標不是水準值，是**形狀**：

- `curve_direction` — 2 年期 20 日變動減 10 年期 20 日變動。正值＝短端主導（貨幣政策重新定價）；負值＝長端主導（財政風險溢價）
- `usd_yield_corr` — 美元與 10 年期殖利率日變動的 60 日相關係數。正＝利率升美元升＝正常化；負＝利率升美元跌＝市場在對主權要求風險補償

這兩個用來區分「市場恢復定價功能」與「政府失去定價權」——兩者在單一數字上長得一模一樣。

---

## 已知限制

1. **未經實際 API 回應測試。** 首次執行請看 Actions log。
2. FRED 序列可能改名或停更。抓取失敗時沿用前值並標記過期，不會讓指標消失。
3. `usd_yield_corr` 需要 60 個交易日，初次部署後約三個月才穩定。
4. 月頻資料（CPI、JGB）有發布落差，`as_of` 會誠實反映。
5. 人工指標會過期。這是取捨——與其接一個會壞掉的爬蟲，不如明確標示資料多舊。

---

## 使用原則

指標轉向時**先降低該部位權重，不要一次全部反轉**。單一數據點不構成訊號，要看是否連續兩期以上同方向。

信用指標的領先時間從 4.4 個月（2007）到兩週（2018）到幾乎為零（2020）都有。任何依賴「信用會提前警告我」的計畫，都應該同時準備「這次沒有警告」的情況。

---

## 授權與免責

MIT。

本工具輸出的一切內容僅為公開資料的整理與門檻比對，不構成投資建議、買賣要約，或任何形式的財務、稅務、法律意見。門檻由使用者自行設定，其合理性由使用者自行負責。資料可能延遲、錯誤或中斷。投資有風險，可能損失全部本金。
