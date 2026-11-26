"""EXECUTOR BINANCE DEMO (futuros USDT-M, dinheiro de teste). Chaves em data/binance_demo.env (fora do git).
URL fixa no ambiente DEMO: nunca toca conta real."""
import os, time, hmac, hashlib, json, math, urllib.parse, requests

AQUI = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(AQUI, "data", "binance_demo.env")
EXEC = os.path.join(AQUI, "data", "foguete2_exec.json")
BASE = "https://demo-fapi.binance.com"  # SÓ demo
_filtros = {}


def chaves():
    if not os.path.exists(ENV):
        return None
    return dict(l.strip().split("=", 1) for l in open(ENV, encoding="utf-8") if "=" in l)


def _req(metodo, caminho, assinado=True, **p):
    k = chaves()
    h = {"X-MBX-APIKEY": k["BINANCE_KEY"]} if k else {}
    if assinado:
        p.update(timestamp=int(time.time() * 1000), recvWindow=10000)
        q = urllib.parse.urlencode(p)
        p["signature"] = hmac.new(k["BINANCE_SECRET"].encode(), q.encode(), hashlib.sha256).hexdigest()
    r = requests.request(metodo, BASE + caminho, params=p, headers=h, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"Binance demo {r.status_code}: {r.text[:200]}")
    return r.json()


def filtros(sym):
    if not _filtros:
        for s in _req("GET", "/fapi/v1/exchangeInfo", assinado=False)["symbols"]:
            f = {x["filterType"]: x for x in s["filters"]}
            _filtros[s["symbol"]] = {"step": float(f["MARKET_LOT_SIZE"]["stepSize"]), "minq": float(f["MARKET_LOT_SIZE"]["minQty"]),
                                     "min": float(f.get("MIN_NOTIONAL", {}).get("notional", 5))}
    return _filtros.get(sym)


def conta():
    a = _req("GET", "/fapi/v2/account")
    return {"saldo": float(a["totalWalletBalance"]), "pnl_aberto": float(a["totalUnrealizedProfit"]), "disponivel": float(a["availableBalance"])}


def posicoes():
    return {p["symbol"]: float(p["positionAmt"]) for p in _req("GET", "/fapi/v2/positionRisk") if float(p["positionAmt"]) != 0}


def ordem(sym, qtd_com_sinal, reduz=False):
    f = filtros(sym)
    if not f:
        return None
    q = math.floor(abs(qtd_com_sinal) / f["step"]) * f["step"]
    if q < f["minq"]:
        return None
    casas = max(0, -int(round(math.log10(f["step"])))) if f["step"] < 1 else 0
    p = dict(symbol=sym, side="BUY" if qtd_com_sinal > 0 else "SELL", type="MARKET", quantity=f"{q:.{casas}f}", newOrderRespType="RESULT")
    if reduz:
        p["reduceOnly"] = "true"
    return _req("POST", "/fapi/v1/order", **p)


def sincroniza(alvo):
    """alvo = {SIMBOLO: quantidade com sinal}. Leva a conta demo até o alvo do foguete. Devolve o registro das execuções."""
    if not chaves():
        return []
    atuais, feitos = posicoes(), []
    for sym in set(atuais) | set(alvo):
        a, cur = alvo.get(sym, 0.0), atuais.get(sym, 0.0)
        dif = a - cur
        f = filtros(sym)
        if not f or abs(dif) < f["minq"]:
            continue
        try:
            if sym not in atuais or (cur != 0 and math.copysign(1, a) != math.copysign(1, cur) if a else False):
                _req("POST", "/fapi/v1/leverage", symbol=sym, leverage=20)
            reduz = abs(a) < abs(cur) and (a == 0 or math.copysign(1, a) == math.copysign(1, cur))
            r = ordem(sym, dif, reduz)
            if r:
                feitos.append({"quando": time.strftime("%Y-%m-%dT%H:%M", time.gmtime()), "simbolo": sym, "lado": r["side"], "qtd": float(r["executedQty"]),
                               "preco": float(r.get("avgPrice") or 0), "status": r["status"], "id": r["orderId"]})
        except Exception as ex:
            feitos.append({"quando": time.strftime("%Y-%m-%dT%H:%M", time.gmtime()), "simbolo": sym, "erro": str(ex)[:160]})
        time.sleep(0.1)
    hist = json.load(open(EXEC, encoding="utf-8")) if os.path.exists(EXEC) else []
    json.dump((hist + feitos)[-2000:], open(EXEC, "w", encoding="utf-8"), indent=1)
    return feitos


if __name__ == "__main__":
    print(conta()); print(posicoes())
