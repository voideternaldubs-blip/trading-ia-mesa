"""Envia os dados do foguete (que roda no PC por causa da Binance) para o site, a cada 30 min, pela API do GitHub.
Não usa o git local: nada de janela, nada de conflito."""
import os, sys, json, time, base64, subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCA = os.path.join(RAIZ, "data", "publica_foguete.ultimo")
ARQ = os.path.join(RAIZ, "site", "dados", "foguete.json")
REPO = "voideternaldubs-blip/trading-ia-mesa"
CAMINHO = "site/dados/foguete.json"
NOJAN = 0x08000000


def gh(*args, entrada=None):
    return subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True, creationflags=NOJAN)


def main():
    if os.path.exists(MARCA) and time.time() - os.path.getmtime(MARCA) < 30 * 60:
        return
    subprocess.run([sys.executable, os.path.join(RAIZ, "mesa", "exportar_site.py"), "--foguete"], creationflags=NOJAN)
    conteudo = base64.b64encode(open(ARQ, "rb").read()).decode()
    sha = gh("api", f"repos/{REPO}/contents/{CAMINHO}", "--jq", ".sha").stdout.strip()
    corpo = {"message": "foguete: dados do PC", "content": conteudo, "branch": "main"}
    if sha and len(sha) == 40:
        corpo["sha"] = sha
    r = gh("api", "-X", "PUT", f"repos/{REPO}/contents/{CAMINHO}", "--input", "-", entrada=json.dumps(corpo))
    print("publicado" if r.returncode == 0 else "falhou: " + r.stderr[:200])
    open(MARCA, "w").write(str(time.time()))


if __name__ == "__main__":
    main()
