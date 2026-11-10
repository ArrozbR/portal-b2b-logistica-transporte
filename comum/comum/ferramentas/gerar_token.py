"""Gera um JWT de teste, no formato do usuarios-service, para chamar a API.

    python -m comum.ferramentas.gerar_token --perfil comprador --empresa emp-comprador-1

Usa a mesma JWT_SECRET_KEY do serviço. Só para desenvolvimento.
"""

import argparse
import time
import uuid

import jwt

from comum import config
from comum.auth import PERFIS


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um JWT de teste.")
    parser.add_argument("--perfil", required=True, choices=PERFIS)
    parser.add_argument("--empresa", default="emp-comprador-1")
    parser.add_argument("--usuario", default=None, help="padrão: gerado")
    parser.add_argument("--minutos", type=int, default=15, help="validade (o kit usa 15 min)")
    args = parser.parse_args()

    agora = int(time.time())
    claims = {
        "sub": args.usuario or f"usr-{uuid.uuid4().hex[:8]}",
        "empresaId": args.empresa,
        "perfil": args.perfil,
        "iat": agora,
        "exp": agora + args.minutos * 60,
        "type": "access",
    }
    print(jwt.encode(claims, config.texto("JWT_SECRET_KEY"), algorithm=config.texto("JWT_ALGORITHM", "HS256")))


if __name__ == "__main__":
    main()
