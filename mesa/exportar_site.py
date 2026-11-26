"""Gera o SITE estático para o Vercel (pasta site/): as 3 telas + os dados em site/dados/*.json.
Roda na nuvem (GitHub Actions, de hora em hora) e no PC (dados do foguete). O Vercel publica a cada atualização."""
import os, sys, json, shutil, re

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SITE = os.path.join(RAIZ, "site")
sys.path.insert(0, AQUI)
import servidor  # noqa: E402  (só as funções; o servidor não sobe)


def ler(p, padrao):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return padrao


def carteira():
    c = ler(os.path.join(RAIZ, "data", "carteira.json"), {}); a = ler(os.path.join(RAIZ, "acoes", "carteira_acoes.json"), {})
    f = ler(os.path.join(RAIZ, "data", "foguete2.json"), None) or ler(os.path.join(SITE, "dados", "foguete.json"), {})
    return {"cripto": {"caixa": c.get("caixa"), "cofre": c.get("cofre", 0), "pos": c.get("pos", {}), "ligado": c.get("ligado", True), "hist": c.get("historico", [])[-200:]},
            "acoes": {"caixa": a.get("caixa"), "pos": a.get("pos", {}), "hist": a.get("hist", [])[-200:]},
            "foguete": {"conta": f.get("conta", {}), "pos": f.get("posicoes", {}), "hist": f.get("hist", [])[-300:]},
            "ia": {**{k: v for k, v in ler(os.path.join(RAIZ, "data", "carteira_predio.json"), {}).items() if k in ("caixa", "posicoes", "fechadas", "modo")},
                   "hist": ler(os.path.join(RAIZ, "data", "carteira_predio.json"), {}).get("hist", [])[-200:],
                   "prob": ler(os.path.join(RAIZ, "data", "probabilidades.json"), {}).get("posicoes", {})},
            "atualizado": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()[:19]}


def aranha():
    rel = ler(os.path.join(RAIZ, "data", "relatorio_aranha.json"), {"noticias": []})
    ia = ler(os.path.join(RAIZ, "data", "analise_ia.json"), {"analises": {}, "briefing": None})
    for n in rel.get("noticias", []):
        n["ia"] = ia["analises"].get(n["id"])
    rel["noticias"].sort(key=lambda n: -((n.get("ia") or {}).get("relevancia") or 0))
    rel["briefing"] = ia.get("briefing")
    return rel


def so_foguete():
    """No PC: grava só os dados do foguete (os demais vêm da nuvem)."""
    os.makedirs(os.path.join(SITE, "dados"), exist_ok=True)
    f = ler(os.path.join(RAIZ, "data", "foguete2.json"), {})
    f["hist"] = f.get("hist", [])[-600:]
    f.pop("sinais", None)
    json.dump(f, open(os.path.join(SITE, "dados", "foguete.json"), "w", encoding="utf-8"), ensure_ascii=False)


def tudo():
    os.makedirs(os.path.join(SITE, "dados"), exist_ok=True)
    pr = ler(os.path.join(RAIZ, "data", "predio.json"), {})
    pr.pop("historico", None)
    dados = {"estado": servidor.estado(), "aranha": aranha(), "carteira": carteira(), "predio": pr}
    for k, v in dados.items():
        json.dump(v, open(os.path.join(SITE, "dados", f"{k}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    # páginas: no Vercel os dados vêm de /dados/*.json; no PC (porta 8787) continuam vindo da /api
    for pg in ("index.html", "aranha.html", "vivo.html", "predio.html"):
        s = open(os.path.join(AQUI, pg), encoding="utf-8").read()
        s = s.replace("<script>", "<script>const API=n=>location.port==='8787'?'/api/'+n:'https://raw.githubusercontent.com/voideternaldubs-blip/trading-ia-mesa/main/site/dados/'+n+'.json?t='+Math.floor(Date.now()/20000);", 1) if "const API=" not in s else s
        s = re.sub(r"fetch\('/api/(estado|aranha|carteira)'", lambda m: f"fetch(API('{m.group(1)}')", s)
        if pg == "index.html":  # o index tem script module próprio
            s = s.replace('<script type="module">', "<script type=\"module\">const API=n=>location.port==='8787'?'/api/'+n:'https://raw.githubusercontent.com/voideternaldubs-blip/trading-ia-mesa/main/site/dados/'+n+'.json?t='+Math.floor(Date.now()/20000);", 1)
        open(os.path.join(SITE, pg), "w", encoding="utf-8").write(s)
    json.dump({"cleanUrls": True, "headers": [{"source": "/dados/(.*)", "headers": [{"key": "Cache-Control", "value": "no-store"}]}]},
              open(os.path.join(SITE, "vercel.json"), "w"), indent=1)
    print("site gerado em", SITE)


if __name__ == "__main__":
    so_foguete() if "--foguete" in sys.argv else tudo()
