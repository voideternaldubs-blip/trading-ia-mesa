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
    "PREVISÃO": "Máquina do tempo: 10.000 futuros por posição",
    "CARTEIRA": "Carteira do Prédio: 100 -> meta 1000",
    "SNIPER": "Executa as entradas",
    "SAÍDA": "Stops, alvos e realização",
    "RISCO": "Tamanho, alavancagem e vetos",
    "CALENDÁRIO": "Agenda do Fed, inflação e balanços",
    "SEC": "Documentos oficiais e compras de diretores",
    "FILLS": "Confere cada execução",
    "SENTINELA": "Vigia se todos estão trabalhando",
}


def ler_json(nome):
    try:
        return json.load(open(os.path.join(RAIZ, "data", nome), encoding="utf-8"))
    except Exception:
        return {}


def equipe_extra():
    k, s, f, v = ler_json("calendario.json"), ler_json("sec.json"), ler_json("fills.json"), ler_json("sentinela.json")
    docs = s.get("documentos", [])
    prox = [e for e in k.get("eventos", []) if e.get("quando", "") >= datetime.now(timezone.utc).isoformat()[:16]]
    ia, pb, fg, rel = ler_json("carteira_predio.json"), ler_json("probabilidades.json"), ler_json("foguete2.json"), ler_json("relatorio_aranha.json")
    ip = ia.get("posicoes", {}); valor = (ia.get("hist") or [{}])[-1].get("valor", 100)
    pp = pb.get("posicoes", {})
    fpos = fg.get("posicoes", {}); vend = sum(1 for p in fpos.values() if p.get("lado", 0) < 0)
    nots = rel.get("noticias", [])
    vivo = {
        "CARTEIRA": (len(ia.get("fechadas", [])) + len(ip), f"{valor:.2f} USD ({valor - 100:+.2f}) · meta 1000 · " + (", ".join(f"{s.replace('USDT', '')} {'vendido' if p['lado'] < 0 else 'comprado'}" for s, p in ip.items()) or "sem posição: a diretoria decide na próxima reunião")),
        "PREVISÃO": (len(pp), " · ".join(f"{s.replace('USDT', '')} alvo {v['chance_alvo'] * 100:.0f}%" for s, v in pp.items()) or "calculando..."),
        "ANALISTA": (len(fpos), f"tendência: {vend} vendidas, {len(fpos) - vend} compradas no foguete"),
        "RISCO": (len(ip), f"IA arrisca {sum(abs(p['qtd'] * (p['stop'] - p['entrada'])) for p in ip.values()):.0f} USD p/ ganhar {sum(abs(p['qtd'] * (p['entrada'] - p['alvo'])) for p in ip.values()):.0f}" if ip else "sem risco aberto"),
        "SAÍDA": (len(ip), " · ".join(f"{s.replace('USDT', '')} stop {p['stop']:g} alvo {p['alvo']:g}" for s, p in ip.items()) or "sem posições"),
        "ARANHA": (len(nots), (nots[0].get("titulo_pt") or nots[0].get("titulo", ""))[:110] if nots else "varrendo..."),
    }
    return {**vivo,
        "CALENDÁRIO": (len(k.get("eventos", [])), (prox[0]["nome"] + " · " + prox[0]["quando"].replace("T", " ")) if prox else k.get("aviso", "aguardando...")),
        "SEC": (len(docs), next((d.get("sinal") for d in docs if d.get("sinal")), f"{len(docs)} documentos lidos")),
        "FILLS": (len(f.get("execucoes", [])), f"escorregão médio {f.get('escorregao_medio_pct')}%" if f.get("execucoes") else "conferindo execuções"),
        "SENTINELA": (len(v.get("checks", [])), v.get("resumo", "aguardando...")),
    }, {"calendario": k, "sec": s, "fills": f, "sentinela": v}


def agente_do_evento(t):
    s = t.lower()
    if s.startswith("posições") or "posições:" in s: return "RISCO"
    if "→ posição" in s: return "SAÍDA" if "zerada" in s else "SNIPER"
    if "carteira do prédio" in s: return "CARTEIRA"
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
    extra, blocos = equipe_extra()
    for nome, (n, txt) in extra.items():
        cont[nome] = n; ultimo[nome] = txt
    cont["ARANHA"] = t["total_noticias"]
    ia = ler_json("carteira_predio.json")
    return {
        "agora": datetime.now(timezone.utc).isoformat(),
        "mesas": ms,
        "total": round(sum(m["valor"] for m in ms), 2),
        "base": 100 * len(ms),
        "agentes": [{"nome": a, "papel": p, "acoes": cont.get(a, 0), "ultimo": ultimo.get(a, "aguardando...")} for a, p in AGENTES.items()],
        "eventos": ev,
        "teia": t,
        "equipe": blocos,
        "prova": ler_json("prova.json"),
        "ia": {"valor": (ia.get("hist") or [{"valor": 100}])[-1]["valor"], "caixa": ia.get("caixa", 100), "meta": 1000, "inicial": 100,
               "posicoes": ia.get("posicoes", {}), "hist": [h["valor"] for h in ia.get("hist", [])[-300:]]},
    }


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=AQUI, **k)

    def log_message(self, *a):
        pass

    def do_POST(self):
        """Recebe textos copiados do navegador (respostas do ChatGPT/Claude web) e salva em estudo/notas/."""
        if not self.path.startswith("/api/nota"):
            self.send_response(404); self.end_headers(); return
        n = int(self.headers.get("Content-Length", 0))
        txt = self.rfile.read(min(n, 2_000_000)).decode("utf-8", "replace")
        pasta = os.path.join(RAIZ, "estudo", "notas"); os.makedirs(pasta, exist_ok=True)
        nome = re.sub(r"[^a-z0-9_-]", "", (self.path.split("nome=")[-1] if "nome=" in self.path else "nota").lower())[:40] or "nota"
        open(os.path.join(pasta, f"{nome}.md"), "w", encoding="utf-8").write(txt)
        self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b"ok")

    def do_GET(self):
        if self.path.startswith("/api/estado"):
            b = json.dumps(estado(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path.startswith("/api/carteira"):
            def lj(p):
                try: return json.load(open(p, encoding="utf-8"))
                except Exception: return {}
            c = lj(os.path.join(RAIZ, "data", "carteira.json")); a = lj(os.path.join(RAIZ, "acoes", "carteira_acoes.json"))
            b = json.dumps({"cripto": {"caixa": c.get("caixa"), "cofre": c.get("cofre", 0), "pos": c.get("pos", {}), "ligado": c.get("ligado", True),
                                       "hist": c.get("historico", [])[-200:]},
                            "acoes": {"caixa": a.get("caixa"), "pos": a.get("pos", {}), "hist": a.get("hist", [])[-200:]},
                            "foguete": (lambda f: {"conta": f.get("conta", {}), "pos": f.get("posicoes", {}), "hist": f.get("hist", [])[-300:]})(lj(os.path.join(RAIZ, "data", "foguete2.json")))},
                           ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(b); return
        if self.path.startswith("/api/aranha"):
            f = os.path.join(RAIZ, "data", "relatorio_aranha.json")
            rel = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {"noticias": []}
            try:
                ia_ = json.load(open(os.path.join(RAIZ, "data", "analise_ia.json"), encoding="utf-8"))
            except Exception:
                ia_ = {"analises": {}, "briefing": None}
            for n in rel.get("noticias", []):
                n["ia"] = ia_["analises"].get(n["id"])
            # as que a IA analisou e marcou como mais relevantes vêm primeiro
            rel["noticias"].sort(key=lambda n: -((n.get("ia") or {}).get("relevancia") or 0))
            rel["briefing"] = ia_.get("briefing")
            b = json.dumps(rel, ensure_ascii=False).encode("utf-8")
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
    """A aranha e os robôs rodam 24h na nuvem (GitHub Actions). Aqui o PC puxa os resultados
    e roda a ARANHA ANALISTA (IA da NVIDIA) por cima das notícias."""
    import subprocess
    while True:
        try:
            subprocess.Popen([sys.executable, os.path.join(RAIZ, "equipe", "aranha_ia.py")], cwd=RAIZ,
                             stdout=open(os.path.join(RAIZ, "data", "aranha_ia.log"), "a"), stderr=subprocess.STDOUT, creationflags=0x08000000)
        except Exception as e:
            print("aranha ia:", e)
        try:
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
            subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=RAIZ, timeout=90, env=env, creationflags=0x08000000)
            # só os DADOS que a nuvem produz; o código local nunca é tocado
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "data/aranha.db", "data/carteira.json", "data/relatorio_aranha.json",
                            "data/calendario.json", "data/sec.json", "data/fills.json", "data/sentinela.json",
                            "data/ia_pura.json", "data/prova.json", "data/foguete2.json", "data/foguete2_exec.json", "data/probabilidades.json",
                            "data/predio.json", "data/cotas_ia.json", "site/dados",
                            "acoes/carteira_acoes.json", "diario"], cwd=RAIZ, timeout=60, env=env, capture_output=True, creationflags=0x08000000)
            subprocess.run(["git", "reset", "-q", "--", "data", "acoes/carteira_acoes.json", "diario", "site/dados"], cwd=RAIZ, timeout=30, env=env, capture_output=True, creationflags=0x08000000)
        except Exception as e:
            print("sync:", e)
        time.sleep(10 * 60)


if __name__ == "__main__":
    threading.Thread(target=ciclo_aranha, daemon=True).start()
    print(f"Mesa de agentes em http://localhost:{PORTA}")
    ThreadingHTTPServer(("127.0.0.1", PORTA), H).serve_forever()
