"""PRÉDIO DE AGENTES — um batalhão, um analista por moeda, todos ao mesmo tempo.

TÉRREO      ARANHA (notícias, já roda no motor)
1º ANDAR    ANALISTAS DE MOEDA: um por moeda. Junta tendência (Donchian 80/120/200 em 4h), Máquina do Tempo
            (chance de alvo x stop dos dois lados), financiamento e notícias da moeda, e pede o veredito a uma IA
            (Groq: GPT-OSS 120B / GPT-OSS 20B / Qwen; NVIDIA: GLM / Kimi — rodízio, todas grátis).
2º ANDAR    COMITÊ DE RISCO: ranqueia por valor esperado e votos.
3º ANDAR    DIRETORIA: quando a IA pura está sem posição, abre o próximo trade do método 1:3 nas melhores
            (só onde tendência + Máquina do Tempo + IA concordam e o valor esperado é positivo).
PLACAR      cada veredito é guardado com o preço; 24h depois o prédio confere quem acertou.
Saída: data/predio.json"""
import os, re, json, time, random, threading, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(AQUI, "data")
SAIDA = os.path.join(D, "predio.json")
F = "https://testnet.binancefuture.com"
DADOS = "https://data-api.binance.vision/api/v3/klines"
ESTAVEIS = {"USDCUSDT", "FDUSDUSDT", "USD1USDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT", "EURUSDT"}


# ---------------- IAs (rodízio de provedores grátis) ----------------
def _chave_groq():
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if k:
        return k
    for arq, nome in ((os.path.join(os.path.expanduser("~"), "ayslla-discord", ".env"), "IA_API_KEY"),
                      (os.path.join(os.path.expanduser("~"), "void-bots", "nuvem", "env", "noticias.env"), "GROQ_API_KEY")):
        try:
            for l in open(arq, encoding="utf-8", errors="ignore"):
                m = re.match(r"\s*" + nome + r"\s*=\s*['\"]?([^'\"\s#]+)", l)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return ""


def _chave_nvidia():
    k = os.environ.get("NVIDIA_API_KEY", "").strip()
    if k:
        return k
    try:
        import sys
        sys.path.insert(0, os.path.join(AQUI, "equipe"))
        import ia
        return ia._chave() or ""
    except Exception:
        return ""


# cada cérebro: função de acordo com a inteligência, e LIMITE respeitado (por minuto e por dia)
GROQ = "https://api.groq.com/openai/v1"; NV = "https://integrate.api.nvidia.com/v1"
CEREBROS = {}
_g = _chave_groq()
if _g:
    CEREBROS["GPT-OSS 120B"] = dict(base=GROQ, modelo="openai/gpt-oss-120b", chave=_g, papeis=("comite",), por_min=7, por_dia=900, tok_min=8000)
    CEREBROS["GPT-OSS 20B"] = dict(base=GROQ, modelo="openai/gpt-oss-20b", chave=_g, papeis=("analista",), por_min=8, por_dia=900, tok_min=8000)
    CEREBROS["Qwen 27B"] = dict(base=GROQ, modelo="qwen/qwen3.8-27b", chave=_g, papeis=("analista",), por_min=8, por_dia=900, tok_min=8000)
_n = _chave_nvidia()
if _n:
    CEREBROS["Kimi K3.1"] = dict(base=NV, modelo="moonshotai/kimi-k3.1-pro", chave=_n, papeis=("comite",), por_min=20, por_dia=3000, tok_min=10**9)
    CEREBROS["GLM 5.3"] = dict(base=NV, modelo="z-ai/glm-5.3-flash", chave=_n, papeis=("analista",), por_min=30, por_dia=5000, tok_min=10**9)
# ---------- APRENDIZADO: o prédio aprende com os próprios erros ----------
PESO = {}        # cérebro -> chance de acerto aprendida (Laplace: (acertos+1)/(vereditos+2))
BANIDOS = set()  # cérebros que erram demais saem da função de analista (ficam só de reserva)
HIST_MOEDA = {}  # moeda -> últimos vereditos conferidos (cérebro, decisão, resultado)


def aprende(hist):
    PESO.clear(); BANIDOS.clear(); HIST_MOEDA.clear()
    por = {}
    for h in hist:
        if h.get("resultado") is None:
            continue
        p = por.setdefault(h.get("cerebro", "?"), [0, 0]); p[0] += 1; p[1] += h["resultado"] > 0
        HIST_MOEDA.setdefault(h["simbolo"], []).append((h.get("cerebro"), h["decisao"], h["resultado"]))
    for n, (v, a) in por.items():
        PESO[n] = (a + 1) / (v + 2)
        if v >= 30 and a / v < 0.45:
            BANIDOS.add(n)
    for k in HIST_MOEDA:
        HIST_MOEDA[k] = HIST_MOEDA[k][-6:]


COTA = os.path.join(D, "cotas_ia.json")
_lk = threading.Lock()
try:
    _cota = json.load(open(COTA, encoding="utf-8"))
except Exception:
    _cota = {}
_min = {}   # nome -> lista de (instante, tokens) do último minuto
_ruim = {}  # nome -> instante até quando fica de castigo (erro/limite)


def _pode(nome, tok):
    c = CEREBROS[nome]; agora = time.time(); hoje = datetime.now(timezone.utc).date().isoformat()
    if _ruim.get(nome, 0) > agora:
        return False
    dia = _cota.get(nome, {})
    if dia.get("dia") == hoje and dia.get("n", 0) >= c["por_dia"]:
        return False
    j = [x for x in _min.get(nome, []) if agora - x[0] < 60]; _min[nome] = j
    return len(j) < c["por_min"] and sum(x[1] for x in j) + tok <= c["tok_min"]


def _gasta(nome, tok):
    hoje = datetime.now(timezone.utc).date().isoformat()
    d = _cota.get(nome, {})
    _cota[nome] = {"dia": hoje, "n": (d.get("n", 0) if d.get("dia") == hoje else 0) + 1}
    _min.setdefault(nome, []).append((time.time(), tok))


def pergunta(sistema, texto, papel="analista", i=0, tok=1400):
    """Escolhe um cérebro do PAPEL com cota livre (rodízio); se todos do papel estiverem cheios, espera;
    se não der, usa qualquer outro com cota. Devolve (nome, texto)."""
    nomes = [n for n, c in CEREBROS.items() if papel in c["papeis"]] or list(CEREBROS)
    if papel == "analista":
        bons = [n for n in nomes if n not in BANIDOS] or nomes
        roleta = [n for n in bons for _ in range(max(1, round(PESO.get(n, .5) * 10)))]   # peso aprendido
        prim = roleta[i % len(roleta)] if roleta else None
        nomes = ([prim] if prim else []) + [n for n in bons if n != prim] + [n for n in nomes if n in BANIDOS]
    outros = [n for n in CEREBROS if n not in nomes]
    nomes = nomes[i % len(nomes):] + nomes[:i % len(nomes)]
    for tentativa in range(40):
        for nome in nomes + (outros if tentativa > 20 else []):
            with _lk:
                if not _pode(nome, tok):
                    continue
                _gasta(nome, tok)
            c = CEREBROS[nome]
            try:
                r = requests.post(c["base"] + "/chat/completions", headers={"Authorization": "Bearer " + c["chave"]},
                                  json={"model": c["modelo"], "temperature": 0.2, "max_tokens": 700,
                                        "messages": [{"role": "system", "content": sistema + (f"\nVocê é o cérebro {nome}. Seu acerto conferido até agora: {PESO[nome] * 100:.0f}%. Aprenda com o histórico desta moeda que vem nos dados: não repita o erro." if nome in PESO else "")},
                                                     {"role": "user", "content": texto}]}, timeout=90)
                if r.status_code == 429:
                    _ruim[nome] = time.time() + 30; continue
                r.raise_for_status()
                return nome, r.json()["choices"][0]["message"]["content"] or ""
            except Exception:
                _ruim[nome] = time.time() + 60
        time.sleep(3)
    return None, ""


def salva_cota():
    with _lk:
        json.dump(_cota, open(COTA, "w", encoding="utf-8"), indent=1)


def json_de(t):
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S)
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


# ---------------- dados de cada moeda ----------------
def velas(s, intervalo, limite, inicio=None):
    out = []
    p = {"symbol": s, "interval": intervalo, "limit": 1000 if inicio else min(1000, limite)}
    if inicio:
        p["startTime"] = inicio
    while True:
        r = requests.get(DADOS, params=p, timeout=30).json()
        if not isinstance(r, list) or not r:
            break
        out += r
        if not inicio or len(r) < 1000:
            break
        p["startTime"] = r[-1][0] + 1
    return [(float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in out]


def tendencia(v4):
    """Donchian 80/120/200 em 4h (o método que passou nos testes): +1 compra, -1 venda, média dos três."""
    tot = 0
    for n in (80, 120, 200):
        est = 0
        for i in range(n, len(v4)):
            hi = max(x[1] for x in v4[i - n:i]); lo = min(x[2] for x in v4[i - n:i])
            if v4[i][3] > hi: est = 1
            elif v4[i][3] < lo: est = -1
        tot += est
    return tot / 3


def maquina(v15, lado, n=500, stop=0.03, alvo=0.09, passos=None, bloco=4):
    rel = [(h / pc, l / pc, c / pc) for (_, _, _, pc), (_, h, l, c) in zip(v15, v15[1:])]
    if len(rel) < 50:
        return 0, 0
    passos = passos or 400
    a = s = 0
    for _ in range(n):
        p = 1.0; k = 0; res = None
        while k < passos and res is None:
            i = random.randrange(len(rel) - bloco)
            for rh, rl, rc in rel[i:i + bloco]:
                h, l = p * rh, p * rl
                if lado > 0:
                    if l <= 1 - stop: res = "s"; break
                    if h >= 1 + alvo: res = "a"; break
                else:
                    if h >= 1 + stop: res = "s"; break
                    if l <= 1 - alvo: res = "a"; break
                p *= rc; k += 1
        a += res == "a"; s += res == "s"
    return a / n, s / n


SIS = """Você é o analista de UMA moeda num prédio de agentes de trading. Recebe os números da moeda e decide.
Regras da casa: só a tendência (rompimentos de 80/120/200 candles de 4h) passou nos testes históricos; a Máquina do Tempo
dá a chance de bater o alvo (9%) antes do stop (3%) em até 4 dias para cada lado; valor esperado = chance_alvo*3 - chance_stop.
Seja frio e honesto: se não houver vantagem clara, decida FORA. Responda SÓ JSON:
{"decisao":"COMPRA|VENDA|FORA","confianca":1,"motivo":"uma frase curta em português do Brasil, sem jargão"}
confianca de 1 (fraca) a 5 (forte)."""


def analista(item):
    i, s, extra = item
    try:
        v4 = velas(s, "4h", 230)
        v15 = velas(s, "15m", 0, inicio=int(time.time() * 1000) - 30 * 86400000)
        preco = v4[-1][3]
        tend = tendencia(v4)
        ca_c, cs_c = maquina(v15, 1); ca_v, cs_v = maquina(v15, -1)
        ev_c = ca_c * 3 - cs_c; ev_v = ca_v * 3 - cs_v
        try:
            fund = float(requests.get(F + "/fapi/v1/premiumIndex", params={"symbol": s}, timeout=10).json()["lastFundingRate"]) * 100
        except Exception:
            fund = 0.0
        moeda = s.replace("USDT", "")
        nots = [n.get("titulo", "") for n in extra.get("noticias", []) if moeda in (n.get("ativos") or [])][:4]
        dados = {"moeda": moeda, "preco": preco, "var_24h_pct": round((preco / v4[-7][3] - 1) * 100, 2), "var_7d_pct": round((preco / v4[-43][3] - 1) * 100, 2),
                 "tendencia_4h": round(tend, 2), "chance_alvo_compra": round(ca_c, 2), "chance_stop_compra": round(cs_c, 2),
                 "chance_alvo_venda": round(ca_v, 2), "chance_stop_venda": round(cs_v, 2), "valor_esperado_compra": round(ev_c, 2),
                 "valor_esperado_venda": round(ev_v, 2), "financiamento_pct": round(fund, 4), "noticias": nots,
                 "medo_ganancia": extra.get("fg"),
                 "historico_desta_moeda": [{"cerebro": c, "disse": dcs, "resultado_24h_pct": r} for c, dcs, r in HIST_MOEDA.get(s, [])]}
        cerebro, txt = pergunta(SIS, json.dumps(dados, ensure_ascii=False), "analista", i)
        j = json_de(txt) or {}
        dec = str(j.get("decisao", "FORA")).upper()
        dec = dec if dec in ("COMPRA", "VENDA", "FORA") else "FORA"
        return {**dados, "simbolo": s, "decisao": dec, "confianca": int(j.get("confianca", 1) or 1), "motivo": str(j.get("motivo", ""))[:220],
                "cerebro": cerebro or "sem IA (regra)", "quando": datetime.now(timezone.utc).isoformat()[:16]}
    except Exception as ex:
        return {"simbolo": s, "moeda": s.replace("USDT", ""), "erro": str(ex)[:120], "decisao": "FORA", "confianca": 0, "quando": datetime.now(timezone.utc).isoformat()[:16]}


# ---------------- placar dos analistas (quem acerta) ----------------
def confere_placar(antigo, precos):
    hist = antigo.get("historico", [])
    agora = datetime.now(timezone.utc)
    for h in hist:
        if h.get("resultado") is None and h["decisao"] != "FORA":
            idade = (agora - datetime.fromisoformat(h["quando"]).replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if idade >= 24 and h["simbolo"] in precos:
                mov = (precos[h["simbolo"]] / h["preco"] - 1) * (1 if h["decisao"] == "COMPRA" else -1)
                h["resultado"] = round(mov * 100, 2)
    por = {}
    for h in hist:
        if h.get("resultado") is not None:
            k = h.get("cerebro", "?"); p = por.setdefault(k, {"vereditos": 0, "acertos": 0, "soma_pct": 0.0})
            p["vereditos"] += 1; p["acertos"] += h["resultado"] > 0; p["soma_pct"] += h["resultado"]
    for k, p in por.items():
        p["acerto_pct"] = round(100 * p["acertos"] / p["vereditos"], 1); p["soma_pct"] = round(p["soma_pct"], 2)
    return hist[-3000:], por


# ---------------- diretoria: abre o próximo trade da IA pura ----------------
def diretoria(analises, log):
    try:
        import binance_demo as b
        e = json.load(open(os.path.join(D, "ia_pura.json"), encoding="utf-8"))
    except Exception as ex:
        log.append(f"diretoria sem acesso: {str(ex)[:80]}"); return
    if e.get("posicoes"):
        log.append(f"diretoria: IA pura já tem {len(e['posicoes'])} posições abertas, espera elas fecharem"); return
    caixa = float(e.get("caixa", 100))
    if caixa < 20:
        log.append("diretoria: caixa abaixo de 20, não abre mais nada"); return
    # ADAPTAÇÃO: olha os últimos trades fechados da carteira
    fech = e.get("fechadas", [])[-4:]
    perdas = sum(1 for f in fech if f.get("resultado", 0) < 0)
    cauteloso = len(fech) >= 2 and perdas >= 2 and sum(f.get("resultado", 0) for f in fech) < 0
    ev_min, conf_min, fator = (0.30, 4, 0.6) if cauteloso else (0.15, 3, 1.0)
    log.append("diretoria aprendeu: " + (f"{perdas} perdas nos últimos {len(fech)} fechamentos -> MODO CAUTELOSO (só confiança >=4, valor esperado >=0,30, risco x0,6)" if cauteloso else "últimos fechamentos ok -> modo normal"))
    ok = []
    for a in analises:
        if a.get("erro") or a["decisao"] == "FORA" or a["confianca"] < conf_min or a.get("vetado"):
            continue
        lado = 1 if a["decisao"] == "COMPRA" else -1
        ev = a["valor_esperado_compra"] if lado > 0 else a["valor_esperado_venda"]
        if ev > ev_min and a["tendencia_4h"] * lado > 0:   # IA + tendência + máquina do tempo concordam
            ok.append((ev * a["confianca"], lado, a))
    ok.sort(key=lambda x: -x[0]); ok = ok[:4]
    if not ok:
        log.append("diretoria: nenhuma moeda com IA + tendência + máquina do tempo concordando; fica fora"); return
    # RISCO: arrisca mais quando vale a pena (não toda hora).
    #  sinal FORTE (comitê aprovou, confiança >= 4 e valor esperado >= 0,4 em média) -> 50% da carteira
    #  sinal comum -> 30%;  depois de um acerto (caixa > 100) -> aposta o lucro inteiro se for maior
    forte = sum(1 for _, _, a in ok if a["confianca"] >= 4) >= max(1, len(ok) // 2) and sum((a["valor_esperado_compra"] if l > 0 else a["valor_esperado_venda"]) for _, l, a in ok) / len(ok) >= 0.4
    base = (0.5 if forte else 0.3) * caixa
    risco = (max(base, caixa - 100) if caixa > 100 else base) * fator
    log.append(f"diretoria: sinal {'FORTE' if forte else 'comum'} -> arrisca {risco:.0f} USD para ganhar ~{risco * 3:.0f}")
    expo_total = risco / 0.03
    info = {x["symbol"]: x for x in b._req("GET", "/fapi/v1/exchangeInfo", assinado=False)["symbols"]}
    import math
    for s_, (_, lado, a) in zip(range(len(ok)), ok):
        s = a["simbolo"]
        if s not in info:
            continue
        e["posicoes"][s] = {"lado": lado, "qtd": 0, "entrada": 0, "stop": 0, "alvo": 0}
    json.dump(e, open(os.path.join(D, "ia_pura.json"), "w", encoding="utf-8"), indent=1)   # reserva antes de operar
    for _, lado, a in ok:
        s = a["simbolo"]
        if s not in info:
            continue
        try:
            tick = float([f for f in info[s]["filters"] if f["filterType"] == "PRICE_FILTER"][0]["tickSize"]); d = max(0, -int(round(math.log10(tick))))
            b._req("POST", "/fapi/v1/leverage", symbol=s, leverage=20)
            px = float(b._req("GET", "/fapi/v1/ticker/price", assinado=False, symbol=s)["price"])
            b.ordem(s, lado * (expo_total / len(ok)) / px)
            pr = b._req("GET", "/fapi/v2/positionRisk", symbol=s)[0]; q = abs(float(pr["positionAmt"])); ent = float(pr["entryPrice"])
            st = round(ent * (1 - 0.03 * lado), d); tp = round(ent * (1 + 0.09 * lado), d)
            lado_ord = "SELL" if lado > 0 else "BUY"
            for tipo, tr in (("STOP_MARKET", st), ("TAKE_PROFIT_MARKET", tp)):
                b._req("POST", "/fapi/v1/algoOrder", algoType="CONDITIONAL", symbol=s, side=lado_ord, type=tipo, triggerPrice=f"{tr:.{d}f}", closePosition="true", workingType="MARK_PRICE")
            e["posicoes"][s] = {"lado": lado, "qtd": q, "entrada": ent, "stop": st, "alvo": tp, "em": datetime.now(timezone.utc).isoformat()[:16],
                                "tese": f"prédio: {a['cerebro']} disse {a['decisao']} ({a['confianca']}/5): {a['motivo']}"}
            log.append(f"DIRETORIA abriu {s} {'COMPRADO' if lado > 0 else 'VENDIDO'} a {ent:g} | stop {st:g} alvo {tp:g} | {a['motivo'][:90]}")
        except Exception as ex:
            e["posicoes"].pop(s, None); log.append(f"diretoria falhou em {s}: {str(ex)[:90]}")
    e["fase"] = int(e.get("fase", 1)) + 1
    json.dump(e, open(os.path.join(D, "ia_pura.json"), "w", encoding="utf-8"), indent=1)


def main():
    inicio = time.time()
    antigo = {}
    try:
        antigo = json.load(open(SAIDA, encoding="utf-8"))
    except Exception:
        pass
    fut = {s["symbol"] for s in requests.get(F + "/fapi/v1/exchangeInfo", timeout=30).json()["symbols"]
           if s["status"] == "TRADING" and s["quoteAsset"] == "USDT" and s["contractType"] == "PERPETUAL"}
    tk = sorted((t for t in requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=30).json()
                 if t["symbol"] in fut and t["symbol"] not in ESTAVEIS), key=lambda t: -float(t["quoteVolume"]))
    ia = {}
    try:
        ia = json.load(open(os.path.join(D, "ia_pura.json"), encoding="utf-8"))
    except Exception:
        pass
    moedas = list(dict.fromkeys(list(ia.get("posicoes", {})) + [t["symbol"] for t in tk[:30]]))[:32]
    rel = {}
    try:
        rel = json.load(open(os.path.join(D, "relatorio_aranha.json"), encoding="utf-8"))
    except Exception:
        pass
    fg = None
    try:
        fg = float(requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()["data"][0]["value"])
    except Exception:
        pass
    extra = {"noticias": rel.get("noticias", []), "fg": fg}
    precos0 = {t["symbol"]: float(t["lastPrice"]) for t in tk}
    hist0, _ = confere_placar(antigo, precos0)
    aprende(hist0)
    antigo["historico"] = hist0
    with ThreadPoolExecutor(max_workers=8) as ex:
        analises = list(ex.map(analista, [(i, s, extra) for i, s in enumerate(moedas)]))
    precos = {a["simbolo"]: a.get("preco") for a in analises if a.get("preco")}
    hist, placar = confere_placar(antigo, precos)
    for a in analises:
        if not a.get("erro"):
            hist.append({k: a[k] for k in ("simbolo", "decisao", "confianca", "cerebro", "preco", "quando")} | {"resultado": None})
    # comitê: ranking por valor esperado do lado escolhido
    for a in analises:
        a["ev_escolhido"] = (a.get("valor_esperado_compra") if a["decisao"] == "COMPRA" else a.get("valor_esperado_venda") if a["decisao"] == "VENDA" else 0) or 0
    SIS_COMITE = """Você é o COMITÊ DE RISCO (o cérebro mais forte do prédio). Um analista deu um veredito para uma moeda.
Confira os números com frieza. Só APROVE se a tendência de 4h e o valor esperado do lado escolhido concordarem com o veredito.
Responda SÓ JSON: {"aprova":true,"motivo":"uma frase curta em português do Brasil"}"""
    cand = sorted([a for a in analises if a["decisao"] != "FORA" and not a.get("erro")], key=lambda a: -(a["ev_escolhido"] * a["confianca"]))[:8]
    def comite(a):
        nome, t = pergunta(SIS_COMITE, json.dumps({k: a.get(k) for k in ("moeda", "decisao", "confianca", "motivo", "tendencia_4h", "valor_esperado_compra", "valor_esperado_venda", "chance_alvo_compra", "chance_alvo_venda", "financiamento_pct", "noticias")}, ensure_ascii=False), "comite")
        j = json_de(t) or {}
        a["comite"] = {"aprova": bool(j.get("aprova")), "motivo": str(j.get("motivo", ""))[:200], "cerebro": nome}
    with ThreadPoolExecutor(max_workers=3) as ex2:
        list(ex2.map(comite, cand))
    for a in analises:
        if a["decisao"] != "FORA" and not (a.get("comite") or {}).get("aprova"):
            a["vetado"] = True
    ranking = sorted([a for a in analises if a["decisao"] != "FORA" and not a.get("vetado")], key=lambda a: -(a["ev_escolhido"] * a["confianca"]))
    log = []
    if "--sem-diretoria" not in os.sys.argv:
        diretoria(analises, log)
    out = {"gerado": datetime.now(timezone.utc).isoformat()[:16], "segundos": round(time.time() - inicio),
           "cerebros": {n: {"papel": c["papeis"][0], "limite_dia": c["por_dia"], "usados_hoje": _cota.get(n, {}).get("n", 0)} for n, c in CEREBROS.items()}, "andares": {
               "terreo": {"nome": "ARANHA", "trabalho": "notícias do mundo", "noticias": len(rel.get("noticias", []))},
               "andar1": {"nome": "ANALISTAS DE MOEDA", "trabalho": "um analista por moeda", "analistas": analises},
               "andar2": {"nome": "COMITÊ DE RISCO", "trabalho": "ranking por valor esperado", "ranking": [a["simbolo"] for a in ranking[:10]]},
               "andar3": {"nome": "DIRETORIA", "trabalho": "abre o próximo trade da IA pura", "log": log}},
           "placar": placar, "historico": hist,
           "aprendizado": {"pesos": {n: round(v, 3) for n, v in PESO.items()}, "banidos": sorted(BANIDOS),
                           "moedas_com_historico": len(HIST_MOEDA),
                           "regras": ["cérebro que acerta mais analisa mais moedas (peso = acertos+1 / vereditos+2)",
                                      "cérebro com menos de 45% de acerto depois de 30 vereditos sai da função de analista",
                                      "cada analista recebe o histórico de acertos e erros da própria moeda e o próprio acerto",
                                      "diretoria: 2 perdas nos últimos fechamentos -> modo cauteloso (mais exigente e arrisca 60%)"]}}
    salva_cota()
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    comp = sum(a["decisao"] == "COMPRA" for a in analises); ven = sum(a["decisao"] == "VENDA" for a in analises)
    print(f"PRÉDIO {len(analises)} analistas em {out['segundos']}s | {comp} compra, {ven} venda, {len(analises) - comp - ven} fora | cérebros: {', '.join(f'{n} {v["usados_hoje"]}/{v["limite_dia"]}' for n, v in out['cerebros'].items()) or 'nenhum'}")
    for l in log:
        print(" ", l)


if __name__ == "__main__":
    if "--so-diretoria" in os.sys.argv:   # roda só a diretoria em cima da última análise (o motor chama na sequência)
        an = json.load(open(SAIDA, encoding="utf-8"))
        log = []; diretoria(an["andares"]["andar1"]["analistas"], log)
        an["andares"]["andar3"]["log"] = log + an["andares"]["andar3"].get("log", [])[:20]
        json.dump(an, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("DIRETORIA:", " | ".join(log) or "nada a fazer")
    else:
        main()
