"""EXECUTOR ALPACA (conta PAPER). Lê as chaves de trading-ia/data/alpaca.env:
    ALPACA_KEY=...
    ALPACA_SECRET=...
Nunca aponta para a conta real: a URL é fixa no ambiente de papel."""
import os, requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(RAIZ, "data", "alpaca.env")
BASE = "https://paper-api.alpaca.markets/v2"  # SÓ papel
DADOS = "https://data.alpaca.markets/v2"


def chaves():
    if not os.path.exists(ENV):
        return None
    kv = dict(l.strip().split("=", 1) for l in open(ENV, encoding="utf-8") if "=" in l)
    return {"APCA-API-KEY-ID": kv.get("ALPACA_KEY", ""), "APCA-API-SECRET-KEY": kv.get("ALPACA_SECRET", "")}


def _req(metodo, caminho, **kw):
    h = chaves()
    if not h:
        raise RuntimeError("sem chaves em data/alpaca.env")
    r = requests.request(metodo, BASE + caminho, headers=h, timeout=20, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Alpaca {r.status_code}: {r.text[:200]}")
    return r.json() if r.text else {}


def conta():
    return _req("GET", "/account")


def posicoes():
    return {p["symbol"]: float(p["market_value"]) for p in _req("GET", "/positions")}


def relogio():
    return _req("GET", "/clock")


def ordem_valor(simbolo, usd):
    """Compra (usd>0) ou vende (usd<0) um valor em dólares, com fração de ação."""
    lado = "buy" if usd > 0 else "sell"
    return _req("POST", "/orders", json={"symbol": simbolo, "notional": f"{abs(usd):.2f}", "side": lado,
                                           "type": "market", "time_in_force": "day"})


def zera(simbolo):
    return _req("DELETE", f"/positions/{simbolo}")


if __name__ == "__main__":
    c = conta()
    print("conta", c["account_number"], "| status", c["status"], "| caixa", c["cash"], "| fração", c.get("fractional_trading"))
    print("mercado aberto?", relogio()["is_open"], "| posições", posicoes())
