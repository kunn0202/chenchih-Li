import requests, json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = open(os.path.join(BASE_DIR, "token.txt"), encoding="utf-8").read().strip()

url = "https://api.finmindtrade.com/api/v4/data"
p = {"dataset": "TaiwanStockMonthRevenue", "data_id": "2330",
     "start_date": "2026-06-01", "end_date": "2026-08-31", "token": TOKEN}

j = requests.get(url, params=p, timeout=30).json()
print("status:", j.get("status"), j.get("msg", ""))
print(json.dumps(j.get("data", [])[-3:], ensure_ascii=False, indent=1))