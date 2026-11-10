"""Leitura de configurações a partir de variáveis de ambiente."""

import os


def texto(nome: str, padrao: str | None = None) -> str:
    valor = os.getenv(nome, padrao)
    if valor is None:
        raise RuntimeError(f"Variável de ambiente obrigatória não definida: {nome}")
    return valor


def inteiro(nome: str, padrao: int) -> int:
    return int(os.getenv(nome, str(padrao)))


def decimal(nome: str, padrao: float) -> float:
    return float(os.getenv(nome, str(padrao)))
