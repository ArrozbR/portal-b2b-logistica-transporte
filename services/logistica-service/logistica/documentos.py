"""Documentos demonstrativos da entrega em PDF (decisão D21).

CT-e, romaneio de carga, nota fiscal e comprovante de coleta, gerados com os
dados REAIS da entrega, mas com a marca "DOCUMENTO DEMONSTRATIVO - SEM VALOR
FISCAL". Documento fiscal de verdade (CT-e, NF-e) é emitido por transportadora
e fornecedor junto à SEFAZ, fora do escopo de qualquer grupo do portal.

`gerar(tipo, entrega, emitido_em)` é pura (não acessa banco), para ser testada.
"""

import hashlib
from datetime import datetime
from decimal import Decimal

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from comum.formatos import data_hora, moeda

TIPOS = {
    "cte": "CT-e - Conhecimento de Transporte Eletrônico",
    "romaneio": "Romaneio de carga",
    "nota-fiscal": "Nota fiscal de venda",
    "comprovante-coleta": "Comprovante de coleta",
}

VERDE = (132, 204, 22)
CINZA = (107, 114, 128)
TEXTO = (31, 41, 55)


class DocumentoIndisponivel(Exception):
    """O documento ainda não pode ser gerado (ex.: comprovante antes da coleta)."""


def _latin1(texto) -> str:
    """As fontes padrão do PDF só têm o alfabeto latino (com acentos); troca o resto."""
    texto = str(texto if texto is not None else "-")
    for de, para in (("—", "-"), ("–", "-"), ("→", "->"), ("×", "x"), ("·", "-")):
        texto = texto.replace(de, para)
    return texto.encode("latin-1", "replace").decode("latin-1")


def numero_do_documento(entrega_id: str, tipo: str) -> str:
    """Número fictício e estável: o mesmo documento tem sempre o mesmo número."""
    return f"{int(hashlib.sha1(f'{tipo}:{entrega_id}'.encode()).hexdigest()[:8], 16) % 1_000_000:06d}"


def _peso(kg) -> str:
    kg = Decimal(str(kg))
    return f"{kg / 1000:,.1f} t ({kg:,.0f} kg)".replace(",", "_").replace(".", ",").replace("_", ".")


def _data(valor) -> str:
    if valor is None:
        return "-"
    if isinstance(valor, datetime):
        return data_hora(valor)
    return valor.strftime("%d/%m/%Y")


class _Pdf(FPDF):
    def __init__(self, titulo: str, numero: str, emitido_em: datetime):
        super().__init__(format="A4")
        self.titulo, self.numero, self.emitido_em = titulo, numero, emitido_em
        self.set_auto_page_break(True, margin=18)
        self.set_margins(14, 14, 14)

    def header(self):
        # Marca d'água na diagonal: começa embaixo à esquerda e sobe ~32°, cabendo na folha A4.
        with self.rotation(angle=32, x=28, y=205):
            self.set_font("Helvetica", "B", 20)
            self.set_text_color(226, 232, 240)
            self.text(28, 205, "DOCUMENTO DEMONSTRATIVO - SEM VALOR FISCAL")
        self.set_fill_color(*VERDE)
        self.rect(0, 0, 210, 30, "F")
        self.set_text_color(26, 46, 5)
        self.set_xy(14, 7)
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 7, _latin1(f"Portal B2B - {self.titulo}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, _latin1(f"Nº {self.numero}   |   Emitido em {data_hora(self.emitido_em)} (hora do módulo)"),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(38)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 6, _latin1("Modelo gerado pelo módulo de Logística (Grupo 5) para demonstração. "
                                "Não substitui documento fiscal. Página ") + str(self.page_no()), align="C")

    def secao(self, titulo: str):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*TEXTO)
        self.cell(0, 8, _latin1(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*VERDE)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)

    def campo(self, rotulo: str, valor):
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*CINZA)
        self.cell(52, 6.5, _latin1(rotulo))
        self.set_text_color(*TEXTO)
        self.set_font("Helvetica", "B", 9.5)
        self.multi_cell(0, 6.5, _latin1(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def assinatura(self, quem: str):
        self.ln(14)
        self.set_draw_color(*CINZA)
        x = self.get_x()
        self.line(x, self.get_y(), x + 80, self.get_y())
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*CINZA)
        self.cell(80, 6, _latin1(quem), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _rota(e: dict) -> str:
    return f"{e['origem_cidade']} - {e['origem_uf']}  ->  {e['destino_cidade']} - {e['destino_uf']}"


def gerar(tipo: str, e: dict, emitido_em: datetime) -> bytes:
    """Gera o PDF do documento `tipo` para a entrega `e` (linha completa da entrega)."""
    if tipo not in TIPOS:
        raise KeyError(tipo)
    if tipo == "comprovante-coleta" and e.get("coletada_em") is None:
        raise DocumentoIndisponivel("O comprovante de coleta só existe depois que a carga é coletada.")

    pdf = _Pdf(TIPOS[tipo], numero_do_documento(e["id"], tipo), emitido_em)
    pdf.add_page()
    transportadora = e.get("transportadora_nome") or e.get("transportadora_id")

    if tipo == "cte":
        pdf.secao("Partes")
        pdf.campo("Emitente (transportadora)", f"{transportadora} - contato {e.get('transportadora_telefone') or '-'}")
        pdf.campo("Remetente (fornecedor)", e["fornecedor_id"])
        pdf.campo("Destinatário (comprador)", e["comprador_id"])
        pdf.secao("Prestação do serviço")
        pdf.campo("Pedido", e["pedido_id"])
        pdf.campo("Percurso", _rota(e))
        pdf.campo("Distância", f"{Decimal(str(e['distancia_km'])):,.1f} km".replace(",", "_").replace(".", ",").replace("_", "."))
        pdf.campo("Valor do frete", moeda(e["preco_frete"]))
        pdf.campo("Prazo", f"{e['prazo_dias']} dias úteis (até {_data(e.get('prazo_prometido'))})")
        pdf.secao("Carga")
        pdf.campo("Produto", e["produto_nome"])
        pdf.campo("Peso", _peso(e["peso_kg"]))
        pdf.campo("Valor da carga", moeda(e["valor_carga"]))
        pdf.secao("Veículo")
        pdf.campo("Placa", e.get("veiculo_placa") or "a definir")
        pdf.campo("Motorista", e.get("motorista_nome") or "a definir")

    elif tipo == "romaneio":
        pdf.secao("Carga")
        pdf.campo("Pedido", e["pedido_id"])
        pdf.campo("Produto", e["produto_nome"])
        pdf.campo("Tipo de carga", e["tipo_carga"])
        pdf.campo("Peso total", _peso(e["peso_kg"]))
        pdf.campo("Percurso", _rota(e))
        pdf.campo("Coleta prevista", _data(e.get("coleta_prevista")))
        pdf.secao("Transporte")
        pdf.campo("Transportadora", transportadora)
        pdf.campo("Veículo", f"{e.get('veiculo_placa') or 'a definir'} ({e.get('veiculo_tipo') or '-'})")
        pdf.campo("Motorista", e.get("motorista_nome") or "a definir")
        pdf.assinatura("Conferente do fornecedor")

    elif tipo == "nota-fiscal":
        pdf.secao("Emitente e destinatário")
        pdf.campo("Emitente (fornecedor)", e["fornecedor_id"])
        pdf.campo("Destinatário (comprador)", e["comprador_id"])
        pdf.secao("Produtos")
        pdf.campo("Descrição", e["produto_nome"])
        pdf.campo("Quantidade", _peso(e["peso_kg"]))
        pdf.campo("Valor total", moeda(e["valor_carga"]))
        pdf.secao("Transporte")
        pdf.campo("Transportadora", transportadora)
        pdf.campo("Frete", f"{moeda(e['preco_frete'])} (por conta do comprador)")
        pdf.campo("Pedido", e["pedido_id"])

    else:  # comprovante-coleta
        pdf.secao("Coleta")
        pdf.campo("Pedido", e["pedido_id"])
        pdf.campo("Data e hora", _data(e["coletada_em"]))
        pdf.campo("Local", f"{e['origem_cidade']} - {e['origem_uf']}")
        pdf.campo("Produto", e["produto_nome"])
        pdf.campo("Peso", _peso(e["peso_kg"]))
        pdf.secao("Responsável pelo transporte")
        pdf.campo("Transportadora", transportadora)
        pdf.campo("Motorista", f"{e.get('motorista_nome') or '-'} (CNH {e.get('motorista_cnh_mascarada') or '-'})")
        pdf.campo("Veículo", e.get("veiculo_placa") or "-")
        pdf.assinatura("Motorista")
        pdf.assinatura("Responsável pelo armazém do fornecedor")

    return bytes(pdf.output())
