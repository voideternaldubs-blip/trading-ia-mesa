"""Baixa velas de FUTUROS perpétuos (4h) + histórico de financiamento das 30 moedas com mais volume."""
import os, time, requests, pandas as pd

F = "https://fapi.binance.com"
PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fut")
EXCLUI = {"USDC", "FDUSD", "BTCDOM", "XAU", "XAG", "PAXG"}


def universo(n=30):
    t = requests.get(F + "/fapi/v1/ticker/24hr", timeout=20).json()
    t = [x for x in t if x["symbol"].endswith("USDT") and x["symbol"][:-4] not in EXCLUI]
    t.sort(key=lambda x: -float(x["quoteVolume"]))
    return [x["symbol"] for x in t[:n]]


def velas(sym, inicio="2021-01-01"):
    t = int(pd.Timestamp(inicio, tz="UTC").timestamp() * 1000)
    out = []
    while True:
        r = requests.get(F + "/fapi/v1/klines", params={"symbol": sym, "interval": "4h", "startTime": t, "limit": 1500}, timeout=20).json()
        if not r or isinstance(r, dict):
            break
        out += r
        t = r[-1][0] + 1
        if len(r) < 1500:
            break
        time.sleep(0.15)
    df = pd.DataFrame(out, columns=list("tohlcvTqnbBx"))[["t", "o", "h", "l", "c", "q"]].astype(float)
    df["t"] = pd.to_datetime(df.t, unit="ms", utc=True)
    return df.set_index("t")


def financiamento(sym, inicio="2021-01-01"):
    t = int(pd.Timestamp(inicio, tz="UTC").timestamp() * 1000)
    out = []
    while True:
        r = requests.get(F + "/fapi/v1/fundingRate", params={"symbol": sym, "startTime": t, "limit": 1000}, timeout=20).json()
        if not r or isinstance(r, dict):
            break
        out += r
        t = r[-1]["fundingTime"] + 1
        if len(r) < 1000:
            break
        time.sleep(0.15)
    s = pd.Series({pd.Timestamp(x["fundingTime"], unit="ms", tz="UTC"): float(x["fundingRate"]) for x in out})
    return s.sort_index()


if __name__ == "__main__":
    os.makedirs(PASTA, exist_ok=True)
    for s in universo():
        v = velas(s); f = financiamento(s)
        v.to_csv(os.path.join(PASTA, s + "_4h.csv")); f.to_csv(os.path.join(PASTA, s + "_fund.csv"))
        print(s, len(v), v.index[0].date() if len(v) else "-", "| financ.", len(f))
