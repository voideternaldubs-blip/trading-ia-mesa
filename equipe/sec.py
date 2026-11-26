"""AGENTE SEC (a aranha dos documentos oficiais): lê os arquivos que as empresas são obrigadas a publicar.
- 8-K  = aconteceu algo importante (mudança de CEO, aquisição, resultado, processo)
- 4    = um DIRETOR comprou ou vendeu ações da própria empresa (compra com dinheiro próprio é sinal forte)
- 10-Q/10-K = balanço trimestral/anual
Saída: data/sec.json (poucas consultas por hora, respeitando a SEC)."""
import os, json, time, re, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "data", "sec.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CIK = {"NVDA": 1045810, "AAPL": 320193, "MSFT": 789019, "TSLA": 1318605, "AMD": 2488, "META": 1326801, "GOOGL": 1652044,
       "AMZN": 1018724, "AVGO": 1730168, "PLTR": 1321655, "MU": 723125, "ORCL": 1341439, "COIN": 1679788, "MSTR": 1050446}
EXPLICA = {"8-K": "Evento importante comunicado oficialmente (mudança na diretoria, aquisição, resultado, processo).",
           "4": "Um diretor ou grande acionista negociou ações da própria empresa.",
           "10-Q": "Balanço do trimestre: vendas, lucro, dívidas.", "10-K": "Balanço anual completo da empresa.",
           "SC 13G": "Um investidor grande passou a ter mais de 5% da empresa.", "SC 13D": "Investidor grande com mais de 5% e intenção de influenciar a empresa.",
           "144": "Aviso de que alguém de dentro pretende vender ações."}


def form4(cik, acc, doc):
    """Lê o Form 4: quem, comprou (P) ou vendeu (S), quantas ações, a que preço."""
    doc = re.sub(r"^xslF345X\d+/", "", doc)
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
    try:
        x = ET.fromstring(requests.get(url, headers=UA, timeout=20).content)
    except Exception:
        return None
    nome = (x.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").title()
    cargo = x.findtext(".//reportingOwnerRelationship/officerTitle") or ("Diretor" if x.findtext(".//isDirector") in ("1", "true") else "")
    compras = vendas = 0.0
    for t in x.findall(".//nonDerivativeTransaction"):
        cod = t.findtext(".//transactionCoding/transactionCode")
        q = float(t.findtext(".//transactionShares/value") or 0)
        p = float(t.findtext(".//transactionPricePerShare/value") or 0)
        if cod == "P": compras += q * p
        if cod == "S": vendas += q * p
    return {"quem": nome, "cargo": cargo, "comprou_usd": round(compras), "vendeu_usd": round(vendas)}


def main(dias=4):
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).date().isoformat()
    out = []
    for tk, cik in CIK.items():
        try:
            r = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=UA, timeout=20).json()["filings"]["recent"]
        except Exception as e:
            print("SEC falhou", tk, e); continue
        for i in range(min(40, len(r["form"]))):
            if r["filingDate"][i] < limite:
                break
            f = r["form"][i]
            if f not in EXPLICA:
                continue
            item = {"ticker": tk, "form": f, "dia": r["filingDate"][i], "explica": EXPLICA[f],
                    "link": f"https://www.sec.gov/Archives/edgar/data/{cik}/{r['accessionNumber'][i].replace('-', '')}/{r['primaryDocument'][i]}",
                    "descricao": r.get("primaryDocDescription", [""] * 99)[i] or ""}
            if f == "4":
                d = form4(cik, r["accessionNumber"][i], r["primaryDocument"][i])
                if d:
                    item.update(d)
                    if d["comprou_usd"] > 0:
                        item["sinal"] = f"{d['quem']} ({d['cargo']}) COMPROU US$ {d['comprou_usd']:,} com dinheiro próprio"
                    elif d["vendeu_usd"] > 0:
                        item["sinal"] = f"{d['quem']} ({d['cargo']}) vendeu US$ {d['vendeu_usd']:,}"
                time.sleep(0.25)
            out.append(item)
        time.sleep(0.25)
    compras = [x for x in out if x.get("comprou_usd", 0) > 0]
    json.dump({"gerado": datetime.now(timezone.utc).isoformat()[:16], "documentos": out, "compras_de_diretores": compras},
              open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"SEC: {len(out)} documentos em {dias} dias | compras de diretores: {len(compras)}")
    for x in out[:6]:
        print(" ", x["dia"], x["ticker"], x["form"], x.get("sinal", x["descricao"])[:80])


if __name__ == "__main__":
    main()
