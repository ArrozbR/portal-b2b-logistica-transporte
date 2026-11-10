"""Formatação de valores para mensagens ao usuário (notificações)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Horário de Brasília (sem horário de verão desde 2019).
BRASILIA = timezone(timedelta(hours=-3), "BRT")


def moeda(valor: Decimal | float) -> str:
    """6156.86 → 'R$ 6.156,86'"""
    texto = f"{Decimal(str(valor)):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def data_hora(momento: datetime) -> str:
    """Data e hora no horário de Brasília: '10/11/2026 09:30'."""
    return momento.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M")
