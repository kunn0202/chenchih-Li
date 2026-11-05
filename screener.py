import pandas as pd
import numpy as np
import os
import glob
import json
import time
import requests
import urllib3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "stock_data")
INST_DIR = os.path.join(BASE_DIR, "inst_data")
TDCC_DIR = os.path.join(BASE_DIR, "tdcc_data")
REV_DIR = os.path.join(BASE_DIR, "revenue_data")
FIN_DIR = os.path.join(BASE_DIR, "fin_data")

# ===== 基本面設定 =====
YIELD_MIN = 5.0          # 高殖利率門檻（%）
# ======================

files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
print("讀取檔案數:", len(files))

info = pd.read_csv(os.path.join(BASE_DIR, "stock_list.csv"), dtype={"stock_id": str})
names = info.set_index("stock_id")["stock_name"].to_dict()
inds = info.set_index("stock_id")["industry_category"].to_dict()

def get_inst_flags(sid):
    """回傳 (外資買超, 投信買超)"""
    path = os.path.join(INST_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False, False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, False
    if df.empty or "date" not in df.columns:
        return False, False
    last_date = df["date"].max()
    today = df[df["date"] == last_date]

    foreign = today[today["name"] == "Foreign_Investor"]
    trust = today[today["name"] == "Investment_Trust"]

    f_buy = bool(len(foreign) and (foreign["buy"].sum() - foreign["sell"].sum()) > 0)
    t_buy = bool(len(trust) and (trust["buy"].sum() - trust["sell"].sum()) > 0)
    return f_buy, t_buy

def get_big_up(sid):
    """大戶(400張以上)持股比例是否連續兩週增加

    需要最近三筆週資料：最新 > 前一週 > 前兩週 才成立。
    資料不足三筆一律回 False。
    """
    path = os.path.join(TDCC_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False
    if df.empty or "big" not in df.columns or "date" not in df.columns:
        return False
    df = df.sort_values("date")
    big = pd.to_numeric(df["big"], errors="coerce").dropna()
    if len(big) < 3:
        return False
    w0, w1, w2 = big.iloc[-1], big.iloc[-2], big.iloc[-3]
    return bool(w0 > w1 > w2)

def http_json(url, retries=3):
    headers = {"User-Agent": "Mozilla/5.0"}
    for att in range(1, retries + 1):
        try:
            try:
                r = requests.get(url, headers=headers, timeout=30)
            except requests.exceptions.SSLError:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, headers=headers, timeout=30, verify=False)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  連線失敗（{att}/{retries}）{url}：{e}")
            if att < retries:
                time.sleep(5 * att)
    return []


def pick(row, keys, contains=None):
    for k in keys:
        if k in row and str(row[k]).strip() not in ("", "-"):
            return str(row[k]).strip()
    if contains:
        for k, v in row.items():
            if any(c in k for c in contains) and str(v).strip() not in ("", "-"):
                return str(v).strip()
    return ""


def load_yield():
    """全市場殖利率 {股票代號: 殖利率%}，上市 + 上櫃"""
    out = {}
    sources = [
        ("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
         ["Code", "證券代號"], ["DividendYield", "殖利率(%)"], "上市"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
         ["SecuritiesCompanyCode", "Code"], ["YieldRatio", "DividendYield"], "上櫃"),
    ]
    for url, code_keys, y_keys, label in sources:
        rows = http_json(url)
        n = 0
        for row in rows or []:
            code = pick(row, code_keys)
            y = pick(row, y_keys, contains=["Yield", "殖利率"])
            try:
                out[code] = float(y.replace(",", ""))
                n += 1
            except ValueError:
                continue
        print(f"殖利率 {label}：{n} 檔")
    return out


def get_revenue_flags(sid):
    """回傳 (營收創歷史新高, 營收創同期新高)

    歷史新高：最新月營收 > 資料期間內所有月份（至少要有 12 個月資料）
    同期新高：最新月營收 > 往年同月份的營收（至少要有 1 年前同月資料）
    """
    path = os.path.join(REV_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False, False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, False
    if df.empty or "revenue" not in df.columns:
        return False, False
    df = df.dropna(subset=["revenue", "revenue_year", "revenue_month"])
    df = df.sort_values(["revenue_year", "revenue_month"]).drop_duplicates(
        subset=["revenue_year", "revenue_month"], keep="last")
    if len(df) < 13:
        return False, False
    latest = df.iloc[-1]
    prev = df.iloc[:-1]
    rev = float(latest["revenue"])
    if rev <= 0:
        return False, False
    ath = bool(rev > prev["revenue"].max())
    same = prev[prev["revenue_month"] == latest["revenue_month"]]
    same_high = bool(len(same) > 0 and rev > same["revenue"].max())
    return ath, same_high


def get_fin_flags(sid):
    """回傳 (毛利率年增, 營益率年增, 公司未虧損)

    毛利率 / 營益率：最新一季 vs 去年同一季
    未虧損：最新一季 EPS > 0 且近四季 EPS 合計 > 0
    """
    path = os.path.join(FIN_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False, False, False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, False, False
    if df.empty or "type" not in df.columns:
        return False, False, False
    df["date"] = pd.to_datetime(df["date"])
    piv = df.pivot_table(index="date", columns="type", values="value", aggfunc="last").sort_index()
    if piv.empty:
        return False, False, False

    def margin(row, col):
        rev, v = row.get("Revenue"), row.get(col)
        if pd.notna(rev) and pd.notna(v) and rev > 0:
            return v / rev
        return None

    latest_dt = piv.index[-1]
    latest = piv.iloc[-1]
    ly_dt = latest_dt - pd.DateOffset(years=1)
    gm_up = om_up = False
    if ly_dt in piv.index:
        ly = piv.loc[ly_dt]
        g0, g1 = margin(latest, "GrossProfit"), margin(ly, "GrossProfit")
        o0, o1 = margin(latest, "OperatingIncome"), margin(ly, "OperatingIncome")
        gm_up = bool(g0 is not None and g1 is not None and g0 > g1)
        om_up = bool(o0 is not None and o1 is not None and o0 > o1)

    profit = False
    if "EPS" in piv.columns:
        eps = piv["EPS"].dropna()
        if len(eps) >= 4:
            profit = bool(eps.iloc[-1] > 0 and eps.tail(4).sum() > 0)
    return gm_up, om_up, profit


YIELDS = load_yield()

results = []

for f in files:
    sid = os.path.basename(f).replace(".csv", "")
    df = pd.read_csv(f)
    if len(df) < 210:
        continue

    df = df.sort_values("date").reset_index(drop=True)
    df = df[df["close"] > 0].reset_index(drop=True)
    if len(df) < 210:
        continue

    close = df["close"]
    last = close.iloc[-1]

    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma24 = close.rolling(24).mean()
    ma72 = close.rolling(72).mean()
    ma200 = close.rolling(200).mean()

    c3 = ma5.iloc[-1] > ma10.iloc[-1] > ma24.iloc[-1]
    c4 = ma24.iloc[-1] > ma72.iloc[-1] > ma200.iloc[-1]

    # 扣抵值 = 均線視窗內最舊的那根收盤（明天會被擠出均線的那根）
    # MA5 視窗是 iloc[-5]~iloc[-1]，所以扣抵值是 iloc[-5]，與圖表的扣抵三角形一致
    d5 = last > close.iloc[-5]
    d10 = last > close.iloc[-10]
    d24 = last > close.iloc[-24]
    d72 = last > close.iloc[-72]

    cross = bool(ma5.iloc[-2] <= ma24.iloc[-2] and ma5.iloc[-1] > ma24.iloc[-1])

    df["date"] = pd.to_datetime(df["date"])
    last_date = df["date"].iloc[-1]

    prev_month = (last_date.replace(day=1) - pd.Timedelta(days=1)).to_period("M")
    pm = df[df["date"].dt.to_period("M") == prev_month]
    pm_high = pm["max"].max() if len(pm) else np.nan
    c2 = bool(len(pm) > 0 and last >= pm_high * 0.95)
    over_month = bool(len(pm) > 0 and last > pm_high)

    this_monday = last_date - pd.Timedelta(days=last_date.weekday())
    prev_monday = this_monday - pd.Timedelta(days=7)
    prev_friday = this_monday - pd.Timedelta(days=3)
    pw = df[(df["date"] >= prev_monday) & (df["date"] <= prev_friday)]
    pw_high = pw["max"].max() if len(pw) else np.nan
    over_week = bool(len(pw) > 0 and last > pw_high)

    vol20 = df["Trading_Volume"].tail(20).mean() / 1000

    def ret(n1, n2):
        if len(close) <= n2:
            return np.nan
        a, b = close.iloc[-n2 - 1], close.iloc[-n1 - 1]
        return (b - a) / a if a > 0 else np.nan

    rs_raw = (0.4 * ret(0, 63) + 0.2 * ret(63, 126)
              + 0.2 * ret(126, 189) + 0.2 * ret(189, 252))

    foreign_buy, trust_buy = get_inst_flags(sid)
    big_up = get_big_up(sid)
    rev_ath, rev_same_high = get_revenue_flags(sid)
    gm_up, om_up, profit = get_fin_flags(sid)
    dy = YIELDS.get(sid)

    results.append({
        "stock_id": sid,
        "stock_name": names.get(sid, ""),
        "industry": inds.get(sid, ""),
        "close": round(float(last), 2),
        "vol20": round(float(vol20), 1),
        "rs_raw": rs_raw,
        "c2": c2,
        "c3": bool(c3),
        "c4": bool(c4),
        "d5": bool(d5),
        "d10": bool(d10),
        "d24": bool(d24),
        "d72": bool(d72),
        "over_month": over_month,
        "over_week": over_week,
        "cross": cross,
        "foreign_buy": foreign_buy,
        "trust_buy": trust_buy,
        "big_up": big_up,
        "rev_ath": rev_ath,
        "rev_same_high": rev_same_high,
        "gm_up": gm_up,
        "om_up": om_up,
        "high_yield": bool(dy is not None and dy >= YIELD_MIN),
        "profit": profit,
        "dy": dy,
    })

res = pd.DataFrame(results).dropna(subset=["rs_raw"])
print("有效檔數:", len(res))

res["rs_score"] = (res["rs_raw"].rank(pct=True) * 100).round(1)
res["c1"] = res["rs_score"] > 90
res = res.drop(columns=["rs_raw"]).sort_values("rs_score", ascending=False)

data_date = str(last_date.date())
out = {"updated": data_date, "count": len(res), "stocks": res.to_dict(orient="records")}

json_path = os.path.join(BASE_DIR, "screener_data.json")
with open(json_path, "w", encoding="utf-8") as fp:
    json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))

print(f"已輸出 {json_path}  ({os.path.getsize(json_path)/1024:.0f} KB)")

cols = ["c1", "c2", "c3", "c4", "d5", "d10", "d24", "d72",
        "over_month", "over_week", "cross",
        "foreign_buy", "trust_buy", "big_up",
        "rev_ath", "rev_same_high", "gm_up", "om_up", "high_yield", "profit"]
print("\n各條件符合檔數:")
for c in cols:
    print(f"  {c}: {res[c].sum()}")