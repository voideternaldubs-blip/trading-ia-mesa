"""ESTUDO DE IMPACTO DAS NOTÍCIAS: cada evento grava o preço quando foi visto e, depois, o retorno em 4h, 1d, 5d e 20d,
comparado com o mercado (retorno anormal). Em 2-3 meses: dados próprios de quais notícias realmente movem preço.
Tabela 'impacto' dentro de data/aranha.db (vai junto para a nuvem)."""
import os, sqlite3, time, requests
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(RAIZ, "data", "aranha.db")
UA = {"User-Agent": "Mozilla/5.0"}
# ativo da aranha -> (fonte, símbolo, referência de mercado)
MAPA = {"BTC": ("bn", "BTCUSDT", None), "ETH": ("bn", "ETHUSDT", "BTCUSDT"), "SOL": ("bn", "SOLUSDT", "BTCUSDT"), "XRP": ("bn", "XRPUSDT", "BTCUSDT"),
        "DOGE": ("bn", "DOGEUSDT", "BTCUSDT"), "BNB": ("bn", "BNBUSDT", "BTCUSDT"), "ADA": ("bn", "ADAUSDT", "BTCUSDT"), "AVAX": ("bn", "AVAXUSDT", "BTCUSDT"),
        "LINK": ("bn", "LINKUSDT", "BTCUSDT"), "SUI": ("bn", "SUIUSDT", "BTCUSDT"),
        "NVDA": ("yh", "NVDA", "SPY"), "AAPL": ("yh", "AAPL", "SPY"), "MSFT": ("yh", "MSFT", "SPY"), "TSLA": ("yh", "TSLA", "SPY"), "AMD": ("yh", "AMD", "SPY"),
        "META": ("yh", "META", "SPY"), "GOOGL": ("yh", "GOOGL", "SPY"), "AMZN": ("yh", "AMZN", "SPY"), "TSM": ("yh", "TSM", "SPY"),
        "NASDAQ": ("yh", "QQQ", "SPY"), "S&P500": ("yh", "SPY", None), "OURO": ("yh", "GLD", "SPY"), "PETRÓLEO": ("yh", "USO", "SPY"),
        "DÓLAR": ("yh", "UUP", None), "BRASIL": ("yh", "EWZ", "SPY"), "CHINA": ("yh", "FXI", "SPY"), "JAPÃO": ("yh", "EWJ", "SPY"),
        "EUROPA": ("yh", "VGK", "SPY"), "EURO/BCE": ("yh", "FXE", None), "FED": ("yh", "TLT", None), "GUERRA": ("yh", "SPY", None)}
HORIZ = {"4h": 4, "1d": 24, "5d": 120, "20d": 480}
_cache = {}


def serie(fonte, sym):
    """Preços de hora em hora dos últimos ~30 dias: lista de (timestamp_s, preço)."""
    if (fonte, sym) in _cache:
        return _cache[(fonte, sym)]
    pts = []
    try:
        if fonte == "bn":
            r = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": sym, "interval": "1h", "limit": 1000}, timeout=20).json()
            pts = [(int(k[0]) // 1000, float(k[4])) for k in r]
        else:
            j = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "1mo", "interval": "60m"}, headers=UA, timeout=20).json()["chart"]["result"][0]
            pts = [(t, c) for t, c in zip(j["timestamp"], j["indicators"]["quote"][0]["close"]) if c]
    except Exception as e:
        print("preço falhou", sym, e)
    _cache[(fonte, sym)] = pts
    return pts


def preco_em(pts, ts):
    """Último preço conhecido até o instante ts (nunca usa o futuro)."""
    ant = None
    for t, p in pts:
        if t > ts:
            break
        ant = p
    return ant


def main():
    c = sqlite3.connect(DB)
    c.execute("""create table if not exists impacto(noticia text, ativo text, simbolo text, ref text, visto_em text, tipo text, direcao text,
                 preco0 real, ref0 real, ret_4h real, ret_1d real, ret_5d real, ret_20d real,
                 abn_4h real, abn_1d real, abn_5d real, abn_20d real, primary key(noticia, ativo))""")
    # 1) eventos novos (últimas 48h) entram com o preço do momento em que foram vistos
    desde = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    novos = 0
    for link, quando, titulo, moedas, p, fo in c.execute("select link, quando, titulo, moedas, perigo, forca from noticias where quando>=? and moedas!=''", (desde,)).fetchall():
        for a in filter(None, moedas.split(",")):
            if a not in MAPA or c.execute("select 1 from impacto where noticia=? and ativo=?", (link, a)).fetchone():
                continue
            fonte, sym, ref = MAPA[a]
            ts = int(datetime.fromisoformat(quando).timestamp())
            p0 = preco_em(serie(fonte, sym), ts)
            r0 = preco_em(serie("bn" if ref and ref.endswith("USDT") else "yh", ref), ts) if ref else None
            if not p0:
                continue
            direcao = "baixa" if p else ("alta" if fo else "neutra")
            c.execute("insert into impacto(noticia, ativo, simbolo, ref, visto_em, tipo, direcao, preco0, ref0) values(?,?,?,?,?,?,?,?,?)",
                      (link, a, sym, ref, quando, "", direcao, p0, r0))
            novos += 1
    # 2) completa os horizontes que já passaram
    completos = 0
    for noticia, a, sym, ref, visto, p0, r0, *rets in c.execute(
            "select noticia, ativo, simbolo, ref, visto_em, preco0, ref0, ret_4h, ret_1d, ret_5d, ret_20d from impacto where ret_20d is null").fetchall():
        fonte = MAPA.get(a, ("yh",))[0]
        ts0 = int(datetime.fromisoformat(visto).timestamp())
        upd = {}
        for (nome, h), atual in zip(HORIZ.items(), rets):
            if atual is not None or time.time() < ts0 + h * 3600:
                continue
            p1 = preco_em(serie(fonte, sym), ts0 + h * 3600)
            if not p1:
                continue
            r = p1 / p0 - 1
            upd["ret_" + nome] = r
            if ref and r0:
                q1 = preco_em(serie("bn" if ref.endswith("USDT") else "yh", ref), ts0 + h * 3600)
                if q1:
                    upd["abn_" + nome] = r - (q1 / r0 - 1)
        if upd:
            c.execute("update impacto set " + ", ".join(f"{k}=?" for k in upd) + " where noticia=? and ativo=?", (*upd.values(), noticia, a))
            completos += 1
    c.commit()
    tot = c.execute("select count(*), sum(ret_1d is not null), sum(ret_5d is not null) from impacto").fetchone()
    print(f"IMPACTO: +{novos} eventos novos | {completos} atualizados | total {tot[0]} (com 1 dia: {tot[1] or 0}, com 5 dias: {tot[2] or 0})")
    c.close()


if __name__ == "__main__":
    main()
