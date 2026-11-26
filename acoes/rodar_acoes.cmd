@echo off
cd /d C:\Users\Administrator\trading-ia\acoes
set PYTHONIOENCODING=utf-8
python robo_acoes.py >> robo_acoes.log 2>&1
cd /d C:\Users\Administrator\trading-ia
python central.py >> data\central.log 2>&1
