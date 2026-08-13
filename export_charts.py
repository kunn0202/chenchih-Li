import pandas as pd
import os
import glob
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "stock_data")
INST_DIR = os.path.join(BASE_DIR, "inst_data")
OUT_DIR = os.path.join(BASE_DIR, "chart")
DAYS = 250

os.makedirs(OUT_DIR, exist_ok=True)
files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
print("待處理:", len(files))

NAME_MAP = {
    "Foreign_Investor": "fi",
    "Investment_Trust": "it",
    "Dealer_self": "dl",
}


def load_inst(sid):
    """回傳 {date: {'fi':x, 'it':y, 'dl':z}}，單位為張"""
    path = os.path.join(INST_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return {}
    try:
        d = pd.read_csv(path)
    except Exception:
        return {}
    if d.empty or "name" not in d.columns:
        return {}

    d = d[d["name"].isin(NAME_MAP)].copy()
    if d.empty:
        return {}

    d["buy"] = pd.to_numeric(d["buy"], errors="coerce").fillna(0)
    d["sell"] = pd.to_numeric(d["sell"], errors="coerce").fillna(0)
    d["net"] = (d["buy"] - d["sell"]) / 1000
    d["key"] = d["name"].map(NAME_MAP)

    g = d.groupby(["date", "key"])["net"].sum()
    out = {}
    for (dt, key), val in g.items():
        out.setdefault(str(dt), {})[key] = round(float(val), 1)
    return out


done = 0
for f in files:
    sid = os.path.basename(f).replace(".csv", "")
    df = pd.read_csv(f)
    if len(df) < 30:
        continue

    df = df.sort_values("date")
    df = df[df["close"] > 0].tail(DAYS)

    inst = load_inst(sid)
    dates = df["date"].astype(str).tolist()

    out = {
        "d": [x[5:] for x in dates],
        "o": [round(float(x), 2) for x in df["open"]],
        "h": [round(float(x), 2) for x in df["max"]],
        "l": [round(float(x), 2) for x in df["min"]],
        "c": [round(float(x), 2) for x in df["close"]],
        "v": [int(x / 1000) for x in df["Trading_Volume"]],
        "fi": [inst.get(x, {}).get("fi", 0) for x in dates],
        "it": [inst.get(x, {}).get("it", 0) for x in dates],
        "dl": [inst.get(x, {}).get("dl", 0) for x in dates],
    }

    with open(os.path.join(OUT_DIR, f"{sid}.json"), "w") as fp:
        json.dump(out, fp, separators=(",", ":"))

    done += 1
    if done % 300 == 0:
        print(f"已完成 {done}")

total = sum(os.path.getsize(os.path.join(OUT_DIR, x))
            for x in os.listdir(OUT_DIR)) / 1024 / 1024
print(f"\n完成 {done} 檔，總大小 {total:.1f} MB")