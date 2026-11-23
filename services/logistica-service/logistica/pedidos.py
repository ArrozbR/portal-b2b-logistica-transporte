"""Pedido que nasce antes de ter comprador (decisão D26, proposta).

Segundo o professor (12/11/2026, registrado pelo grupo de Fornecimento e
Produtos), o pedido é criado na ABERTURA do leilão ou da negociação. No
leilão, o comprador só é definido quando ele fecha. Então o `pedido_criado`
pode chegar sem `compradorId` e, como o destino é o local do comprador, sem
`destino`.

Sem comprador e destino não há frete para cotar. O pedido fica guardado e a
solicitação de frete só abre quando o fechamento chega, num `pedido_atualizado`
com `compradorId` e `destino`. Os dois eventos vêm de tópicos diferentes e
podem chegar em qualquer ordem, por isso o pedido e o fechamento são guardados
separados e juntados aqui.

Funções puras (sem banco), testadas sozinhas.
"""

# O que o frete precisa e o pedido de leilão só ganha no fechamento.
OBRIGATORIOS_PARA_O_FRETE = ("compradorId", "destino")

# Campos do pedido_atualizado que valem como fechamento (o lance vencedor pode
# mudar o valor e a quantidade).
CAMPOS_DO_FECHAMENTO = ("compradorId", "destino", "quantidade", "pesoKg", "valorTotal", "dataEntregaDesejada")


def dados_do_fechamento(payload: dict) -> dict:
    """Os campos de fechamento presentes (e não nulos) num pedido_atualizado."""
    return {campo: payload[campo] for campo in CAMPOS_DO_FECHAMENTO if payload.get(campo) is not None}


def mesclar(pedido: dict, fechamento: dict) -> dict:
    """O pedido com os dados do fechamento por cima. O fechamento vence, mas um nulo nunca apaga um valor."""
    return {**pedido, **{campo: valor for campo, valor in fechamento.items() if valor is not None}}


def faltando_para_o_frete(dados: dict) -> list[str]:
    """Campos que ainda faltam para abrir a solicitação de frete (vazia = pode abrir)."""
    return [campo for campo in OBRIGATORIOS_PARA_O_FRETE if not dados.get(campo)]
