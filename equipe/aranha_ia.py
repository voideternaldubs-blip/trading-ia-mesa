"""ARANHA ANALISTA (IA): lê as notícias que a aranha coletou e ENTENDE cada uma, com o modelo grátis da NVIDIA.
Para cada notícia: o que aconteceu (simples), por que importa, quem sobe/cai (força e prazo), lição para o dono aprender.
A cada rodada: BRIEFING DO MUNDO (o que está acontecendo, o que significa para o dinheiro, o que a mesa está fazendo).
Saída: data/analise_ia.json (lido pela página da aranha)."""
import os, sys, json, time
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import ia  # noqa: E402

REL = os.path.join(RAIZ, "data", "relatorio_aranha.json")
SAIDA = os.path.join(RAIZ, "data", "analise_ia.json")

SIS_NOTICIA = """Você é um analista sênior de mercados e um ótimo professor para iniciantes.
O leitor NÃO entende de mercado e quer aprender. Escreva em português do Brasil, frases curtas, sem jargão (se usar um termo, explique).
Para CADA notícia recebida devolva um objeto no JSON final. Responda SOMENTE com JSON válido no formato:
{"analises":[{"id":"<id>","resumo":"o que aconteceu em 2 frases simples",
"por_que_importa":"por que isso mexe com dinheiro, em 2 frases",
"impactos":[{"ativo":"BTC|ETH|NVDA|NASDAQ|S&P500|OURO|PETRÓLEO|DÓLAR|...","direcao":"alta|baixa","forca":1,"prazo":"horas|dias|semanas"}],
"relevancia":1,"licao":"uma lição curta de mercado que esta notícia ensina","confianca":"baixa|média|alta"}]}
forca e relevancia vão de 1 (fraco) a 3 (forte). Seja honesto: se o impacto é incerto, diga e use confianca baixa."""

SIS_BRIEF = """Você é o estrategista-chefe de uma mesa de agentes de trading e explica para um dono iniciante.
Português do Brasil, direto, sem enrolação, sem prometer lucro. Responda SOMENTE com JSON válido:
{"titulo":"manchete do momento em até 10 palavras",
"clima":"medo|cautela|neutro|otimismo|euforia",
"mundo":"o que está acontecendo no mundo agora (3 a 4 frases)",
"dinheiro":"o que isso significa para ações e cripto (2 a 3 frases)",
"mesa":"o que os robôs/agentes da mesa estão fazendo e por que isso faz sentido (2 a 3 frases)",
"ficar_de_olho":["3 coisas para acompanhar nas próximas horas"],
"aprenda":[{"termo":"...","explicacao":"..."},{"termo":"...","explicacao":"..."}]}"""


def carregar(p, padrao):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return padrao


def operario(grupo):
    """Um dos 9 OPERÁRIOS (modelo rápido) analisa um lote de notícias."""
    SEP = chr(10)
    partes = []
    for n in grupo:
        partes.append(SEP.join([f'id: {n["id"]}', f'fonte: {n["fonte"]}' + (" (FONTE OFICIAL)" if n.get("primaria") else ""),
                                f'título: {n["titulo"]}', f'resumo: {n.get("resumo", "")[:600]}', f'ativos citados: {", ".join(n["ativos"])}']))
    texto = (SEP * 2).join(partes)
    try:
        j = ia.json_de(ia.pergunta(SIS_NOTICIA, texto, modelo="z-ai/glm-5.3-flash", max_tokens=2200, timeout=150)) or {}
        ids = {n["id"] for n in grupo}
        return [a for a in j.get("analises", []) if a.get("id") in ids]
    except Exception as ex:
        print("operário falhou:", str(ex)[:100]); return []


def main(max_novas=45, lote=5, operarios=9):
    from concurrent.futures import ThreadPoolExecutor
    rel = carregar(REL, {})
    out = carregar(SAIDA, {"analises": {}, "briefing": None})
    ns = [n for n in rel.get("noticias", []) if n["id"] not in out["analises"]][:max_novas]
    lotes = [ns[i:i + lote] for i in range(0, len(ns), lote)]
    feitas = 0
    # MAESTRO + 9 OPERÁRIOS: os lotes são analisados em paralelo
    with ThreadPoolExecutor(max_workers=operarios) as ex:
        for res in ex.map(operario, lotes):
            for a in res:
                a["quando"] = datetime.now(timezone.utc).isoformat()[:16]
                out["analises"][a["id"]] = a; feitas += 1
    # briefing do mundo
    try:
        mesa = carregar(os.path.join(RAIZ, "data", "carteira.json"), {})
        fg = carregar(os.path.join(RAIZ, "data", "foguete2.json"), {})
        sent = carregar(os.path.join(RAIZ, "data", "sentinela.json"), {})
        cal = carregar(os.path.join(RAIZ, "data", "calendario.json"), {})
        manchetes = "\n".join(f'- [{n["tipo"]}] {n["titulo"]} ({", ".join(n["ativos"])})' for n in rel.get("noticias", [])[:35])
        posf = ", ".join(f'{s.replace("USDT", "")} {"comprado" if p["lado"] > 0 else "vendido"}' for s, p in fg.get("posicoes", {}).items())
        contexto = (f"MANCHETES RECENTES:\n{manchetes}\n\nMESA: foguete multi-moeda com posições: {posf or 'nenhuma'}; "
                    f"robô de tendência cripto: {len(mesa.get('pos', {}))} posições; ações TQQQ/SOXL/UPRO em caixa porque os índices estão abaixo da média de 200 dias. "
                    f"Calendário: {cal.get('aviso', '')}. Sentinela: {sent.get('resumo', '')}.")
        b = ia.json_de(ia.pergunta(SIS_BRIEF, contexto, modelo="moonshotai/kimi-k3.1-pro", max_tokens=1600, timeout=240))             or ia.json_de(ia.pergunta(SIS_BRIEF, contexto, max_tokens=1400, timeout=150))
        if b:
            b["quando"] = datetime.now(timezone.utc).isoformat()[:16]
            out["briefing"] = b
    except Exception as ex:
        print("briefing falhou:", str(ex)[:120])
    # mantém só as análises das notícias ainda no relatório + 200 últimas
    ids = {n["id"] for n in rel.get("noticias", [])}
    out["analises"] = {k: v for k, v in out["analises"].items() if k in ids} or dict(list(out["analises"].items())[-200:])
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ARANHA IA: {feitas} notícias analisadas | briefing: {(out.get('briefing') or {}).get('titulo', '-')}")


if __name__ == "__main__":
    trava = os.path.join(RAIZ, "data", "aranha_ia.lock")
    if os.path.exists(trava) and time.time() - os.path.getmtime(trava) < 1800:
        print("análise anterior ainda rodando"); raise SystemExit
    open(trava, "w").write(str(os.getpid()))
    try:
        main()
    finally:
        os.remove(trava)
