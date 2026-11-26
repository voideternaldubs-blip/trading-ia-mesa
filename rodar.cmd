@echo off
cd /d C:\Users\Administrator\trading-ia
set PYTHONIOENCODING=utf-8
python robo.py >> data\robo.log 2>&1
cd /d C:\Users\Administrator\trading-ia
python central.py >> data\central.log 2>&1
