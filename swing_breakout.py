# -*- coding: utf-8 -*-
"""
swing_breakout.py
短波段突破掃描（收盤後執行）+ LINE 官方帳號廣播推播

訊號：
- 週突破：本週「第一次」收盤站上上週K棒最高價
- 月突破：本月「第一次」收盤站上上月K棒最高價
停損：突破當日K棒最低價
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone, date

import pandas as pd
import requests
import urllib3
import yfinance as yf

# ===== 篩選設定 =====
MIN_VOL_LOTS = 1000      # 當日成交量下限（張）
MIN_PRICE = 10           # 股價下限（元）
ONLY_FIRST_DAY = False   # True = 只認週一 / 月初第一個交易日的突破
MAX_PUSH = 40            # 最多推播幾檔
EXCLUDE_ETF = True       # 排除 0 開頭的 ETF
CHUNK = 100              # yfinance 每批下載檔數
OUTPUT_JSON = "data/swing_breakout.json"
# ====================

LINE_TOKEN = os.getenv("LINE_TOKEN")
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

TPE = timezone(timedelta(hours=8))
WEEKDAY = "一二三四五六日"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------- 工具 ----------
def fmt(p):
    s = f"{p:,.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def http_get_json(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.SSLError:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(url, headers=headers, timeout=30, verify=False)
    r.raise_for_status()
    return r.json()


def pick(row, keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k]).strip()
    return ""


def to_num(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_date(s):
    s = s.strip()
    if len(s) == 7 and s.isdigit():
        return date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:]))
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return None


def valid_code(code):
    if not (len(code) == 4 and code.isdigit()):
        return False
    if EXCLUDE_ETF and code.startswith("0"):
        return False
    return True


def week_key(d):
    return d - timedelta(days=d.weekday())


def month_key(d):
    return (d.year, d.month)


# ---------- 1. 全市場清單 ----------
def load_universe():
    sources = [
        (TWSE_URL, ".TW", "上市", {
            "code": ["Code", "證券代號"], "name": ["Name", "證券名稱"],
            "vol": ["TradeVolume", "成交股數"], "high": ["HighestPrice", "最高價"],
            "low": ["LowestPrice", "最低價"], "close": ["ClosingPrice", "收盤價"],
            "date": ["Date", "日期"],
        }),
        (TPEX_URL, ".TWO", "上櫃", {
            "code": ["SecuritiesCompanyCode", "Code"], "name": ["CompanyName", "Name"],
            "vol": ["TradingShares", "TradeVolume"], "high": ["High", "HighestPrice"],
            "low": ["Low", "LowestPrice"], "close": ["Close", "ClosingPrice"],
            "date": ["Date"],
        }),
    ]
    universe, seen = [], set()
    for url, suffix, label, keys in sources:
        try:
            rows = http_get_json(url)
        except Exception as e:
            print(f"❌ {label}清單抓取失敗：{e}")
            continue
        n = 0
        for row in rows:
            code = pick(row, keys["code"])
            if not valid_code(code) or code in seen:
                continue
            vol = to_num(pick(row, keys["vol"]))
            close = to_num(pick(row, keys["close"]))
            if vol is None or close is None or close <= 0:
                continue
            seen.add(code)
            universe.append({
                "code": code,
                "name": pick(row, keys["name"]) or code,
                "suffix": suffix,
                "vol_lots": vol / 1000,
                "close": close,
                "high": to_num(pick(row, keys["high"])),
                "low": to_num(pick(row, keys["low"])),
                "date": parse_date(pick(row, keys["date"])),
            })
            n += 1
        print(f"{label}：{n} 檔")
    return universe


# ---------- 2. 歷史日K ----------
def download_history(cands):
    tickers = [c["code"] + c["suffix"] for c in cands]
    result = {}
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        print(f"下載歷史日K {i + 1}-{i + len(chunk)} / {len(tickers)}")
        try:
            data = yf.download(chunk, period="3mo", interval="1d", group_by="ticker",
                               auto_adjust=False, threads=True, progress=False)
        except Exception as e:
            print(f"  下載失敗：{e}")
            continue
        if data is None or data.empty:
            continue
        for t in chunk:
            try:
                sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            except KeyError:
                continue
            if not all(col in sub for col in ("High", "Low", "Close")):
                continue
            sub = sub[["High", "Low", "Close"]].dropna()
            if sub.empty:
                continue
            idx = pd.to_datetime(sub.index)
            if idx.tz is not None:
                idx = idx.tz_convert("Asia/Taipei").tz_localize(None)
            sub = sub.copy()
            sub.index = idx.normalize()
            result[t] = sub
        time.sleep(1)
    return result


def merge_latest(hist, c):
    """以交易所當日資料為準：覆蓋或補上最新一天"""
    d = c["date"]
    if d is None or c["high"] is None or c["low"] is None:
        return hist
    ts = pd.Timestamp(d)
    hist = hist[hist.index != ts]
    row = pd.DataFrame({"High": [c["high"]], "Low": [c["low"]], "Close": [c["close"]]}, index=[ts])
    return pd.concat([hist, row]).sort_index()


# ---------- 3. 突破判斷 ----------
def analyze(c, hist, market_date):
    hist = hist[hist.index.date <= market_date].round(2)   # 消除浮點誤差
    if len(hist) < 2 or hist.index[-1].date() != market_date:
        return None

    today = hist.iloc[-1]
    prev_close = float(hist.iloc[-2]["Close"])
    close = float(today["Close"])
    dates = list(hist.index.date)

    signals = []
    for kind, key_func in (("月", month_key), ("週", week_key)):
        cur = key_func(market_date)
        keys = [key_func(d) for d in dates]

        before_keys = [k for k in keys if k < cur]
        if not before_keys:
            continue
        last_key = before_keys[-1]
        level = float(hist[[k == last_key for k in keys]]["High"].max())

        cur_bars = hist[[k == cur for k in keys]]
        if ONLY_FIRST_DAY and len(cur_bars) != 1:
            continue
        earlier = cur_bars.iloc[:-1]
        if close > level and not (earlier["Close"] > level).any():
            signals.append({"kind": kind, "level": round(level, 2)})

    if not signals:
        return None

    low = float(today["Low"])
    return {
        "code": c["code"],
        "name": c["name"],
        "market": "上市" if c["suffix"] == ".TW" else "上櫃",
        "close": round(close, 2),
        "chg_pct": round((close / prev_close - 1) * 100, 2),
        "vol_lots": round(c["vol_lots"]),
        "signals": signals,
        "stop": round(low, 2),
        "risk_pct": round((close - low) / close * 100, 2),
    }


# ---------- 4. 推播 ----------
def build_messages(matches, market_date, scanned):
    title = f"📈 波段突破 {market_date:%Y/%m/%d}({WEEKDAY[market_date.weekday()]}) 收盤"
    n_month = sum(1 for s in matches if any(g["kind"] == "月" for g in s["signals"]))
    n_week = sum(1 for s in matches if any(g["kind"] == "週" for g in s["signals"]))
    shown = matches[:MAX_PUSH]
    rule = "週一/月初當天突破" if ONLY_FIRST_DAY else "當週/當月首次收盤突破"
    header = (
        f"{title}\n"
        f"條件：量≥{MIN_VOL_LOTS:,}張、價≥{MIN_PRICE}、{rule}\n"
        f"掃描 {scanned} 檔 → 月突破 {n_month}｜週突破 {n_week}，顯示前 {len(shown)} 檔\n"
        f"停損：突破日K棒最低價\n"
    )

    blocks = []
    for s in shown:
        tags = "".join(f"[{g['kind']}]" for g in s["signals"])
        levels = "、".join(f"{g['kind']}高 {fmt(g['level'])}" for g in s["signals"])
        blocks.append(
            f"\n{tags} {s['code']} {s['name']}  收 {fmt(s['close'])} ({s['chg_pct']:+.1f}%)｜量 {s['vol_lots']:,}張\n"
            f"  突破 {levels}\n"
            f"  停損 {fmt(s['stop'])} (-{s['risk_pct']:.1f}%)"
        )

    if not shown:
        blocks.append("\n今天沒有符合條件的標的")

    msgs, cur = [], header
    for b in blocks:
        if len(cur) + len(b) > 3500:
            msgs.append(cur)
            cur = f"{title}（續）\n"
        cur += b + "\n"
    msgs.append(cur)
    return msgs


def send_line_broadcast(msgs):
    """廣播給所有加入官方帳號好友的人；一次最多 5 則，同一次呼叫只算 1 則額度"""
    msgs = msgs[:5]
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"messages": [{"type": "text", "text": m[:5000]} for m in msgs]}
    try:
        r = requests.post(LINE_BROADCAST_URL, headers=headers, json=body, timeout=15)
        if r.ok:
            print("✅ 已推播到 LINE")
        else:
            print(f"LINE 發送失敗：{r.status_code} {r.text}")
    except Exception as e:
        print(f"LINE 發送失敗：{e}")


# ---------- 主程式 ----------
def main():
    t0 = time.time()
    now = datetime.now(TPE)

    universe = load_universe()
    if not universe:
        print("❌ 取不到全市場清單，結束")
        return

    cands = [c for c in universe if c["vol_lots"] >= MIN_VOL_LOTS and c["close"] >= MIN_PRICE]
    print(f"全市場 {len(universe)} 檔 → 量價過濾後 {len(cands)} 檔")

    histories = download_history(cands)

    merged = {}
    for c in cands:
        hist = histories.get(c["code"] + c["suffix"])
        if hist is not None:
            merged[c["code"]] = merge_latest(hist, c)

    exch_dates = [c["date"] for c in cands if c["date"] is not None]
    if exch_dates:
        market_date = max(exch_dates)
    elif merged:
        market_date = max(h.index[-1].date() for h in merged.values())
    else:
        print("❌ 沒有任何歷史資料，結束")
        return
    print(f"掃描交易日：{market_date}")

    # GitHub Actions 自動執行時：資料不是今天（假日或交易所尚未更新）就不推播
    if os.getenv("GITHUB_ACTIONS") == "true" and market_date != now.date():
        print(f"⏸ 最新資料為 {market_date}，不是今天 {now.date()}，本次不推播")
        return

    matches, missing = [], []
    for c in cands:
        hist = merged.get(c["code"])
        if hist is None:
            missing.append(c["code"])
            continue
        s = analyze(c, hist, market_date)
        if s:
            matches.append(s)

    def sort_key(s):
        kinds = {g["kind"] for g in s["signals"]}
        score = (2 if "月" in kinds else 0) + (1 if "週" in kinds else 0)
        return (-score, -s["vol_lots"])

    matches.sort(key=sort_key)
    print(f"符合條件 {len(matches)} 檔；無歷史資料 {len(missing)} 檔")

    out_dir = os.path.dirname(OUTPUT_JSON)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": now.strftime("%Y-%m-%d %H:%M"),
            "market_date": market_date.strftime("%Y-%m-%d"),
            "settings": {
                "min_vol_lots": MIN_VOL_LOTS, "min_price": MIN_PRICE,
                "only_first_day": ONLY_FIRST_DAY,
            },
            "scanned": len(cands),
            "stocks": matches,
            "missing": missing,
        }, f, ensure_ascii=False, indent=2)

    msgs = build_messages(matches, market_date, len(cands))
    for m in msgs:
        print(m)

    if LINE_TOKEN:
        send_line_broadcast(msgs)
    else:
        print("未設定 LINE_TOKEN，只輸出到畫面")

    print(f"耗時 {time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()