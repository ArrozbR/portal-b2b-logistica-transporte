"""Gera um token de teste para chamar a API. Só para desenvolvimento.

    python -m comum.ferramentas.gerar_token --perfil comprador --empresa emp-comprador-1

No formato da Autenticação (RS256, o padrão), quem assina é o `usuarios-falso`,
porque só ele tem a chave privada: o script pede o token a ele
(`USUARIOS_FALSO_URL`, padrão http://usuarios-falso:8101). No formato do kit
(`JWT_ALGORITHM=HS256`), o script assina sozinho com a `JWT_SECRET_KEY`.
"""

import argparse
import json
import time
import urllib.request
import uuid

import jwt

from comum import config
from comum.auth import PERFIS, algoritmo


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um token de teste.")
    parser.add_argument("--perfil", required=True, choices=PERFIS)
    parser.add_argument("--empresa", default="emp-comprador-1")
    parser.add_argument("--usuario", default=None, help="padrão: gerado")
    parser.add_argument("--minutos", type=int, default=15, help="validade (o kit usa 15 min)")
    args = parser.parse_args()
    usuario = args.usuario or f"usr-{uuid.uuid4().hex[:8]}"

    if algoritmo() == "HS256":
        agora = int(time.time())
        claims = {"sub": usuario, "empresaId": args.empresa, "perfil": args.perfil,
                  "iat": agora, "exp": agora + args.minutos * 60, "type": "access"}
        print(jwt.encode(claims, config.texto("JWT_SECRET_KEY"), algorithm="HS256"))
        return

    base = config.texto("USUARIOS_FALSO_URL", "http://usuarios-falso:8101")
    corpo = json.dumps({"perfil": args.perfil, "empresaId": args.empresa, "usuarioId": usuario,
                        "minutos": args.minutos}).encode()
    pedido = urllib.request.Request(f"{base}/api/v1/usuarios/demonstracao/token", data=corpo,
                                    headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(pedido, timeout=5) as resposta:
        print(json.load(resposta)["accessToken"])


if __name__ == "__main__":
    main()
