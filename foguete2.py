"""FOGUETE v2 — especificação do Claude web (modo Extra), implementada à risca. PAPEL, preço real da Binance Futures.
100 USD = 50 no COFRE (separado, intocável) + 50 no FOGUETE (piso 15). Ciclo a cada 5 min (só risco);
sinais só no fechamento das velas de 4h (o único timeframe com vantagem comprovada nos testes).
Alavancagem CPPI: exposição G = min(m·colchão·σref/σcesta, 20·E). Meta: total ≥ 1000 → encerra.
"""
import os, json, csv, math, time, requests, numpy as np
from datetime import datetime, timezone, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
EST = os.path.join(AQUI, "data", "foguete2.json")
TRADES = os.path.join(AQUI, "data", "foguete2_trades.csv")
TRAVA = os.path.join(AQUI, "data", "foguete2.lock")
DIARIO = os.path.join(AQUI, "diario")
F = "https://fapi.binance.com"
CFG = dict(horizontes=(80, 120, 200), max_pos=12, kappa=1.0, piso=15.0, m=20, lev_max=20, sigma_ref=0.025, cap_moeda=0.25,
           banda_G=0.15, banda_peso=0.25, stop_atr=4.0, taxa=0.0005, slip_stop=0.0005, mmr=0.01,
           funding_max=0.0010, funding_corte=0.0015, crash_btc_1h=-0.06, cofre_pct=0.25, meta=1000.0)
FORA = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "PAXG", "XAUT", "BTCDOM", "XAU", "XAG"}
S = requests.Session()
log = []


def get(path, **p):
    for i in range(3):
        try:
            r = S.get(F + path, params=p, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1 + i)
    raise RuntimeError("binance falhou " + path)


def agora():
    return datetime.now(timezone.utc)


def novo_estado():
    return {"versao": 2, "conta": {"caixa": 50.0, "cofre": 50.0, "marca_dobra": 100.0, "taxas": 0.0, "funding": 0.0,
                                   "status": "ATIVO", "pausa_ate": None, "inicio": agora().isoformat()[:16]},
            "posicoes": {}, "sinais": {}, "universo": {"lista": [], "em": None}, "ultima_4h": None,
            "ultimo_minuto": int((agora() - timedelta(minutes=5)).timestamp() // 60 * 60000), "hist": [], "filtros": {}}


def registrar(st, sym, acao, qtd, preco, valor, res, motivo):
    novo = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["quando", "moeda", "acao", "qtd", "preco", "nocional", "resultado", "motivo"])
        w.writerow([agora().isoformat()[:16], sym, acao, round(qtd, 6), preco, round(valor, 2), round(res, 4), motivo])


# ---------------- universo ----------------
def montar_universo(st):
    info = get("/fapi/v1/exchangeInfo")["symbols"]
    limite = (agora() - timedelta(days=180)).timestamp() * 1000
    ok, filtros = {}, {}
    for s in info:
        if s["contractType"] != "PERPETUAL" or s["status"] != "TRADING" or s["quoteAsset"] != "USDT":
            continue
        if s.get("underlyingType") not in (None, "COIN") or s["baseAsset"] in FORA or s["onboardDate"] > limite:
            continue
        f = {x["filterType"]: x for x in s["filters"]}
        filtros[s["symbol"]] = {"step": float(f["LOT_SIZE"]["stepSize"]), "min": float(f.get("MIN_NOTIONAL", {}).get("notional", 5))}
        ok[s["symbol"]] = 1
    tk = [t for t in get("/fapi/v1/ticker/24hr") if t["symbol"] in ok]
    tk.sort(key=lambda t: -float(t["quoteVolume"]))
    st["universo"] = {"lista": [t["symbol"] for t in tk if float(t["quoteVolume"]) >= 1e8][:30], "em": agora().isoformat()[:16]}
    st["filtros"] = {k: v for k, v in filtros.items() if k in st["universo"]["lista"] or k in st["posicoes"]}
    log.append(f"- SCAN: universo {len(st['universo']['lista'])} moedas")


# ---------------- sinais (4h) ----------------
def estado_donchian(h, l, c, n, ns):
    e = 0
    for t in range(n, len(c)):
        hi, lo = h[t - n:t].max(), l[t - n:t].min()
        hs, ls = h[t - ns:t].max(), l[t - ns:t].min()
        if e == 0:
            e = 1 if c[t] > hi else (-1 if c[t] < lo else 0)
        elif e == 1 and c[t] < ls:
            e = -1 if c[t] < lo else 0
        elif e == -1 and c[t] > hs:
            e = 1 if c[t] > hi else 0
    return e


def k4h(sym):
    r = get("/fapi/v1/klines", symbol=sym, interval="4h", limit=601)[:-1]  # só velas fechadas
    a = np.array([[float(x[2]), float(x[3]), float(x[4])] for x in r])
    return int(r[-1][0]), a[:, 0], a[:, 1], a[:, 2]


def calcular_sinal(sym):
    t, h, l, c = k4h(sym)
    est = {n: estado_donchian(h, l, c, n, n // 2) for n in CFG["horizontes"]}
    lr = np.diff(np.log(c))
    vol = float(lr[-120:].std())
    forca = float(math.log(c[-1] / c[-181]) / (vol * math.sqrt(180))) if vol > 0 else 0.0
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    fund = float(get("/fapi/v1/premiumIndex", symbol=sym)["lastFundingRate"])
    return {"estados": est, "S": sum(est.values()) / 3, "vol_4h": vol, "forca": forca, "atr": float(tr[-20:].mean()),
            "funding_8h": fund, "barra": t, "ret": [float(x) for x in lr[-120:]]}


# ---------------- carteira ----------------
def equity(st, px):
    return st["conta"]["caixa"] + sum(p["lado"] * p["qtd"] * (px[s] - p["entrada"]) for s, p in st["posicoes"].items())


def slip(sym):
    if sym in ("BTCUSDT", "ETHUSDT"): return 0.0002
    if sym in (st_glob or {}).get("universo", {}).get("lista", [])[:10]: return 0.0005
    return 0.0010


def fill(st, sym, delta_usd, preco_ref, motivo, slip_extra=0.0):
    """delta_usd > 0 compra; < 0 vende. Realiza lucro/prejuízo na parte que reduz a posição."""
    preco = preco_ref * (1 + math.copysign(slip(sym) + slip_extra, delta_usd))
    step = st["filtros"].get(sym, {}).get("step", 0.001)
    qtd = math.floor(abs(delta_usd) / preco / step) * step
    if qtd <= 0 or qtd * preco < st["filtros"].get(sym, {}).get("min", 5) and sym not in st["posicoes"]:
        return
    lado_ord = 1 if delta_usd > 0 else -1
    taxa = qtd * preco * CFG["taxa"]
    st["conta"]["caixa"] -= taxa; st["conta"]["taxas"] += taxa
    p = st["posicoes"].get(sym)
    if p and p["lado"] != lado_ord:  # reduzindo/fechando
        q = min(qtd, p["qtd"])
        res = p["lado"] * q * (preco - p["entrada"])
        st["conta"]["caixa"] += res
        p["qtd"] -= q
        registrar(st, sym, "REDUZ" if p["qtd"] > 1e-12 else "FECHA", q, preco, q * preco, res - taxa, motivo)
        if p["qtd"] <= 1e-12:
            log.append(f"- {'🟢' if res >= 0 else '🔴'} SAÍDA {sym}: {res:+.2f} USD ({motivo})")
            del st["posicoes"][sym]
        qtd -= q
        if qtd <= 1e-12:
            return
        p = None
    if p:  # aumentando
        p["entrada"] = (p["entrada"] * p["qtd"] + preco * qtd) / (p["qtd"] + qtd); p["qtd"] += qtd
        registrar(st, sym, "AUMENTA", qtd, preco, qtd * preco, -taxa, motivo)
    else:
        atr = st["sinais"].get(sym, {}).get("atr", preco * 0.03)
        st["posicoes"][sym] = {"lado": lado_ord, "qtd": qtd, "entrada": preco, "melhor": preco, "atr": atr,
                               "stop": preco - lado_ord * CFG["stop_atr"] * atr, "em": agora().isoformat()[:16]}
        registrar(st, sym, "ABRE", qtd, preco, qtd * preco, -taxa, motivo)
        log.append(f"- 🎯 ABRE {sym} {'COMPRADO' if lado_ord > 0 else 'VENDIDO'} {qtd * preco:.0f} USD ({motivo})")


def fechar_tudo(st, px, motivo):
    for s, p in list(st["posicoes"].items()):
        fill(st, s, -p["lado"] * p["qtd"] * px[s] * 1.0001, px[s], motivo)


# ---------------- ciclo ----------------
st_glob = None


def ciclo():
    global st_glob
    st = json.load(open(EST, encoding="utf-8")) if os.path.exists(EST) else novo_estado()
    st_glob = st
    c = st["conta"]
    if c["status"] != "ATIVO":
        print("FOGUETE encerrado:", c["status"]); return
    t0 = agora()
    simb = set(st["posicoes"]) | {"BTCUSDT"}

    # 1) replay minuto a minuto: liquidação -> stops -> funding
    k1 = {}
    for s in simb:
        r = get("/fapi/v1/klines", symbol=s, interval="1m", startTime=st["ultimo_minuto"], limit=1000)
        k1[s] = {int(x[0]): (float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in r if int(x[6]) < t0.timestamp() * 1000}
    minutos = sorted(set().union(*[set(v) for v in k1.values()])) if k1 else []
    for m in minutos:
        eq, manut = c["caixa"], 0.0
        for s, p in st["posicoes"].items():
            if m not in k1.get(s, {}): continue
            o, h, l, cl = k1[s][m]
            pior = l if p["lado"] == 1 else h
            eq += p["lado"] * p["qtd"] * (pior - p["entrada"]); manut += p["qtd"] * pior * CFG["mmr"]
        if st["posicoes"] and eq <= manut:
            log.append("- 💥 LIQUIDAÇÃO: o foguete foi a zero (cofre intacto)")
            for s, p in list(st["posicoes"].items()):
                registrar(st, s, "LIQUIDADO", p["qtd"], 0, 0, -0.0, "liquidação")
            st["posicoes"] = {}; c["caixa"] = 0.0; c["status"] = "LIQUIDADO"; break
        for s, p in list(st["posicoes"].items()):
            if m not in k1.get(s, {}): continue
            o, h, l, cl = k1[s][m]
            if p["lado"] == 1:
                p["melhor"] = max(p["melhor"], h); p["stop"] = max(p["stop"], p["melhor"] - CFG["stop_atr"] * p["atr"])
                bateu = l <= p["stop"]; px_s = o if o < p["stop"] else p["stop"]
            else:
                p["melhor"] = min(p["melhor"], l); p["stop"] = min(p["stop"], p["melhor"] + CFG["stop_atr"] * p["atr"])
                bateu = h >= p["stop"]; px_s = o if o > p["stop"] else p["stop"]
            if bateu:
                fill(st, s, -p["lado"] * p["qtd"] * px_s * 1.0001, px_s, "stop 4 ATR", CFG["slip_stop"])
        # funding nos horários de 8h (00, 08, 16 UTC)
        dt = datetime.fromtimestamp(m / 1000, timezone.utc)
        if dt.minute == 0 and dt.hour % 8 == 0:
            for s, p in st["posicoes"].items():
                taxa_f = st["sinais"].get(s, {}).get("funding_8h", 0.0)
                pg = p["lado"] * p["qtd"] * k1[s].get(m, (0, 0, 0, p["entrada"]))[3] * taxa_f
                c["caixa"] -= pg; c["funding"] += pg
    if minutos:
        st["ultimo_minuto"] = minutos[-1] + 60000
    if c["status"] != "ATIVO":
        return salvar(st, {})

    # 2) marcação e guardas
    px = {s: float(get("/fapi/v1/ticker/price", symbol=s)["price"]) for s in simb}
    E = equity(st, px); T = E + c["cofre"]
    if E <= CFG["piso"]:
        fechar_tudo(st, px, "PISO"); c["status"] = "FIM_PISO"; log.append(f"- 🛑 PISO do foguete ({E:.2f}). Cofre de {c['cofre']:.2f} intacto."); return salvar(st, px)
    if T >= CFG["meta"]:
        fechar_tudo(st, px, "META"); c["status"] = "FIM_META"; log.append(f"- 🏆 META! Total {T:.2f} USD"); return salvar(st, px)
    btc = get("/fapi/v1/klines", symbol="BTCUSDT", interval="1h", limit=2)
    if float(btc[-1][4]) / float(btc[-2][4]) - 1 <= CFG["crash_btc_1h"]:
        c["pausa_ate"] = (agora() + timedelta(hours=4)).isoformat(); log.append("- ⚠️ CRASH no BTC: sem entradas por 4h")

    # 3) cofre por dobra
    if T >= 2 * c["marca_dobra"] and CFG["cofre_pct"] > 0 and E > 0:
        valor = CFG["cofre_pct"] * E
        for s, p in list(st["posicoes"].items()):
            fill(st, s, -p["lado"] * p["qtd"] * px[s] * (valor / E), px[s], "cofre por dobra")
        c["caixa"] -= valor; c["cofre"] += valor; c["marca_dobra"] *= 2
        log.append(f"- 🔒 DOBROU: {valor:.2f} USD do foguete para o cofre (cofre {c['cofre']:.2f})")

    # 4) fechou vela de 4h?
    barra_atual = int(t0.timestamp() // 14400 * 14400 * 1000)
    nova = st["ultima_4h"] != barra_atual
    if nova:
        if not st["universo"]["em"] or st["universo"]["em"][:10] != t0.isoformat()[:10]:
            montar_universo(st)
        for s in set(st["universo"]["lista"]) | set(st["posicoes"]):
            try:
                st["sinais"][s] = calcular_sinal(s)
            except Exception as ex:
                log.append(f"- SCAN: {s} falhou ({ex})")
            time.sleep(0.05)
        st["ultima_4h"] = barra_atual
        log.append(f"- ANALISTA: nova vela de 4h, {sum(1 for x in st['sinais'].values() if x['S'] != 0)} moedas com sinal")
        for s in st["sinais"]:
            if s not in px:
                try: px[s] = float(get("/fapi/v1/ticker/price", symbol=s)["price"])
                except Exception: pass

    # 5) alvos (CPPI) e ordens
    E = equity(st, px)
    pausado = c["pausa_ate"] and agora().isoformat() < c["pausa_ate"]
    cand = []
    for s, g in st["sinais"].items():
        if g["S"] == 0 or s not in px: continue
        aberta = s in st["posicoes"]
        if not aberta and (not nova or pausado or s not in st["universo"]["lista"]): continue
        if not aberta and ((g["S"] > 0 and g["funding_8h"] > CFG["funding_max"]) or (g["S"] < 0 and g["funding_8h"] < -CFG["funding_max"])): continue
        cand.append(s)
    cand.sort(key=lambda s: (s not in st["posicoes"], -abs(st["sinais"][s]["S"]), -st["sinais"][s]["forca"] * np.sign(st["sinais"][s]["S"])))
    cand = cand[:CFG["max_pos"]]
    alvo = {}
    if cand:
        fz = {s: st["sinais"][s]["forca"] * np.sign(st["sinais"][s]["S"]) for s in cand}
        ordem = sorted(cand, key=lambda s: fz[s])
        rk = {s: (i / (len(ordem) - 1) if len(ordem) > 1 else 1.0) for i, s in enumerate(ordem)}
        w = {s: st["sinais"][s]["S"] * (1 + CFG["kappa"] * rk[s]) / max(st["sinais"][s]["vol_4h"], 1e-6) for s in cand}
        tot = sum(abs(v) for v in w.values()); w = {s: v / tot for s, v in w.items()}
        n = min(len(st["sinais"][s]["ret"]) for s in cand)
        R = np.array([st["sinais"][s]["ret"][-n:] for s in cand])
        cesta = (np.array([w[s] for s in cand])[:, None] * R).sum(axis=0)
        pesos = 0.5 ** (np.arange(n)[::-1] / 30); pesos /= pesos.sum()
        sig = float(math.sqrt(max((pesos * cesta ** 2).sum(), 1e-12)) * math.sqrt(6))
        C = max(E - CFG["piso"], 0)
        G = min(CFG["m"] * C * CFG["sigma_ref"] / sig, CFG["lev_max"] * E)
        alvo = {s: w[s] * G for s in cand}
        cap = CFG["cap_moeda"] * G
        exc = sum(max(abs(v) - cap, 0) for v in alvo.values())
        alvo = {s: math.copysign(min(abs(v), cap), v) for s, v in alvo.items()}
        livres = [s for s in alvo if abs(alvo[s]) < cap]
        if exc > 0 and livres:
            soma = sum(abs(alvo[s]) for s in livres)
            for s in livres: alvo[s] = math.copysign(min(cap, abs(alvo[s]) * (1 + exc / soma)), alvo[s])
        alvo = {s: v for s, v in alvo.items() if abs(v) >= st["filtros"].get(s, {}).get("min", 5) or s in st["posicoes"]}
        log.append(f"- ⚙️ RISCO: colchão {C:.2f} | vol da cesta {sig:.2%}/dia | exposição alvo {G:.0f} USD ({G / max(E, 1e-6):.1f}x)") if nova else None
    atual = {s: p["lado"] * p["qtd"] * px[s] for s, p in st["posicoes"].items() if s in px}
    if nova:
        for s, v in atual.items():
            if s not in alvo or np.sign(alvo[s]) != np.sign(v):
                fill(st, s, -v * 1.0001, px[s], "sinal saiu/inverteu")
        atual = {s: p["lado"] * p["qtd"] * px[s] for s, p in st["posicoes"].items()}
        for s, a in alvo.items():
            cur = atual.get(s, 0.0)
            if cur == 0 or abs(a - cur) / abs(a) > CFG["banda_peso"]:
                fill(st, s, a - cur, px[s], "entrada" if cur == 0 else "ajuste de peso")
    elif atual and alvo:
        Ga = sum(abs(v) for v in atual.values()); Gt = sum(abs(v) for s, v in alvo.items() if s in atual)
        if Gt > 0 and abs(Ga - Gt) / Gt > CFG["banda_G"]:
            f = Gt / Ga
            for s, v in atual.items():
                fill(st, s, v * (f - 1), px[s], "CPPI ajusta exposição")
            log.append(f"- ⚙️ CPPI: exposição {Ga:.0f} → {Gt:.0f} USD")
    salvar(st, px)


def salvar(st, px):
    c = st["conta"]
    E = equity(st, px) if px else c["caixa"]
    T = E + c["cofre"]
    G = sum(p["qtd"] * px.get(s, p["entrada"]) for s, p in st["posicoes"].items()) if px else 0
    st["hist"].append({"quando": agora().isoformat()[:16], "valor": round(T, 2), "foguete": round(E, 2), "exposicao": round(G, 2)})
    st["hist"] = st["hist"][-5000:]
    tmp = EST + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, EST)
    res = f"FOGUETE v2 {agora():%H:%M} | total {T:.2f} (foguete {E:.2f} + cofre {c['cofre']:.2f}) | {len(st['posicoes'])} posições | exposição {G:.0f} USD | {c['status']}"
    if log:
        os.makedirs(DIARIO, exist_ok=True)
        open(os.path.join(DIARIO, f"foguete_{agora():%Y-%m-%d}.md"), "a", encoding="utf-8").write(f"## {agora():%H:%M} UTC | {T:.2f} USD\n" + "\n".join(x for x in log if x) + "\n\n")
    print(res); print("\n".join(x for x in log if x))


if __name__ == "__main__":
    if os.path.exists(TRAVA) and time.time() - os.path.getmtime(TRAVA) < 600:
        print("outro ciclo rodando"); raise SystemExit
    open(TRAVA, "w").write(str(os.getpid()))
    try:
        ciclo()
    finally:
        os.remove(TRAVA)
