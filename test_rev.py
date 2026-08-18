import requests, json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = open(os.path.join(BASE_DIR, "token.txt"), encoding="utf-8").read().strip()

url = "https://api.finmindtrade.com/api/v4/data"
p = {"dataset": "TaiwanStockFinancialStatements", "data_id": "2330",
     "start_date": "2026-01-01", "end_date": "2026-12-31", "token": TOKEN}

j = requests.get(url, params=p, timeout=30).json()
rows = j.get("data", [])
print("status:", j.get("status"))
print("筆數:", len(rows))
dates = sorted(set(r["date"] for r in rows))
print("有資料的季度:", dates)
for r in rows:
    if r["type"] in ("Revenue", "GrossProfit", "OperatingIncome") and r["date"] == dates[-1]:
        print(r["date"], r["type"], r["value"], r.get("origin_name"))