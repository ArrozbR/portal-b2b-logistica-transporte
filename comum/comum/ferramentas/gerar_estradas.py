"""Gera `comum/dados/estradas.json`: o traçado das estradas entre cidades vizinhas.

Roda uma vez, por quem mantém a tabela de cidades (com internet), e o resultado vai
para o repositório. Os serviços só leem o arquivo: a demonstração não depende de
internet nem do servidor de rotas.

Como funciona:

1. Cada cidade de `comum.geo` é ligada às suas vizinhas mais próximas (até
   VIZINHAS cidades, a no máximo RAIO_KM em linha reta).
2. Para cada ligação, o servidor público do OSRM (motor de rotas sobre o
   OpenStreetMap) devolve o caminho de carro e a distância. Ligações absurdas
   (balsa ou volta de mais de 3 vezes a linha reta) são descartadas.
3. O traçado é simplificado (Douglas-Peucker, ~1 km de tolerância), para o
   arquivo ficar pequeno, e gravado com 4 casas decimais (~11 m).

Uso (fora dos contêineres, com a .venv):
    .venv/Scripts/python -m comum.ferramentas.gerar_estradas

Dados de rota: © colaboradores do OpenStreetMap (licença ODbL), via OSRM.
"""

import argparse
import json
import math
import sys
import subprocess
import time
from datetime import date
from pathlib import Path

from comum.geo import cidades, distancia_linha_reta_km

SERVIDOR = "https://router.project-osrm.org"
VIZINHAS = 5
RAIO_KM = 900.0
TOLERANCIA_GRAUS = 0.01  # ~1,1 km
MAIOR_DESVIO = 3.0       # estrada mais de 3x a linha reta: balsa ou volta enorme
ESPERA_S = 1.1           # política de uso do servidor público: até 1 consulta por segundo
DESTINO = Path(__file__).resolve().parent.parent / "dados" / "estradas.json"


def chave(cidade) -> str:
    return f"{cidade.nome}/{cidade.uf}"


def ligacoes() -> list[tuple]:
    """Pares (a, b) de cidades vizinhas, sem repetição."""
    todas = cidades()
    pares = set()
    for c in todas:
        perto = sorted((distancia_linha_reta_km(c.lat, c.lon, o.lat, o.lon), i, o)
                       for i, o in enumerate(todas) if o is not c)
        for distancia, _, o in perto[:VIZINHAS]:
            if distancia <= RAIO_KM:
                pares.add(tuple(sorted((chave(c), chave(o)))))
    por_chave = {chave(c): c for c in todas}
    return [(por_chave[a], por_chave[b]) for a, b in sorted(pares)]


def simplificar(pontos: list[tuple[float, float]], tolerancia: float) -> list[tuple[float, float]]:
    """Douglas-Peucker: tira os pontos que quase não mudam o desenho."""
    if len(pontos) < 3:
        return pontos
    (x1, y1), (x2, y2) = pontos[0], pontos[-1]
    dx, dy = x2 - x1, y2 - y1
    norma = math.hypot(dx, dy) or 1e-12
    maior, indice = 0.0, 0
    for i in range(1, len(pontos) - 1):
        x, y = pontos[i]
        distancia = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norma
        if distancia > maior:
            maior, indice = distancia, i
    if maior <= tolerancia:
        return [pontos[0], pontos[-1]]
    return simplificar(pontos[:indice + 1], tolerancia)[:-1] + simplificar(pontos[indice:], tolerancia)


def baixar_json(url: str) -> dict:
    """GET com o curl do sistema.

    O curl usa os certificados do sistema operacional. Em algumas instalações do Python, a
    lista de certificados é antiga e recusa o do servidor ("certificate has expired"); a
    verificação do certificado nunca é desligada.
    """
    resultado = subprocess.run(
        ["curl", "--silent", "--show-error", "--fail", "--max-time", "30",
         "--user-agent", "portal-b2b-ferramenta-de-rotas/1.0", url],
        capture_output=True, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode(errors="replace").strip() or f"curl saiu com {resultado.returncode}")
    return json.loads(resultado.stdout)


def rota_osrm(a, b) -> tuple[float, list[tuple[float, float]]]:
    url = (f"{SERVIDOR}/route/v1/driving/{a.lon},{a.lat};{b.lon},{b.lat}"
           "?overview=full&geometries=geojson")
    dados = baixar_json(url)
    if dados.get("code") != "Ok" or not dados.get("routes"):
        raise RuntimeError(dados.get("code", "sem rota"))
    rota = dados["routes"][0]
    pontos = [(lat, lon) for lon, lat in rota["geometry"]["coordinates"]]
    return rota["distance"] / 1000, pontos


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    pares = ligacoes()
    print(f"{len(pares)} ligações entre {len(cidades())} cidades", file=sys.stderr)
    trechos, descartados = [], []
    falhas_seguidas = 0
    for n, (a, b) in enumerate(pares, start=1):
        reta = distancia_linha_reta_km(a.lat, a.lon, b.lat, b.lon)
        km, pontos, ultimo = None, [], None
        for tentativa in range(3):
            time.sleep(ESPERA_S)
            try:
                km, pontos = rota_osrm(a, b)
                break
            except Exception as erro:  # rede instável: tenta de novo
                ultimo = erro
                time.sleep(3 * (tentativa + 1))
        if km is None:
            descartados.append(f"{chave(a)} - {chave(b)}: {ultimo}")
            falhas_seguidas += 1
            if falhas_seguidas >= 5:  # o servidor não está respondendo: para, em vez de insistir por horas
                sys.exit(f"5 falhas seguidas; última: {ultimo}")
            continue
        falhas_seguidas = 0
        if km > reta * MAIOR_DESVIO:
            descartados.append(f"{chave(a)} - {chave(b)}: {km:.0f} km de estrada para {reta:.0f} km em linha reta")
            continue
        # O traçado começa e termina no centro das cidades da tabela, como o resto da simulação.
        pontos = [(a.lat, a.lon), *simplificar(pontos, TOLERANCIA_GRAUS), (b.lat, b.lon)]
        trechos.append({"a": chave(a), "b": chave(b), "km": round(km, 1),
                        "pontos": [[round(lat, 4), round(lon, 4)] for lat, lon in pontos]})
        if n % 25 == 0:
            print(f"  {n}/{len(pares)}", file=sys.stderr, flush=True)
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(json.dumps({
        "fonte": "OSRM (router.project-osrm.org) sobre dados do OpenStreetMap, © colaboradores do "
                 "OpenStreetMap, licença ODbL",
        "geradoEm": date.today().isoformat(),
        "trechos": trechos,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(trechos)} trechos gravados em {DESTINO}", file=sys.stderr)
    for d in descartados:
        print(f"  descartado: {d}", file=sys.stderr)


if __name__ == "__main__":
    main()
