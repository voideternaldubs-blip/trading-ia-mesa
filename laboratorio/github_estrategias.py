"""Teste único das estratégias mais famosas do GitHub (freqtrade/freqtrade-strategies 5,7k estrelas, paulcpk
"strategies-that-work") nas regras originais, em dados que os autores não viram (2025 em diante), com taxa.
Execução no estilo Freqtrade: sinal no fechamento, entra/sai na abertura seguinte; stoploss e tabela ROI do arquivo."""
import time, requests, numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

TAXA = 0.0012   # ida+volta: 0,1% Binance + escorregão
MO1H = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK", "AVAX", "SUI", "LTC", "BNB", "AAVE", "NEAR", "DOT", "UNI", "TRX", "ATOM", "FIL", "APT", "ARB"]
MO5M = MO1H[:10]


def baixa(s, iv, ini_ms):
    out = []; fim = int(time.time() * 1000)
    while ini_ms < fim:
        r = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": s + "USDT", "interval": iv, "startTime": ini_ms, "limit": 1000}, timeout=30).json()
        if not isinstance(r, list) or not r: break
        out += r; ini_ms = r[-1][0] + 1
    d = pd.DataFrame([[float(x[i]) for i in (1, 2, 3, 4, 5)] for x in out], columns=["open", "high", "low", "close", "volume"])
    d.index = pd.to_datetime([x[0] for x in out], unit="ms"); return d


# ---------------- indicadores (mesmas fórmulas do TA-Lib) ----------------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()
def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def bb(c, n=20, k=2):
    m = sma(c, n); s = c.rolling(n).std(ddof=0); return m - k * s, m, m + k * s
def macd(c):
    m = ema(c, 12) - ema(c, 26); return m, ema(m, 9)
def atr(d, n=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()
def adx(d, n=14):
    up = d.high.diff(); dn = -d.low.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), d.index); mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), d.index)
    a = atr(d, n); pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / a; mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan); return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi
def cci(d, n=20):
    tp = (d.high + d.low + d.close) / 3; m = sma(tp, n); md = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - m) / (0.015 * md)
def mfi(d, n=14):
    tp = (d.high + d.low + d.close) / 3; mf = tp * d.volume; pos = mf.where(tp > tp.shift(), 0).rolling(n).sum(); neg = mf.where(tp < tp.shift(), 0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))
def stochf(d, k=5, dd=3):
    lo = d.low.rolling(k).min(); hi = d.high.rolling(k).max(); fk = 100 * (d.close - lo) / (hi - lo).replace(0, np.nan); return fk, sma(fk, dd)
def stoch(d):
    fk, _ = stochf(d, 5, 3); sk = sma(fk, 3); return sk, sma(sk, 3)
def sar(d, af0=.02, afm=.2):
    h, l = d.high.values, d.low.values; n = len(h); out = np.zeros(n); up = True; ep = h[0]; s = l[0]; af = af0
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < s: up = False; s = ep; ep = l[i]; af = af0
            elif h[i] > ep: ep = h[i]; af = min(af + af0, afm)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s: up = True; s = ep; ep = h[i]; af = af0
            elif l[i] < ep: ep = l[i]; af = min(af + af0, afm)
        out[i] = s
    return pd.Series(out, d.index)
def fisher(r):
    x = 0.1 * (r - 50); return (np.exp(2 * x) - 1) / (np.exp(2 * x) + 1)
def ha(d):
    hc = (d.open + d.high + d.low + d.close) / 4; ho = hc.copy(); ho.iloc[0] = (d.open.iloc[0] + d.close.iloc[0]) / 2
    for i in range(1, len(d)): ho.iloc[i] = (ho.iloc[i - 1] + hc.iloc[i - 1]) / 2
    return ho, hc
def supertrend(d, m, p):
    a = atr(d, p); hl = (d.high + d.low) / 2; ub = (hl + m * a).values; lb = (hl - m * a).values; c = d.close.values
    fu, fl = ub.copy(), lb.copy(); st = np.zeros(len(c)); up = np.ones(len(c), bool)
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        up[i] = c[i] > fu[i - 1] if not up[i - 1] else not (c[i] < fl[i - 1])
    return pd.Series(up, d.index)
def _ant(x): return x.shift() if hasattr(x, 'shift') else x
def cruza_acima(a, b): return (a > b) & (_ant(a) <= _ant(b))
def cruza_abaixo(a, b): return (a < b) & (_ant(a) >= _ant(b))


# ---------------- as estratégias (regras dos arquivos originais) ----------------
def S001(d):
    e20, e50, e100 = ema(d.close, 20), ema(d.close, 50), ema(d.close, 100); ho, hc = ha(d)
    return cruza_acima(e20, e50) & (hc > e20) & (ho < hc), cruza_acima(e50, e100) & (hc < e20) & (ho > hc)
def S002(d):
    r = rsi(d.close); sk, _ = stoch(d); lo, _, _ = bb(d.close); f = fisher(r); s = sar(d)
    body = (d.close - d.open).abs(); lw = d[["open", "close"]].min(axis=1) - d.low; ham = (lw > 2 * body) & ((d.high - d[["open", "close"]].max(axis=1)) < body)
    return (r < 30) & (sk < 20) & (lo > d.close) & ham, (s > d.close) & (f > 0.3)
def S003(d):
    r = rsi(d.close); f = fisher(r); m = mfi(d); fk, fd = stochf(d); e5, e10, e50, e100 = (ema(d.close, n) for n in (5, 10, 50, 100)); s = sar(d)
    ent = (r < 28) & (r > 0) & (d.close < sma(d.close, 40)) & (f < -0.94) & (m < 16) & ((e50 > e100) | cruza_acima(e5, e10)) & (fd > fk) & (fd > 0)
    return ent, (s > d.close) & (f > 0.3)
def S005(d):
    r = rsi(d.close); fk, fd = stochf(d); fn = (fisher(r) + 1) * 50; m, _ = macd(d.close); _, _, mdi = adx(d); s = sar(d)
    ent = (d.volume > d.volume.rolling(150).mean() * 4) & (d.close < sma(d.close, 40)) & (fd > fk) & (r > 26) & (fd > 1) & (fn < 5)
    return ent, cruza_acima(r, 74) & (m < 0) & (mdi > 4)
def BbandRsi(d):
    r = rsi(d.close); lo, _, _ = bb(d.close); return (r < 30) & (d.close < lo), r > 70
def ADXMomentum(d):
    a, p, m = adx(d); mo = d.close - d.close.shift(14); return (a > 25) & (mo > 0) & (p > 25) & (p > m), (a > 25) & (mo < 0) & (m > 25) & (p < m)
def AdxSmas(d):
    a, _, _ = adx(d); s3, s6 = sma(d.close, 3), sma(d.close, 6); return (a > 25) & cruza_acima(s3, s6), (a < 25) & cruza_acima(s6, s3)
def ClucMay(d):
    lo, mid, _ = bb(d.close); return (d.close < ema(d.close, 50)) & (d.close < 0.985 * lo) & (d.volume < d.volume.rolling(30).mean().shift() * 20), d.close > mid
def BinHV45(d):
    m = sma(d.close, 40); s = d.close.rolling(40).std(ddof=0); lower = m - 2 * s; bbd = (m - lower).abs(); cd = (d.close - d.close.shift()).abs(); tail = (d.close - d.low).abs()
    ent = lower.shift().gt(0) & bbd.gt(d.close * 7 / 1000) & cd.gt(d.close * 17 / 1000) & tail.lt(bbd * 25 / 1000) & d.close.lt(lower.shift()) & d.close.le(d.close.shift())
    return ent, pd.Series(False, d.index)
def CombinedBinHAndCluc(d):
    m = sma(d.close, 40); s = d.close.rolling(40).std(ddof=0); lower = m - 2 * s; bbd = (m - lower).abs(); cd = (d.close - d.close.shift()).abs(); tail = (d.close - d.low).abs()
    lo, mid, _ = bb(d.close)
    a = lower.shift().gt(0) & bbd.gt(d.close * 0.008) & cd.gt(d.close * 0.0175) & tail.lt(bbd * 0.25) & d.close.lt(lower.shift()) & d.close.le(d.close.shift())
    b = (d.close < ema(d.close, 50)) & (d.close < 0.985 * lo) & (d.volume < d.volume.rolling(30).mean().shift() * 20)
    return a | b, d.close > mid
def MACDStrategy(d):
    m, s = macd(d.close); c = cci(d); return (m > s) & (c <= -48), (m < s) & (c >= 687)
def Quickie(d):
    t = ema(ema(ema(d.close, 9), 9), 9); t = 3 * ema(d.close, 9) - 3 * ema(ema(d.close, 9), 9) + t
    _, mid, _ = bb(d.close); a, _, _ = adx(d)
    return (a > 30) & (t < mid) & (t > t.shift()) & (sma(d.close, 200) > d.close), (a > 70) & (t > mid) & (t < t.shift())
def LowBB(d):
    lo, _, _ = bb(d.close); return d.close <= 0.98 * lo, pd.Series(False, d.index)
def DoubleEMATrend(d):
    e9, e21, e200 = ema(d.close, 9), ema(d.close, 21), ema(d.close, 200); return cruza_acima(e9, e21) & (d.low > e200), cruza_abaixo(e9, e21) | (d.low < e200)
def MACDTrend(d):
    m, s = macd(d.close); e = ema(d.close, 100); return (m < 0) & cruza_acima(m, s) & (d.low > e), cruza_abaixo(m, pd.Series(0, d.index)) | (d.low < e)
def RSIDirTrend(d):
    r = rsi(d.close, 4); e = ema(d.close, 100); return cruza_acima(r, pd.Series(15, d.index)) & (d.low > e), cruza_acima(r, pd.Series(85, d.index)) | (d.low < e)
def Supertrend3(d):
    b = supertrend(d, 4, 8) & supertrend(d, 7, 9) & supertrend(d, 1, 8)
    s = (~supertrend(d, 1, 16)) & (~supertrend(d, 3, 18)) & (~supertrend(d, 6, 18)); return b, s
def DonchianTendencia(d):   # o nosso (referência), só comprado para comparar igual
    sinal = pd.Series(0.0, d.index)
    for n in (80, 120, 200):
        hi = d.high.rolling(n).max().shift(); lo = d.low.rolling(n).min().shift()
        st = pd.Series(np.where(d.close > hi, 1, np.where(d.close < lo, -1, np.nan)), d.index).ffill().fillna(0); sinal += st
    return (sinal > 0) & (sinal.shift() <= 0), sinal <= 0
def BuyHold(d):
    e = pd.Series(False, d.index); e.iloc[1] = True; return e, pd.Series(False, d.index)

# nome: (função, tempo gráfico, stoploss, tabela ROI {minutos: lucro})
EST = {
    "Strategy001": (S001, "5m", -0.10, {60: .01, 30: .03, 20: .04, 0: .05}),
    "Strategy002": (S002, "5m", -0.10, {60: .01, 30: .03, 20: .04, 0: .05}),
    "Strategy003": (S003, "5m", -0.10, {60: .01, 30: .03, 20: .04, 0: .05}),
    "Strategy005": (S005, "5m", -0.10, {1440: .01, 80: .02, 40: .03, 20: .04, 0: .05}),
    "ClucMay72018": (ClucMay, "5m", -0.05, {0: .01}),
    "BinHV45": (BinHV45, "5m", -0.05, {0: .0125}),
    "CombinedBinHAndCluc": (CombinedBinHAndCluc, "5m", -0.05, {0: .05}),
    "MACDStrategy": (MACDStrategy, "5m", -0.30, {60: .01, 30: .03, 20: .04, 0: .05}),
    "Quickie": (Quickie, "5m", -0.25, {100: .01, 30: .03, 15: .06, 10: .15}),
    "Low_BB": (LowBB, "5m", -0.015, {15: .5, 10: .04, 1: .05, 0: .9}),
    "BbandRsi": (BbandRsi, "1h", -0.25, {0: .1}),
    "ADXMomentum": (ADXMomentum, "1h", -0.25, {0: .01}),
    "AdxSmas": (AdxSmas, "1h", -0.25, {0: .1}),
    "DoubleEMACrossoverWithTrend": (DoubleEMATrend, "1h", -0.20, {}),
    "MACDCrossoverWithTrend": (MACDTrend, "1h", -0.20, {}),
    "RSIDirectionalWithTrend": (RSIDirTrend, "1h", -0.10, {}),
    "Supertrend": (Supertrend3, "1h", -0.265, {2221: 0, 861: .029, 372: .058, 0: .087}),
    "NOSSA tendência (Donchian, só compra)": (DonchianTendencia, "1h", -0.50, {}),
    "Comprar e segurar": (BuyHold, "1h", -1.0, {}),
}


def roda(d, f, sl, roi, minutos):
    ent, sai = f(d); ent = ent.fillna(False).values; sai = sai.fillna(False).values
    o, h, l = d.open.values, d.high.values, d.low.values
    tabela = sorted(roi.items(), reverse=True); res = []; i = 1; n = len(d)
    while i < n - 1:
        if not ent[i - 1]:
            i += 1; continue
        e = o[i]; stop = e * (1 + sl); j = i; saiu = None
        while j < n:
            if l[j] <= stop: saiu = stop; break
            idade = (j - i) * minutos
            alvo = next((v for m, v in tabela if idade >= m), None)
            if alvo is not None and h[j] >= e * (1 + alvo): saiu = max(o[j], e * (1 + alvo)) if j > i else e * (1 + alvo); break
            if j > i and sai[j - 1]: saiu = o[j]; break
            j += 1
        if saiu is None: saiu = d.close.values[-1]; j = n - 1
        res.append(saiu / e - 1 - TAXA); i = j + 1
    return res


def main():
    ini1 = int(pd.Timestamp("2025-01-01").timestamp() * 1000); ini5 = int(time.time() * 1000) - 120 * 86400000
    with ThreadPoolExecutor(8) as ex:
        h1 = dict(zip(MO1H, ex.map(lambda m: baixa(m, "1h", ini1), MO1H)))
        m5 = dict(zip(MO5M, ex.map(lambda m: baixa(m, "5m", ini5), MO5M)))
    print(f"dados: 1h {MO1H[0]} {len(h1['BTC'])} candles desde 2025-01 | 5m {len(m5['BTC'])} candles (120 dias)\n")
    linhas = []
    for nome, (f, tf, sl, roi) in EST.items():
        dados = m5 if tf == "5m" else h1; mins = 5 if tf == "5m" else 60
        todos = []; por_moeda = []
        for m, d in dados.items():
            try:
                r = roda(d, f, sl, roi, mins)
            except Exception as ex:
                print(f'  {nome} em {m}: pulei ({ex})'); r = []
            todos += r; por_moeda.append(np.prod([1 + x for x in r]) - 1 if r else 0)
        g = [x for x in todos if x > 0]; p = [x for x in todos if x <= 0]
        pf = sum(g) / abs(sum(p)) if p else float("inf")
        linhas.append((nome, tf, len(todos), 100 * len(g) / max(1, len(todos)), 100 * np.mean(todos) if todos else 0, pf, 100 * np.mean(por_moeda)))
    import json, os
    from datetime import datetime, timezone
    rk = [{"estrategia": l[0], "tempo": l[1], "trades": l[2], "acerto_pct": round(l[3], 1), "media_trade_pct": round(l[4], 3),
           "fator_lucro": (round(l[5], 2) if l[5] != float("inf") else None), "retorno_medio_moeda_pct": round(l[6], 1)} for l in sorted(linhas, key=lambda x: -x[6])]
    os.makedirs("data", exist_ok=True)
    json.dump({"gerado": datetime.now(timezone.utc).isoformat()[:16], "periodo_1h": "2025-01-01 até hoje", "periodo_5m": "últimos 120 dias",
               "moedas_1h": MO1H, "moedas_5m": MO5M, "taxa_ida_volta_pct": TAXA * 100, "ranking": rk},
              open(os.path.join("data", "estrategias.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{'estratégia':40} {'tempo':5} {'trades':>6} {'acerto':>7} {'média/trade':>11} {'fator lucro':>11} {'retorno médio por moeda':>24}")
    for l in sorted(linhas, key=lambda x: -x[6]):
        print(f"{l[0]:40} {l[1]:5} {l[2]:6d} {l[3]:6.1f}% {l[4]:+10.3f}% {l[5]:11.2f} {l[6]:+23.1f}%")


if __name__ == "__main__":
    main()
