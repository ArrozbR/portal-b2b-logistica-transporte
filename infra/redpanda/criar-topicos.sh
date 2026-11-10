#!/bin/bash
# Cria os tópicos que o grupo usa. 3 partições, como no kit; réplica 1 porque
# o ambiente de desenvolvimento tem um broker só (o kit tem 3).
set -uo pipefail

BROKERS="${BROKERS:-redpanda:9092}"

TOPICOS=(
    # do kit
    pedido_criado
    pedido_atualizado
    empresa_cadastrada
    solicitacao_frete_criada
    cotacao_recebida
    frete_selecionado
    # novos, propostos à Infraestrutura (D12, D18)
    rastreio_atualizado
    entrega_concluida
    frete_indisponivel
    relogio_ajustado
    # tópicos de falha
    logistica.dlt
    transportadoras.dlt
)

for topico in "${TOPICOS[@]}"; do
    if rpk topic describe "$topico" -X brokers="$BROKERS" >/dev/null 2>&1; then
        echo "já existe: $topico"
    else
        rpk topic create "$topico" -p 3 -r 1 -c retention.ms=604800000 -X brokers="$BROKERS" \
            || { echo "falhou: $topico"; exit 1; }
    fi
done
echo "Tópicos prontos."
