import requests, pandas as pd, time
UA={"User-Agent":"Mozilla/5.0"}
def historico(t, rng="10y", iv="1d"):
    j=requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}",params=({"period1":0,"period2":9999999999} if rng=="max" else {"range":rng})|{"interval":iv,"events":"div,split"},headers=UA,timeout=20).json()["chart"]["result"][0]
    q=j["indicators"]["quote"][0]; adj=j["indicators"].get("adjclose",[{}])[0].get("adjclose")
    df=pd.DataFrame({"o":q["open"],"h":q["high"],"l":q["low"],"c":q["close"],"v":q["volume"]},index=pd.to_datetime(j["timestamp"],unit="s").normalize())
    if adj: df["adj"]=adj
    return df.dropna(subset=["c"])
