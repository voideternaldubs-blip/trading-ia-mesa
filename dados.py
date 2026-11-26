"""Baixa histórico de velas da Binance (dados públicos) e salva em data/."""
import os, time, requests, pandas as pd

BASE = "https://data-api.binance.vision/api/v3/klines"
MOEDAS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "ADA", "SUI"]
PASTA = os.path.join(os.path.dirname(__file__), "data")


def baixar(simbolo, intervalo="4h", inicio="2022-01-01"):
    os.makedirs(PASTA, exist_ok=True)
    t = int(pd.Timestamp(inicio, tz="UTC").timestamp() * 1000)
    linhas = []
    while True:
        r = requests.get(BASE, params={"symbol": simbolo + "USDT", "interval": intervalo,
                                       "startTime": t, "limit": 1000}, timeout=20)
        r.raise_for_status()
        lote = r.json()
        if not lote:
            break
        linhas += lote
        t = lote[-1][0] + 1
        if len(lote) < 1000:
            break
        time.sleep(0.2)
    df = pd.DataFrame(linhas, columns=["t", "o", "h", "l", "c", "v", "ct", "qv", "n", "tb", "tq", "x"])
    df = df[["t", "o", "h", "l", "c", "v"]].astype(float)
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.set_index("t")
    df.to_csv(os.path.join(PASTA, f"{simbolo}_{intervalo}.csv"))
    return df


if __name__ == "__main__":
    for m in MOEDAS:
        d = baixar(m)
        print(m, len(d), d.index[0].date(), "->", d.index[-1].date())
