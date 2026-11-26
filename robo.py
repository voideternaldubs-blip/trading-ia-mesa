"""ROBÔ: mesa de 6 agentes operando com DINHEIRO DE MENTIRA (papel), preço real da Binance.
Roda a cada 4h (depois que a vela fecha). Estado em data/carteira.json, diário em diario/.

ATIRADOR   -> média de 3 rompimentos (80, 120, 200 velas): passou no teste vs aleatório e no período de prova
RISCO      -> tamanho pela volatilidade (alvo 50%/ano por moeda), máx. 10 moedas divididas igual
SAÍDA      -> stop de emergência: perda de 12% numa posição fecha na hora
NOTÍCIAS   -> aranha: muito perigo sobre a moeda = não abre compra nova nela
BALEIA     -> financiamento esticado demais (>0,05%/8h) = não abre compra; muito negativo = não abre venda
CHEFE      -> se a carteira cair 40% do topo, desliga tudo e chama o Breno
"""
import os, json, requests, pandas as pd
from datetime import datetime, timezone
from testador_ls import donch_ls, vol_ajuste
import aranha

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(AQUI, "data", "carteira.json")
DIARIO = os.path.join(AQUI, "diario")
CUSTO = 0.0015
INICIAL = 100.0


def velas(m, n=600):
    r = requests.get("https://data-api.binance.vision/api/v3/klines",
                     params={"symbol": m + "USDT", "interval": "4h", "limit": n}, timeout=20).json()
    df = pd.DataFrame(r, columns=list("tohlcvTqnbBx"))[["t", "o", "h", "l", "c"]].astype(float)
    df["t"] = pd.to_datetime(df.t, unit="ms", utc=True)
    df = df.set_index("t")
    return df.iloc[:-1]  # descarta a vela que ainda não fechou


def carregar():
    if os.path.exists(ESTADO):
        return json.load(open(ESTADO, encoding="utf-8"))
    return {"caixa": INICIAL, "pos": {}, "topo": INICIAL, "ligado": True, "historico": []}


def valor(est, precos):
    v = est["caixa"]
    for m, p in est["pos"].items():
        v += p["qtd"] * precos[m]  # qtd negativa = vendido
    return v


def main():
    est = carregar()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log = [f"## {agora}"]
    c = aranha.db()
    try:
        aranha.noticias(c); aranha.mercado(c); c.commit()
    except Exception as e:
        log.append(f"- aranha falhou: {e}")
    news, merc = aranha.resumo(c)
    fin = merc.get("financiamento", {})

    dados = {m: velas(m) for m in aranha.MOEDAS}
    precos = {m: d.c.iloc[-1] for m, d in dados.items()}
    total = valor(est, precos)
    est["topo"] = max(est["topo"], total)
    queda = total / est["topo"] - 1

    # CHEFE: freio de mão
    if est["ligado"] and queda <= -0.40:
        est["ligado"] = False
        log.append(f"- 🛑 CHEFE: carteira caiu {queda:.0%} do topo. TUDO DESLIGADO. Chamar o Breno.")
    alvo = {}
    for m, df in dados.items():
        if not est["ligado"]:
            alvo[m] = 0.0; continue
        sinal = float(vol_ajuste(df.c, sum(donch_ls(df, n) for n in (80, 120, 200)) / 3, 0.5).iloc[-1])  # ATIRADOR (ensemble) + RISCO
        motivo = []
        atual = est["pos"].get(m)
        # SAÍDA: stop de emergência
        if atual:
            pl = (precos[m] / atual["preco"] - 1) * (1 if atual["qtd"] > 0 else -1)
            if pl <= -0.12:
                sinal = 0.0; motivo.append(f"stop {pl:.0%}")
        abrindo = not atual or (atual["qtd"] > 0) != (sinal > 0)
        # NOTÍCIAS: veto de compra nova
        lim = 5 if m in ("BTC", "ETH") else 2
        if sinal > 0 and abrindo and len(news[m]["perigo"]) >= lim:
            sinal = 0.0; motivo.append(f"veto notícias ({len(news[m]['perigo'])} alertas)")
        # BALEIA: mercado esticado
        f = fin.get(m, 0)
        if sinal > 0 and abrindo and f > 0.0005:
            sinal = 0.0; motivo.append(f"veto baleia (financ. {f:.3%})")
        if sinal < 0 and abrindo and f < -0.0005:
            sinal = 0.0; motivo.append(f"veto baleia (financ. {f:.3%})")
        alvo[m] = sinal
        if motivo:
            log.append(f"- {m}: " + "; ".join(motivo))

    # executa no papel: cada moeda recebe no máx. 1/10 da carteira
    fatia = total / len(dados)
    for m, s in alvo.items():
        desejado = s * fatia / precos[m]
        atual = est["pos"].get(m, {"qtd": 0.0, "preco": precos[m]})
        dif = desejado - atual["qtd"]
        if abs(dif * precos[m]) < 1.0:  # ignora ajuste menor que 1 dólar
            continue
        est["caixa"] -= dif * precos[m] + abs(dif * precos[m]) * CUSTO
        nova = atual["qtd"] + dif
        lado = "COMPRA" if dif > 0 else "VENDA"
        log.append(f"- {lado} {m}: {abs(dif * precos[m]):.2f} USD a {precos[m]:.4g} → posição {'comprado' if nova > 0 else 'vendido' if nova < 0 else 'zerada'}")
        if abs(nova * precos[m]) < 1.0:
            est["pos"].pop(m, None)
        else:
            mesmo = atual["qtd"] != 0 and (atual["qtd"] > 0) == (nova > 0)
            est["pos"][m] = {"qtd": nova, "preco": atual["preco"] if mesmo else precos[m]}

    total = valor(est, precos)
    est["historico"].append({"quando": agora, "valor": round(total, 4)})
    log.append(f"- **Carteira: {total:.2f} USD** ({total / INICIAL - 1:+.1%} desde o início) | medo/ganância {merc.get('medo_ganancia', {}).get('geral')}")
    log.append("- Posições: " + (", ".join(f"{m} {'comprado' if p['qtd'] > 0 else 'vendido'} {abs(p['qtd'] * precos[m]):.2f}$" for m, p in est["pos"].items()) or "nenhuma"))
    json.dump(est, open(ESTADO, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.makedirs(DIARIO, exist_ok=True)
    with open(os.path.join(DIARIO, agora[:10] + ".md"), "a", encoding="utf-8") as fp:
        fp.write("\n".join(log) + "\n\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
