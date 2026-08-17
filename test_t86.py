import requests

UA = {"User-Agent": "Mozilla/5.0"}
DATE = "20260814"

urls = [
    ("舊路徑 ALLBUT0999", f"https://www.twse.com.tw/fund/T86?response=json&date={DATE}&selectType=ALLBUT0999"),
    ("舊路徑 ALL",        f"https://www.twse.com.tw/fund/T86?response=json&date={DATE}&selectType=ALL"),
    ("新路徑 ALL",        f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={DATE}&selectType=ALL"),
]

for name, u in urls:
    try:
        j = requests.get(u, headers=UA, timeout=30).json()
        print(f"{name}: stat={j.get('stat')}, 筆數={len(j.get('data') or [])}")
    except Exception as e:
        print(f"{name}: 失敗 {type(e).__name__}")