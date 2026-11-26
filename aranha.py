"""ARANHA: varre notícias e dados do mercado e guarda tudo em data/aranha.db."""
import os, re, json, sqlite3, time, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(AQUI, "data", "aranha.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
MOEDAS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "ADA", "SUI"]
NOMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "bnb|binance coin", "XRP": "xrp|ripple",
         "DOGE": "dogecoin|doge", "AVAX": "avalanche|avax", "LINK": "chainlink", "ADA": "cardano", "SUI": r"\bsui\b"}
GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
FEEDS = [
    # agências e mercado global (paywall: só título + link)
    "https://feeds.bloomberg.com/markets/news.rss", GN + "site:reuters.com+markets+when:1d", GN + "site:apnews.com+business+when:1d",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "https://www.ft.com/markets?format=rss", "https://www.economist.com/finance-and-economics/rss.xml",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://feeds.bbci.co.uk/news/business/rss.xml", GN + "site:finance.yahoo.com+when:1d", GN + "site:asia.nikkei.com+markets+when:1d",
    # comunicados oficiais de empresas (fonte primária)
    "https://www.prnewswire.com/rss/news-releases-list.rss", GN + "site:businesswire.com+when:1d",
    GN + "site:globenewswire.com+when:1d",
    # bancos centrais e reguladores (fonte primária)
    "https://www.federalreserve.gov/feeds/press_all.xml", "https://www.ecb.europa.eu/rss/press.html", "https://www.sec.gov/news/pressreleases.rss",
    # cripto
    "https://www.coindesk.com/arc/outboundfeeds/rss/", "https://www.theblock.co/rss.xml", "https://cointelegraph.com/rss", "https://decrypt.co/feed",
    # Brasil
    "https://pox.globo.com/rss/valor/", "https://www.infomoney.com.br/feed/",
    # temas (Google News)
    GN + "crypto+OR+bitcoin+when:1d", GN + "nvidia+OR+nasdaq+OR+%22stock+market%22+when:1d", GN + "stocks+earnings+OR+fed+OR+tariffs+when:1d",
    GN + "oil+OR+gold+OR+dollar+OR+yuan+OR+euro+markets+when:1d", GN + "war+OR+sanctions+OR+election+markets+when:1d",
]
PAYWALL = ("bloomberg.com", "reuters.com", "wsj.com", "a.dj.com", "ft.com", "economist.com", "dowjones.io")
PRIMARIA = ("federalreserve.gov", "ecb.europa.eu", "sec.gov", "prnewswire.com", "globenewswire.com", "businesswire.com", "binance.com")
ACOES = {"NVDA": r"nvidia|jensen huang|nvda", "NASDAQ": r"nasdaq|tech stocks", "S&P500": r"s&p 500|s&p500|spy|wall street|stock market|dow jones",
         "TSLA": r"tesla|tsla", "AAPL": r"apple|aapl", "MSFT": r"microsoft|msft", "AMD": r"amd", "TSM": r"tsmc|taiwan semiconductor",
         "META": r"meta", "GOOGL": r"google|alphabet", "AMZN": r"amazon", "FED": r"fed|federal reserve|powell|interest rate|rate cut|inflation",
         "PETRÓLEO": r"oil|crude|opec|brent", "OURO": r"gold|bullion", "DÓLAR": r"dollar|usd|greenback", "EURO/BCE": r"euro|ecb|lagarde|eurozone",
         "CHINA": r"china|chinese|yuan|beijing|pboc|xi jinping", "JAPÃO": r"japan|yen|nikkei|bank of japan|boj", "EUROPA": r"europe|eu|germany|france|uk|britain|ftse|dax",
         "BRASIL": r"brazil|ibovespa|petrobras|vale|selic|lula|real brasileiro", "GUERRA": r"war|military|missile|attack on|ukraine|russia|israel|iran|gaza|taiwan strait",
         "TRUMP/EUA": r"trump|white house|congress|treasury secretary"}
# palavras de perigo (agente RUG/RISCO) e de força
PERIGO = r"hack|exploit|drain|stolen|rug ?pull|delist|lawsuit|sec sues|charged|insolv|bankrupt|halt(ed)? withdrawals|depeg|outage|attack"
FORCA = r"etf approv|approved|partnership|listing on|lists|record high|all-time high|inflows|upgrade live|mainnet launch|adopt"


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("create table if not exists noticias(link text primary key, quando text, fonte text, titulo text, moedas text, perigo int, forca int)")
    c.execute("create table if not exists mercado(quando text, tipo text, chave text, valor real)")
    cols = [x[1] for x in c.execute("pragma table_info(noticias)")]
    if "resumo" not in cols:
        c.execute("alter table noticias add column resumo text default ''")
    return c


def marcar(titulo):
    t = titulo.lower()
    moedas = [m for m, rx in {**NOMES, **ACOES}.items() if re.search(rx, t)]
    return moedas, int(bool(re.search(PERIGO, t))), int(bool(re.search(FORCA, t)))


def noticias(c):
    novas = 0
    from concurrent.futures import ThreadPoolExecutor
    def baixa(f):  # todas as fontes AO MESMO TEMPO (antes: uma por vez, 43 s)
        try:
            return f, ET.fromstring(requests.get(f, headers=UA, timeout=12).content)
        except Exception as e:
            print("feed falhou", f, str(e)[:80]); return f, None
    with ThreadPoolExecutor(max_workers=24) as ex:
        baixados = list(ex.map(baixa, FEEDS))
    for f, raiz in baixados:
        if raiz is None:
            continue
        for it in list(raiz.iter("item"))[:40]:
            tit, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
            resumo = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", it.findtext("description") or "")).strip()[:900]
            if "news.google" in f or any(p in f for p in PAYWALL):
                resumo = ""  # Google News repete o título; sites com paywall: só título + link (regra do dono)
            if not link:
                continue
            moedas, p, fo = marcar(tit)
            cur = c.execute("insert or ignore into noticias(link,quando,fonte,titulo,moedas,perigo,forca,resumo) values(?,?,?,?,?,?,?,?) on conflict(link) do update set resumo=excluded.resumo where noticias.resumo='' and excluded.resumo!=''",
                            (link, datetime.now(timezone.utc).isoformat(), f.split("/")[2], tit, ",".join(moedas), p, fo, resumo))
            novas += cur.rowcount
    try:
        arts = requests.get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query",
                            params={"type": 1, "catalogId": 48, "pageNo": 1, "pageSize": 15}, headers=UA, timeout=20).json()["data"]["catalogs"][0]["articles"]
        for a in arts:
            tit = a["title"]; link = f"https://www.binance.com/en/support/announcement/{a['code']}"
            moedas, p, fo = marcar(tit)
            cur = c.execute("insert or ignore into noticias(link,quando,fonte,titulo,moedas,perigo,forca,resumo) values(?,?,?,?,?,?,?,?)",
                            (link, datetime.now(timezone.utc).isoformat(), "binance.com", tit, ",".join(moedas), p, int(fo or "list" in tit.lower()), ""))
            novas += cur.rowcount
    except Exception as e:
        print("anúncios binance falharam", e)
    return novas


def mercado(c):
    agora = datetime.now(timezone.utc).isoformat()
    linhas = []
    try:
        f = requests.get("https://api.alternative.me/fng/?limit=1", timeout=15).json()["data"][0]
        linhas.append((agora, "medo_ganancia", "geral", float(f["value"])))
    except Exception as e:
        print("medo falhou", e)
    for m in MOEDAS:
        s = m + "USDT"
        try:
            p = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": s}, timeout=15).json()
            linhas.append((agora, "financiamento", m, float(p["lastFundingRate"])))
            r = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                             params={"symbol": s, "period": "4h", "limit": 1}, timeout=15).json()
            linhas.append((agora, "comprados_vendidos", m, float(r[-1]["longShortRatio"])))
            oi = requests.get("https://fapi.binance.com/futures/data/openInterestHist",
                              params={"symbol": s, "period": "4h", "limit": 2}, timeout=15).json()
            if len(oi) == 2:
                linhas.append((agora, "contratos_var", m, float(oi[-1]["sumOpenInterestValue"]) / float(oi[0]["sumOpenInterestValue"]) - 1))
        except Exception as e:
            print("binance falhou", m, e)
        time.sleep(0.1)
    try:
        tr = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=15).json()["coins"]
        for i, x in enumerate(tr[:15]):
            linhas.append((agora, "em_alta", x["item"]["symbol"].upper(), float(i + 1)))
    except Exception as e:
        print("coingecko falhou", e)
    c.executemany("insert into mercado values(?,?,?,?)", linhas)
    return len(linhas)


def resumo(c, horas=12):
    """O que a aranha viu nas últimas N horas, por moeda."""
    desde = datetime.fromtimestamp(time.time() - horas * 3600, timezone.utc).isoformat()
    out = {m: {"perigo": [], "forca": []} for m in MOEDAS}
    for tit, ms, p, fo in c.execute("select titulo, moedas, perigo, forca from noticias where quando>=?", (desde,)):
        for m in filter(lambda x: x in out, ms.split(",")):
            if p: out[m]["perigo"].append(tit)
            if fo: out[m]["forca"].append(tit)
    ult = {}
    for tipo, chave, valor in c.execute("select tipo, chave, valor from mercado where quando=(select max(quando) from mercado)"):
        ult.setdefault(tipo, {})[chave] = valor
    return out, ult


if __name__ == "__main__":
    c = db()
    print("notícias novas:", noticias(c), "| dados de mercado:", mercado(c))
    c.commit()
    out, ult = resumo(c)
    for m, v in out.items():
        if v["perigo"] or v["forca"]:
            print(m, json.dumps(v, ensure_ascii=False)[:300])
    print("medo/ganância:", ult.get("medo_ganancia"), "| em alta:", list(ult.get("em_alta", {}))[:8])
