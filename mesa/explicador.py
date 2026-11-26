"""EXPLICADOR DA ARANHA: traduz as notícias, classifica o evento e explica em português simples.
Gera data/relatorio_aranha.json (lido pela página /aranha.html)."""
import os, re, json, sqlite3, time, requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(RAIZ, "data", "aranha.db")
SAIDA = os.path.join(RAIZ, "data", "relatorio_aranha.json")

# ---------------- tipos de evento (lista fechada) ----------------
TIPOS = [
    ("ATAQUE / ROUBO", r"hack|exploit|drain|stolen|attack|breach|scam|rug", "#ff4d6d",
     "Alguém roubou ou atacou uma plataforma, carteira ou rede. Quando isso acontece, quem tem dinheiro ali costuma vender com medo e o preço da moeda envolvida cai.",
     "O agente RUG/RISCO bloqueia compras novas na moeda citada até a poeira baixar."),
    ("JUSTIÇA / REGULAÇÃO", r"\bsec\b|lawsuit|sues|charged|settle|court|regulat|\bban\b|\bbans\b|probe|investigat|congress|senate|bill", "#ffb02e",
     "Governo, tribunal ou órgão regulador (como a SEC, a 'CVM' dos EUA) mexeu no assunto. Isso cria incerteza: o mercado não gosta de não saber as regras.",
     "Conta como alerta de risco: a mesa fica mais cautelosa com o ativo citado."),
    ("TARIFAS / GUERRA COMERCIAL", r"tariff|trade war|export control|sanction", "#ff7aa8",
     "Os EUA (ou outro país) estão taxando produtos de fora ou proibindo vendas. Isso encarece coisas, assusta investidores e costuma derrubar ações de tecnologia e cripto no curto prazo.",
     "Notícia macro: afeta o mercado inteiro, não uma moeda só. O filtro de tendência percebe a queda e reduz a exposição."),
    ("GUERRA / GEOPOLÍTICA", r"war|military|missile|troops|ukraine|russia|israel|iran|gaza|taiwan|north korea|sanction|ceasefire|nato", "#ff4d6d",
     "Conflito ou tensão entre países. Guerra assusta o mercado: investidores fogem do risco (ações, cripto) e correm para proteção (ouro, dólar). Se envolve região de petróleo, o petróleo sobe.",
     "Notícia de risco global: a mesa reduz o apetite e espera o preço confirmar antes de agir."),
    ("PETRÓLEO / OURO / MATÉRIAS-PRIMAS", r"oil|crude|opec|brent|gold|bullion|copper|commodit|wheat|natural gas", "#ffb02e",
     "Preço de matérias-primas. Petróleo caro = gasolina e frete mais caros = inflação = juros altos por mais tempo. Ouro subindo = gente com medo, buscando proteção.",
     "Termômetro do medo e da inflação no mundo; afeta bolsas e cripto de forma indireta."),
    ("MOEDAS / CÂMBIO", r"dollar|yen|euro|yuan|currency|forex|exchange rate|real brasileiro|peso", "#2ee6ff",
     "Valor das moedas entre si. Dólar forte costuma pressionar ações, cripto e países emergentes (como o Brasil). Dólar fraco costuma ajudar.",
     "Ajuda a entender por que tudo sobe ou cai junto em certos dias."),
    ("BRASIL", r"brazil|ibovespa|petrobras|vale|selic|lula|b3", "#2bff9a",
     "Notícia da economia brasileira: Ibovespa (a bolsa daqui), Petrobras, Vale, Selic (juros do Brasil). Mexe com o real e com o seu bolso.",
     "Contexto: a mesa opera fora do Brasil, mas o câmbio muda quanto vale o seu lucro em reais."),
    ("JUROS / ECONOMIA", r"\bfed\b|federal reserve|powell|interest rate|rate cut|rate hike|inflation|cpi|jobs report|recession|treasury", "#9b7bff",
     "O Banco Central americano (Fed) controla os juros. Juros altos = dinheiro mais caro = menos gente comprando ações e cripto. Juros caindo costuma animar o mercado.",
     "Muda o 'clima' geral. A mesa não aposta na notícia; espera o preço confirmar a direção."),
    ("ETF / DINHEIRO GRANDE", r"\betf\b|inflow|outflow|blackrock|institution|fund|treasury company|buys \$|purchase", "#2ee6ff",
     "Dinheiro de grandes instituições entrando ou saindo (fundos, ETFs, empresas comprando bitcoin). Entrada de dinheiro grande costuma sustentar o preço; saída, pressionar.",
     "Sinal de força ou fraqueza que a mesa registra para medir depois se antecipa o preço."),
    ("RESULTADO DE EMPRESA", r"earnings|revenue|profit|quarter|guidance|beats|misses|forecast|sales", "#2bff9a",
     "A empresa mostrou quanto vendeu e lucrou. Se veio melhor que o esperado, a ação costuma subir; pior, cair. O que importa é a surpresa, não o número em si.",
     "Entra no estudo de eventos: medimos quanto a ação andou nas horas seguintes."),
    ("LIDERANÇA DA EMPRESA", r"\bceo\b|board|resign|reinstat|fired|steps down|founder|jensen huang|chief", "#ff2bd6",
     "Mudou (ou balançou) quem comanda a empresa. O mercado aposta muito nas pessoas: quando a Nvidia perdeu o Jensen Huang a ação caiu 30%; quando ele voltou, subiu 31% num dia.",
     "Evento raro e forte. A mesa não tenta adivinhar; o filtro de tendência só entra quando o preço confirma."),
    ("MOVIMENTO DE PREÇO", r"surge|soar|rall|jump|climb|gain|record|high|plunge|sink|fall|drop|crash|slump|tumble|slide|dip|rebound", "#5ab8ff",
     "A notícia é sobre o preço em si: subiu ou caiu forte. Notícia de preço vem DEPOIS do movimento, então sozinha não serve pra prever, mas mostra o humor do mercado.",
     "É exatamente o que o ANALISTA mede com números: rompimentos e tendência."),
]
GLOSSARIO = {
    "ETF": "Fundo vendido como uma ação. Você compra 1 cota e tem um pedaço de vários ativos (ex.: QQQ = as 100 maiores do Nasdaq). TQQQ é um ETF que anda 3x o Nasdaq: se o índice sobe 1%, ele sobe ~3% (e cai 3% também).",
    "Bitcoin": "A primeira e maior criptomoeda. Quando ela sobe ou cai, quase todas as outras vão junto.",
    "Comprado / Vendido": "Comprado = ganha se o preço SOBE. Vendido = ganha se o preço CAI (dá pra 'vender' sem ter, nos futuros). A mesa fica vendida quando a tendência é de queda.",
    "Alavancagem": "Operar com mais dinheiro do que você tem. 3x = ganha 3 vezes mais, mas também perde 3 vezes mais. É o que acelera e o que quebra contas.",
    "Stop": "Ordem de saída automática para limitar perda (stop loss) ou proteger lucro (stop móvel).",
    "Financiamento (funding)": "Taxa que quem está comprado paga para quem está vendido (ou o contrário) a cada 8h nos futuros de cripto. Muito alto = muita gente apostando na alta = mercado 'esticado'.",
    "Medo e Ganância": "Índice de 0 a 100 do humor do mercado cripto. Perto de 0 = pânico. Perto de 100 = euforia. Hoje está em medo extremo.",
    "Média de 200 dias": "O preço médio dos últimos 200 dias. Preço acima dela = tendência de alta; abaixo = de baixa. É o filtro do robô de ações.",
    "Rompimento": "Quando o preço passa da máxima (ou mínima) das últimas X velas. É o sinal do ANALISTA: rompeu pra cima, compra; pra baixo, vende.",
    "Vela (candle)": "Um pedaço do gráfico que mostra abertura, máxima, mínima e fechamento num período (4h, 1 dia...).",
    "Liquidez": "Quanto dinheiro tem disponível para comprar e vender sem mexer o preço. Pouca liquidez = é fácil ficar preso.",
    "Rug pull (puxar o tapete)": "Golpe em moeda nova: o criador tira o dinheiro da piscina de liquidez e a moeda vai a zero. É o que o agente RUG tenta barrar.",
    "SEC": "Órgão que fiscaliza o mercado financeiro dos EUA (parecido com a CVM no Brasil).",
    "Fed": "O Banco Central dos EUA. Decide os juros e mexe com todos os mercados do mundo.",
    "Nasdaq": "Bolsa americana cheia de empresas de tecnologia (Apple, Nvidia, Microsoft...). 'O Nasdaq subiu' = o índice dessas empresas subiu.",
    "S&P 500": "Índice com as 500 maiores empresas dos EUA. É o 'termômetro' da bolsa americana.",
    "Tarifa": "Imposto sobre produto importado. Guerra de tarifas assusta o mercado porque encarece tudo e reduz lucro das empresas.",
    "Volatilidade": "O quanto o preço chacoalha. Cripto e ETFs 3x são muito voláteis: sobem e caem forte.",
    "Backtest": "Testar uma estratégia no passado para ver se teria dado lucro, sem arriscar dinheiro. Só vale se for testado em dados que a estratégia nunca viu.",
    "Papel (paper trading)": "Operar com dinheiro de mentira e preço real. É onde a mesa está agora: prova se funciona antes de pôr dinheiro.",
    "Memecoin": "Moeda criada por piada/hype, sem produto. Pode subir 100x ou ir a zero em horas.",
    "Resultado trimestral": "Relatório que a empresa publica a cada 3 meses com vendas e lucro. Faz a ação pular para cima ou para baixo.",
    "CEO": "O chefe principal da empresa.",
    "Petróleo": "A matéria-prima mais importante do mundo. Se sobe, quase tudo fica mais caro (inflação). Quem decide boa parte da produção é a OPEP.",
    "Ouro": "O 'porto seguro'. Quando o mundo fica com medo (guerra, crise), muita gente compra ouro e o preço sobe.",
    "Dólar forte": "Quando o dólar sobe frente às outras moedas. Costuma derrubar ações, cripto e moedas de países como o Brasil.",
    "Banco Central": "Quem controla os juros de um país: Fed (EUA), BCE (Europa), Banco do Japão, Banco Central do Brasil (Selic). Juros mexem com todos os preços.",
    "Selic": "A taxa de juros básica do Brasil. Selic alta = renda fixa rende mais e a bolsa brasileira sofre.",
    "Ibovespa": "O índice da bolsa brasileira (B3), com as maiores empresas daqui, como Petrobras, Vale e bancos.",
    "Sanções": "Punições econômicas de um país contra outro (proibir comércio, congelar dinheiro). Podem mexer com petróleo, chips e mercados inteiros.",
    "Geopolítica": "A política entre países: guerras, alianças, eleições, disputas. O mercado reage porque muda o risco de tudo.",
}
TERMOS = {
    "ETF": r"\betf", "Bitcoin": r"bitcoin|\bbtc\b", "Alavancagem": r"leverag|alavanc", "Financiamento (funding)": r"funding",
    "Liquidez": r"liquidit", "Rug pull (puxar o tapete)": r"\brug", "SEC": r"\bsec\b", "Fed": r"\bfed\b|federal reserve|powell",
    "Nasdaq": r"nasdaq", "S&P 500": r"s&p", "Tarifa": r"tariff", "Volatilidade": r"volatil", "Memecoin": r"memecoin|meme coin",
    "Resultado trimestral": r"earnings|quarter", "CEO": r"\bceo\b", "Comprado / Vendido": r"short|long position|bear|bull",
}
ALTA = r"surge|soar|rall|jump|climb|gain|record|high|rebound|rise|beats|approv|inflow"
BAIXA = r"plunge|sink|fall|drop|crash|slump|tumble|slide|dip|lose|loss|outflow|misses|downgrade|warn|hack|lawsuit|tariff"

S = requests.Session()


def db():
    c = sqlite3.connect(DB)
    c.execute("create table if not exists traducoes(orig text primary key, pt text)")
    return c


def traduz(c, txt):
    if not txt:
        return ""
    r = c.execute("select pt from traducoes where orig=?", (txt,)).fetchone()
    if r:
        return r[0]
    try:
        j = S.get("https://translate.googleapis.com/translate_a/single",
                  params={"client": "gtx", "sl": "auto", "tl": "pt", "dt": "t", "q": txt}, timeout=15).json()
        pt = "".join(x[0] for x in j[0] if x[0])
    except Exception:
        return txt
    c.execute("insert or replace into traducoes values(?,?)", (txt, pt))
    time.sleep(0.15)
    return pt


def classifica(t):
    s = t.lower()
    for nome, rx, cor, sig, uso in TIPOS:
        if re.search(rx, s):
            return nome, cor, sig, uso
    return ("NOTÍCIA DE MERCADO", "#7d8196",
            "Notícia geral do mercado. Sozinha não muda nada, mas a aranha guarda tudo para medir depois quais tipos de notícia mexem no preço.",
            "Só registro: alimenta o estudo de impacto.")


def relatorio(limite=60):
    c = db()
    # as mais recentes de cada assunto, para a aranha ler de tudo (mundo, Brasil, ações, cripto)
    recentes = c.execute("select link, quando, fonte, titulo, moedas, perigo, forca, coalesce(resumo,'') from noticias "
                         "where moedas!='' order by quando desc, (resumo!='') desc limit 400").fetchall()
    por_assunto, linhas, vistos = {}, [], set()
    for r in recentes:
        por_assunto.setdefault(r[4].split(",")[0], []).append(r)
    while len(linhas) < limite and any(por_assunto.values()):
        for k in list(por_assunto):
            if por_assunto[k] and len(linhas) < limite:
                r = por_assunto[k].pop(0)
                if r[3] not in vistos:
                    vistos.add(r[3]); linhas.append(r)
    out = []
    for link, quando, fonte, tit, ms, p, fo, resumo in linhas:
        tit_limpo = re.sub(r"\s+-\s+[^-]{2,40}$", "", tit)  # tira " - Yahoo Finance"
        tipo, cor, sig, uso = classifica(tit + " " + resumo)
        base = (tit + " " + resumo).lower()
        direcao = "alta" if re.search(ALTA, base) and not re.search(BAIXA, base) else "baixa" if re.search(BAIXA, base) else "neutra"
        termos = [k for k, rx in TERMOS.items() if re.search(rx, base)]
        out.append({"id": link, "quando": quando[:16].replace("T", " "), "fonte": fonte.replace("www.", ""),
                    "titulo_en": tit_limpo, "titulo": traduz(c, tit_limpo), "resumo": traduz(c, resumo[:700]),
                    "ativos": [a for a in ms.split(",") if a], "tipo": tipo, "cor": cor, "significa": sig, "mesa_usa": uso,
                    "direcao": direcao, "perigo": p, "forca": fo, "termos": termos})
    c.commit()
    # resumo do humor do mercado
    contagem = {}
    for n in out:
        contagem[n["tipo"]] = contagem.get(n["tipo"], 0) + 1
    ativos = {}
    for n in out:
        for a in n["ativos"]:
            d = ativos.setdefault(a, {"alta": 0, "baixa": 0, "neutra": 0})
            d[n["direcao"]] += 1
    rel = {"gerado": time.strftime("%Y-%m-%d %H:%M"), "noticias": out, "tipos": contagem, "ativos": ativos, "glossario": GLOSSARIO}
    json.dump(rel, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False)
    return rel


if __name__ == "__main__":
    r = relatorio()
    print(len(r["noticias"]), "notícias explicadas |", r["tipos"])
    for n in r["noticias"][:3]:
        print("-", n["tipo"], "|", n["titulo"], "|", n["ativos"], "|", n["resumo"][:120])
