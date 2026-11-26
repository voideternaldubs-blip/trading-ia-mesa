"""Cérebro dos agentes: modelos grátis da NVIDIA via OmniRoute local (combo nvidia-gratis).
A chave vem da variável OMNIROUTE_API_KEY (carregada do arquivo de chaves do dono; nunca gravada aqui)."""
import os, re, json, subprocess, requests

URL = "https://integrate.api.nvidia.com/v1/chat/completions"  # NVIDIA NIM direto (grátis; funciona no PC e na nuvem)


def _chave():
    k = os.environ.get("NVIDIA_API_KEY") or os.environ.get("OMNIROUTE_API_KEY")
    if k:
        return k
    bat = os.path.join(os.path.expanduser("~"), ".bv-chaves.bat")
    if os.path.exists(bat):
        out = subprocess.run(f'cmd /v:on /c "call "{bat}" >nul 2>&1 && echo !OMNIROUTE_API_KEY!"', capture_output=True, text=True).stdout.strip()
        if out and "!" not in out:
            os.environ["OMNIROUTE_API_KEY"] = out
            return out
    return None


MODELOS = ["z-ai/glm-5.3-flash", "moonshotai/kimi-k3.1-pro"]


def pergunta(sistema, texto, modelo=None, max_tokens=900, timeout=90):
    k = _chave()
    if not k:
        raise RuntimeError("sem chave do OmniRoute")
    erro = None
    for m in ([modelo] if modelo else MODELOS):
        try:
            r = requests.post(URL, headers={"Authorization": f"Bearer {k}"}, timeout=timeout,
                              json={"model": m, "temperature": 0, "max_tokens": max_tokens,
                                    "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as ex:
            erro = ex
    raise RuntimeError(f"IA indisponível: {erro}")


def json_de(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else None


if __name__ == "__main__":
    print(pergunta("Responda em português, em uma frase.", "O que é uma ação?"))
