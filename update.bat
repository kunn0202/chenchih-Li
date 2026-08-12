@echo off
chcp 65001 >nul
cd /d D:\stock_system

echo ===== 1/5 更新上市股價 =====
python update_price.py
if errorlevel 1 goto fail

echo.
echo ===== 2/5 更新上櫃股價 =====
python update_price_otc.py
if errorlevel 1 goto fail

echo.
echo ===== 3/5 更新三大法人 =====
python update_inst.py
if errorlevel 1 goto fail

echo.
echo ===== 4/5 執行選股 =====
python screener.py
if errorlevel 1 goto fail

echo.
echo ===== 5/5 匯出圖表 =====
python export_charts.py
if errorlevel 1 goto fail

echo.
echo ===== 上傳 GitHub =====
git add .
git commit -m "資料更新 %date%"
git push
if errorlevel 1 goto fail

echo.
echo ===== 全部完成 =====
echo 請等 1-2 分鐘後開啟網站，並按 Ctrl+F5 重新整理
pause
exit

:fail
echo.
echo ===== 中途失敗，已停止，未上傳 =====
echo 請看上面的錯誤訊息
pause