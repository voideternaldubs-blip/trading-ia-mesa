"""FOGUETE MULTI-MOEDA — PAPEL, 100 USD de mentira, preço real da Binance. Ciclo a cada 5 min.
Objetivo: buscar 10x com várias moedas ao mesmo tempo, girando o lucro de uma para a mais forte,
sem perder os 100 de uma vez (piso de 50).

SCAN     -> 10 moedas, velas de 1h
ANALISTA -> força da tendência = consenso de 3 rompimentos (24h, 72h, 168h) × momento ajustado à volatilidade
SNIPER   -> carrega as 4 mais fortes (comprado ou vendido), só com consenso de pelo menos 2 dos 3 sinais
RISCO    -> cada posição mira 6% de oscilação diária da conta (alavancagem alta, mas dividida); teto 4x por moeda, 14x no total
SAÍDA    -> stop em 2,5 ATR da entrada, stop móvel de 3 ATR do melhor preço, sai se a tendência perder o consenso
ROTAÇÃO  -> posição que rendeu +30% sobre a fatia dela realiza METADE: 25% do lucro vai pro COFRE, o resto volta
            pro caixa e é reinvestido na moeda mais forte da próxima rodada
PISO     -> conta + cofre em 50 USD: desliga tudo
"""
import os, json, csv, requests, numpy as np, pandas as pd
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
EST = os.path.join(AQUI, "data", "foguete.json")
TRADES = os.path.join(AQUI, "data", "foguete_trades.csv")
DIARIO = os.path.join(AQUI, "diario")
MOEDAS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "ADA", "SUI"]
INICIAL, PISO, K = 100.0, 50.0, 4
ALVO_DIA, TETO_MOEDA, TETO_TOTAL = 0.06, 4.0, 14.0
CUSTO = 0.001            # 0,05% taxa + 0,05% escorregão por lado
REALIZA, COFRE_PCT = 0.30, 0.25


def velas(m, n=400):
    r = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": m + "USDT", "interval": "1h", "limit": n}, timeout=20).json()
    df = pd.DataFrame(r, columns=list("tohlcvTqnbBx"))[["t", "o", "h", "l", "c"]].astype(float)
    return df


def preco_agora(m):
    return float(requests.get("https://data-api.binance.vision/api/v3/ticker/price", params={"symbol": m + "USDT"}, timeout=15).json()["price"])


def sinal(df):
    c, h, l = df.c, df.h, df.l
    votos = []
    for n in (24, 72, 168):
        hi, lo = h.rolling(n).max().shift(1), l.rolling(n).min().shift(1)
        mid = (hi + lo) / 2
        s = pd.Series(np.nan, index=c.index)
        s[c > hi] = 1; s[c < lo] = -1
        st = s.ffill()
        s[(st == 1) & (c < mid) & s.isna()] = 0; s[(st == -1) & (c > mid) & s.isna()] = 0
        votos.append(s.ffill().fillna(0).iloc[-1])
    cons = sum(votos)
    ret = c.pct_change()
    vol_dia = float(ret.tail(72).std() * np.sqrt(24))
    mom = float(c.iloc[-1] / c.iloc[-73] - 1) / max(vol_dia, 1e-6)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(24).mean())
    return cons, vol_dia, mom, atr


def registrar(linha):
    novo = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["quando", "moeda", "acao", "lado", "preco", "nocional_usd", "resultado_usd", "motivo"])
        w.writerow(linha)


def main():
    agora = datetime.now(timezone.utc)
    e = json.load(open(EST, encoding="utf-8")) if os.path.exists(EST) else \
        {"caixa": INICIAL, "cofre": 0.0, "pos": {}, "ligado": True, "hist": [], "inicio": agora.isoformat()[:16]}
    log = []
    dados = {}
    for m in MOEDAS:
        try:
            df = velas(m)
            df.loc[df.index[-1], "c"] = preco_agora(m)   # vela em andamento com o preço deste instante
            dados[m] = df
        except Exception as ex:
            log.append(f"- SCAN: {m} falhou ({ex})")
    px = {m: float(d.c.iloc[-1]) for m, d in dados.items()}
    sig = {m: sinal(d) for m, d in dados.items()}

    def pl(m, p):  # lucro aberto da posição
        return p["lado"] * p["nocional"] * (px[m] / p["entrada"] - 1)

    conta = e["caixa"] + sum(pl(m, p) + p["margem"] for m, p in e["pos"].items() if m in px)
    patrimonio = conta + e["cofre"]

    # PISO
    if e["ligado"] and patrimonio <= PISO:
        e["ligado"] = False
        log.append(f"- 🛑 PISO: patrimônio {patrimonio:.2f} bateu em {PISO:.0f}. Tudo fechado.")

    # SAÍDA + ROTAÇÃO
    for m, p in list(e["pos"].items()):
        if m not in px:
            continue
        cons, vol, mom, atr = sig[m]
        p["melhor"] = max(p["melhor"], px[m]) if p["lado"] > 0 else min(p["melhor"], px[m])
        motivo = None
        if not e["ligado"]: motivo = "piso"
        elif p["lado"] * (px[m] - p["entrada"]) <= -2.5 * p["atr"]: motivo = "stop 2,5 ATR"
        elif p["lado"] * (p["melhor"] - px[m]) >= 3 * p["atr"] and p["lado"] * (px[m] - p["entrada"]) > 0: motivo = "stop móvel"
        elif p["lado"] * cons < 2: motivo = "tendência perdeu consenso"
        lucro = pl(m, p)
        if not motivo and lucro >= REALIZA * p["margem"]:
            metade = lucro / 2
            p["nocional"] /= 2
            p["margem"] /= 2
            cofre = COFRE_PCT * metade
            e["cofre"] += cofre
            e["caixa"] += p["margem"] + metade - cofre - p["nocional"] * CUSTO
            p["entrada"] = px[m]  # o lucro da metade que ficou continua contando a partir daqui
            registrar([agora.isoformat()[:16], m, "REALIZA 1/2", p["lado"], px[m], round(p["nocional"], 2), round(metade, 2), "rotação +30%"])
            log.append(f"- 💰 ROTAÇÃO {m}: realizou {metade:.2f} USD, {cofre:.2f} pro cofre, resto volta pra girar")
            lucro = 0.0
        if motivo:
            e["caixa"] += p["margem"] + lucro - p["nocional"] * CUSTO
            registrar([agora.isoformat()[:16], m, "FECHA", p["lado"], px[m], round(p["nocional"], 2), round(lucro, 2), motivo])
            log.append(f"- {'🟢' if lucro >= 0 else '🔴'} SAÍDA {m} {'comprado' if p['lado'] > 0 else 'vendido'}: {lucro:+.2f} USD ({motivo})")
            del e["pos"][m]

    # SNIPER: as K mais fortes com consenso
    if e["ligado"]:
        conta = e["caixa"] + sum(pl(m, p) + p["margem"] for m, p in e["pos"].items())
        cand = sorted([(abs(s[2]), m, int(np.sign(s[0]))) for m, s in sig.items() if abs(s[0]) >= 2], reverse=True)[:K]
        bruto = sum(p["nocional"] for p in e["pos"].values())
        for forca, m, lado in cand:
            if m in e["pos"] or len(e["pos"]) >= K:
                continue
            cons, vol, mom, atr = sig[m]
            alav = min(TETO_MOEDA, ALVO_DIA / max(vol, 1e-4))
            nocional = conta * alav
            if bruto + nocional > TETO_TOTAL * conta:
                nocional = max(0.0, TETO_TOTAL * conta - bruto)
            margem = conta / K
            if nocional < 5 or e["caixa"] < margem:
                continue
            e["caixa"] -= margem + nocional * CUSTO
            bruto += nocional
            e["pos"][m] = {"lado": lado, "entrada": px[m], "nocional": nocional, "margem": margem, "atr": atr, "melhor": px[m], "quando": agora.isoformat()[:16]}
            registrar([agora.isoformat()[:16], m, "ABRE", lado, px[m], round(nocional, 2), "", f"consenso {cons:+.0f}/3, força {forca:.1f}, {alav:.1f}x"])
            log.append(f"- 🎯 ABRE {m} {'COMPRADO' if lado > 0 else 'VENDIDO'} {nocional:.0f} USD ({alav:.1f}x da conta) | consenso {cons:+.0f}/3")

    conta = e["caixa"] + sum(pl(m, p) + p["margem"] for m, p in e["pos"].items())
    total = conta + e["cofre"]
    bruto = sum(p["nocional"] for p in e["pos"].values())
    e["hist"].append({"quando": agora.isoformat()[:16], "valor": round(total, 2)})
    e["hist"] = e["hist"][-3000:]
    json.dump(e, open(EST, "w", encoding="utf-8"), indent=1)
    resumo = f"FOGUETE {agora:%H:%M} | total {total:.2f} USD ({total / INICIAL:.2f}x) | cofre {e['cofre']:.2f} | {len(e['pos'])} posições | exposição {bruto / max(conta, 1e-6):.1f}x"
    if log:
        os.makedirs(DIARIO, exist_ok=True)
        open(os.path.join(DIARIO, f"foguete_{agora:%Y-%m-%d}.md"), "a", encoding="utf-8").write(f"## {agora:%H:%M} UTC | {total:.2f} USD\n" + "\n".join(log) + "\n\n")
    print(resumo); print("\n".join(log))


if __name__ == "__main__":
    main()
