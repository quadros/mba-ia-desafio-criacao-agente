"""Tools do especialista de reservas.

Nenhuma tool recebe o apartamento como parâmetro: ele vem sempre do state da
sessão (apartamento_da_sessao). Os retornos nunca trazem dono ou código de
reservas de outros apartamentos.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import FunctionTool, ToolContext

from aurora.domain import repositorio as repo
from aurora.tools.contexto import (
    apartamento_da_sessao,
    confirmacao_aprovada,
    normalizar_area,
)

_MSG_INDISPONIVEL = "A área não está disponível nessa data."


def _validar(area: str, data: str) -> tuple[str | None, float | None, dict | None]:
    """Normaliza a área e valida área e data. Devolve (area_id, taxa, erro)."""
    area_id = normalizar_area(area)
    taxa = repo.taxa(area_id) if area_id else None
    if taxa is None:
        validas = ", ".join(a["id"] for a in repo.listar_areas())
        return None, None, {
            "status": "area_invalida",
            "mensagem": f"Área desconhecida. Áreas válidas: {validas}.",
        }
    if not repo.data_valida(data):
        return None, None, {
            "status": "data_invalida",
            "mensagem": "Data inválida. Use o formato AAAA-MM-DD.",
        }
    return area_id, taxa, None


def listar_minhas_reservas(tool_context: ToolContext) -> dict[str, Any]:
    """Lista as reservas ativas do apartamento do morador desta conversa.

    Não recebe apartamento: o sistema já sabe quem é o morador.
    """
    apto = apartamento_da_sessao(tool_context)
    return {"status": "ok", "reservas": repo.listar_reservas(apto)}


def verificar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict[str, Any]:
    """Informa se uma área comum está livre numa data. Não revela de quem é a reserva.

    Args:
        area: id da área: 'salao-de-festas', 'churrasqueira' ou 'quadra'.
        data: data no formato AAAA-MM-DD.
    """
    apartamento_da_sessao(tool_context)
    area_id, taxa, erro = _validar(area, data)
    if erro:
        return erro
    return {
        "status": "ok",
        "area": area_id,
        "data": data,
        "disponivel": not repo.data_ocupada(area_id, data),
        "taxa": taxa,
    }


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict[str, Any]:
    """Reserva uma área comum para o morador desta conversa na data informada.

    Chame esta tool diretamente quando o morador pedir uma reserva. Se a área
    tiver taxa, o próprio sistema pede a confirmação ao morador pelo
    aplicativo; não peça confirmação na conversa.

    Args:
        area: id da área: 'salao-de-festas', 'churrasqueira' ou 'quadra'.
        data: data da reserva no formato AAAA-MM-DD.
    """
    apto = apartamento_da_sessao(tool_context)
    area_id, taxa, erro = _validar(area, data)
    if erro:
        return erro

    conf = tool_context.tool_confirmation
    if conf is not None and not conf.confirmed:
        return {"status": "recusada", "mensagem": "O morador não confirmou a reserva."}

    if taxa > 0 and not confirmacao_aprovada(tool_context):
        # Trava final da Garantia 1, dentro da própria função: reserva com
        # cobrança nunca é gravada sem uma confirmação aprovada. Só chega aqui
        # quando _precisa_confirmar_reserva viu a data ocupada.
        if repo.data_ocupada(area_id, data):
            return {"status": "indisponivel", "mensagem": _MSG_INDISPONIVEL}
        return {
            "status": "confirmacao_necessaria",
            "mensagem": "Esta reserva gera cobrança. Chame reservar_area novamente.",
        }

    r = await repo.criar_reserva(apto, area_id, data, call_id=tool_context.function_call_id)
    if r.status == "indisponivel":
        return {"status": "indisponivel", "mensagem": _MSG_INDISPONIVEL}
    return {
        "status": "criada",
        "codigo": r.codigo,
        "area": area_id,
        "data": data,
        "cobranca": r.cobranca,
        "mensagem": "Reserva registrada. Se havia cobrança, o morador já confirmou; nada mais a confirmar.",
    }


def _precisa_confirmar_reserva(area: str, data: str, **_: Any) -> bool:
    """Regra 2: pede confirmação quando a reserva gera cobrança (taxa > 0).

    Se a data já está ocupada não há o que cobrar: a tool roda e recusa sem
    pedir confirmação (e sem dizer de quem é a reserva).
    """
    area_id = normalizar_area(area)
    taxa = repo.taxa(area_id) if area_id else None
    if not taxa or not repo.data_valida(data):
        return False
    return not repo.data_ocupada(area_id, data)


async def cancelar_minha_reserva(
    tool_context: ToolContext,
    area: str = "",
    data: str = "",
    codigo: str = "",
) -> dict[str, Any]:
    """Cancela uma reserva do próprio morador desta conversa. Não pede confirmação.

    Informe a área e a data da reserva, ou o código dela. Só reservas do
    apartamento do morador podem ser canceladas.

    Args:
        area: id da área: 'salao-de-festas', 'churrasqueira' ou 'quadra'.
        data: data da reserva no formato AAAA-MM-DD.
        codigo: código da reserva, se o morador informar.
    """
    apto = apartamento_da_sessao(tool_context)
    area_id = normalizar_area(area) if area else None
    if data and not repo.data_valida(data):
        return {"status": "data_invalida", "mensagem": "Data inválida. Use AAAA-MM-DD."}
    if not (area_id or data or codigo):
        return {"status": "dados_insuficientes", "mensagem": "Informe área e data, ou o código."}

    r = await repo.cancelar_reserva(apto, area=area_id, data=data or None, codigo=codigo or None)
    if r["status"] == "nao_encontrada":
        # Mesma resposta para "não existe" e "é de outro apartamento".
        return {
            "status": "nao_encontrada",
            "mensagem": "Não encontrei reserva sua com esses dados.",
        }
    return r


listar_minhas_reservas_tool = FunctionTool(listar_minhas_reservas)
verificar_disponibilidade_tool = FunctionTool(verificar_disponibilidade)
reservar_area_tool = FunctionTool(reservar_area, require_confirmation=_precisa_confirmar_reserva)
cancelar_minha_reserva_tool = FunctionTool(cancelar_minha_reserva)

TOOLS_RESERVAS = [
    listar_minhas_reservas_tool,
    verificar_disponibilidade_tool,
    reservar_area_tool,
    cancelar_minha_reserva_tool,
]
