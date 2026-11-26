"""MESA DE AGENTES — servidor local do painel vivo (http://localhost:8787).
Lê o que os agentes fizeram de verdade (diário, carteiras, aranha) e entrega em /api/estado."""
import os, sys, json, glob, re, sqlite3, time, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import central  # noqa: E402
import aranha  # noqa: E402
import explicador  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA = 8787

AGENTES = {
    "CHEFE": "Decide, junta tudo e fecha o placar",
    "ARANHA": "Varre notícias e dados do mercado",
    "ANALISTA": "Sinais de tendência testados",
    "VET": "Filtra moedas novas (liquidez, compradores)",
    "RUG": "Detector de golpe",
    "SNIPER": "Executa as entradas",
    "SAÍDA": "Stops, alvos e realização",
    "RISCO": "Tamanho, alavancagem e vetos",
}


def agente_do_evento(t):
    s = t.lower()
    if s.startswith("posições") or "posições:" in s: return "RISCO"
    if "→ posição" in s: return "SAÍDA" if "zerada" in s else "SNIPER"
    if "barrada" in s or "golpe" in s or "tapete" in s: return "RUG"
    if "veto" in s: return "RISCO"
    if "stop" in s or "venda" in s or "vendeu" in s or "vende " in s or "sumiu" in s or "tempo" in s: return "SAÍDA"
    if "compra" in s: return "SNIPER"
    if "carteira" in s or "chefe" in s or "desligado" in s: return "CHEFE"
    if "mantém" in s or "média 200" in s: return "ANALISTA"
    return "ARANHA"


def eventos(limite=60):
    out = []
    for f in glob.glob(os.path.join(RAIZ, "diario", "*.md")):
        mesa = "memecoin" if "meme_" in f else "ações" if "acoes_" in f else "cripto"
        dia = re.findall(r"\d{4}-\d{2}-\d{2}", f)
        dia = dia[0] if dia else ""
        hora = ""
        for linha in open(f, encoding="utf-8"):
            linha = linha.strip()
            if linha.startswith("## "):
                m = re.search(r"(\d{2}:\d{2})", linha)
                hora = m.group(1) if m else ""
                d2 = re.search(r"\d{4}-\d{2}-\d{2}", linha)
                if d2: dia = d2.group(0)
            elif linha.startswith("- "):
                txt = re.sub(r"\*\*", "", linha[2:])
                out.append({"quando": f"{dia} {hora}".strip(), "mesa": mesa, "agente": agente_do_evento(txt), "texto": txt[:160]})
    out.sort(key=lambda e: e["quando"])
    return out[-limite:]


def teia():
    """Notícias recentes ligadas às moedas que elas citam (a teia da aranha)."""
    db = os.path.join(RAIZ, "data", "aranha.db")
    nos, lig, mercado = [], [], {}
    if not os.path.exists(db):
        return {"noticias": nos, "ligacoes": lig, "mercado": mercado, "total_noticias": 0}
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    total = c.execute("select count(*) from noticias").fetchone()[0]
    for tit, ms, p, fo, fonte in c.execute("select titulo, moedas, perigo, forca, fonte from noticias where moedas!='' order by quando desc limit 40"):
        i = len(nos)
        nos.append({"titulo": tit[:110], "perigo": p, "forca": fo, "fonte": fonte})
        for m in filter(None, ms.split(",")):
            lig.append([i, m])
    for tipo, chave, valor in c.execute("select tipo, chave, valor from mercado where quando=(select max(quando) from mercado)"):
        mercado.setdefault(tipo, {})[chave] = valor
    c.close()  # solta o arquivo (no Windows, conexão aberta trava o git)
    return {"noticias": nos, "ligacoes": lig, "mercado": mercado, "total_noticias": total}


def estado():
    ms = central.mesas()
    ev = eventos()
    cont = {a: sum(1 for e in ev if e["agente"] == a) for a in AGENTES}
    ultimo = {}
    for e in ev:
        ultimo[e["agente"]] = e["texto"]
    t = teia()
    cont["ARANHA"] = t["total_noticias"]
    return {
        "agora": datetime.now(timezone.utc).isoformat(),
        "mesas": ms,
        "total": round(sum(m["valor"] for m in ms), 2),
        "base": 100 * len(ms),
        "agentes": [{"nome": a, "papel": p, "acoes": cont.get(a, 0), "ultimo": ultimo.get(a, "aguardando...")} for a, p in AGENTES.items()],
        "eventos": ev,
        "teia": t,
    }


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=AQUI, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/estado"):
            b = json.dumps(estado(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path.startswith("/api/aranha"):
            f = os.path.join(RAIZ, "data", "relatorio_aranha.json")
            b = open(f, "rb").read() if os.path.exists(f) else b'{"noticias":[]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()


def ciclo_aranha():
    """A aranha e os robôs rodam 24h na nuvem (GitHub Actions). Aqui o PC só puxa os resultados."""
    import subprocess
    while True:
        try:
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
            subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=RAIZ, timeout=90, env=env)
            # só os DADOS que a nuvem produz; o código local nunca é tocado
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "data/aranha.db", "data/carteira.json", "data/relatorio_aranha.json",
                            "data/calendario.json", "data/sec.json", "data/fills.json", "data/sentinela.json",
                            "acoes/carteira_acoes.json", "diario"], cwd=RAIZ, timeout=60, env=env, capture_output=True)
            subprocess.run(["git", "reset", "-q", "--", "data", "acoes/carteira_acoes.json", "diario"], cwd=RAIZ, timeout=30, env=env, capture_output=True)
        except Exception as e:
            print("sync:", e)
        time.sleep(10 * 60)


if __name__ == "__main__":
    threading.Thread(target=ciclo_aranha, daemon=True).start()
    print(f"Mesa de agentes em http://localhost:{PORTA}")
    ThreadingHTTPServer(("127.0.0.1", PORTA), H).serve_forever()
