"""Publica um pedido_criado falso no Kafka (decisão D23).

Substitui o grupo de Pedidos nos testes e, se preciso, na apresentação. O
payload é validado contra o mesmo JSON Schema que a logística usa, então um
pedido que este script aceita é um pedido que o serviço aceita.

Exemplos (de dentro de um contêiner do projeto):

    python -m comum.ferramentas.publicar_pedido_falso
    python -m comum.ferramentas.publicar_pedido_falso --origem "Sorriso/MT" --destino "Santos/SP" \\
        --tipo GRANEL --peso 24000 --produto "Soja em grão" --valor 192000
    python -m comum.ferramentas.publicar_pedido_falso --repetir 5   # mesmo evento 5 vezes (teste de duplicidade)
"""

import argparse
import asyncio
import json
import sys
import uuid

from aiokafka import AIOKafkaProducer

from comum.eventos import erros_do_payload, montar_envelope
from comum.kafka import servidores


def _local(texto: str) -> dict:
    cidade, _, uf = texto.rpartition("/")
    if not cidade or len(uf) != 2:
        raise argparse.ArgumentTypeError('use o formato "Cidade/UF", ex.: "Sorriso/MT"')
    return {"cidade": cidade.strip(), "uf": uf.strip().upper()}


def montar_payload(args: argparse.Namespace) -> dict:
    return {
        "pedidoId": args.pedido_id or f"ped-{uuid.uuid4().hex[:8]}",
        "negociacaoId": f"neg-{uuid.uuid4().hex[:8]}",
        "compradorId": args.comprador,
        "fornecedorId": args.fornecedor,
        "produtoId": args.produto_id,
        "fornecimentoId": f"forn-{uuid.uuid4().hex[:8]}",  # pedido do grupo de Fornecimento e Produtos
        "produtoNome": args.produto,
        "quantidade": args.peso,
        "unidade": "KG",
        "pesoKg": args.peso,
        "tipoTransporte": args.tipo,
        "valorTotal": args.valor,
        "origem": args.origem,
        "destino": args.destino,
        "status": "CRIADO",
    }


async def publicar(envelope: dict, repetir: int) -> None:
    produtor = AIOKafkaProducer(bootstrap_servers=servidores(), acks="all", enable_idempotence=True)
    await produtor.start()
    try:
        corpo = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        for _ in range(repetir):
            await produtor.send_and_wait("pedido_criado", value=corpo, key=envelope["aggregateId"].encode("utf-8"))
    finally:
        await produtor.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica um pedido_criado falso no Kafka.")
    parser.add_argument("--pedido-id", help="padrão: gerado")
    parser.add_argument("--origem", type=_local, default=_local("Sorriso/MT"))
    parser.add_argument("--destino", type=_local, default=_local("Santos/SP"))
    parser.add_argument("--tipo", default="GRANEL", choices=["GRANEL", "REFRIGERADO", "CARGA_SECA", "PERIGOSO"])
    parser.add_argument("--peso", type=float, default=24000, help="peso em kg")
    parser.add_argument("--produto", default="Soja em grão")
    parser.add_argument("--produto-id", default="prod-soja")
    parser.add_argument("--valor", type=float, default=192000.0, help="valor da carga em R$")
    parser.add_argument("--comprador", default="emp-comprador-1")
    parser.add_argument("--fornecedor", default="emp-fornecedor-1")
    parser.add_argument("--repetir", type=int, default=1, help="publica o MESMO evento N vezes")
    args = parser.parse_args()

    payload = montar_payload(args)
    erros = erros_do_payload("pedido_criado", payload)
    if erros:
        print("Pedido fora do contrato:", *erros, sep="\n  ", file=sys.stderr)
        sys.exit(1)

    envelope = montar_envelope("pedido_criado", "pedidos-falso", payload["pedidoId"], payload)
    asyncio.run(publicar(envelope, args.repetir))
    print(json.dumps({"publicado": args.repetir, "pedidoId": payload["pedidoId"],
                      "eventId": envelope["eventId"], "correlationId": envelope["correlationId"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
