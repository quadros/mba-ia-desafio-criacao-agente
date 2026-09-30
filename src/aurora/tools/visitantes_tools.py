"""Tools do especialista de visitantes (apartamento sempre vindo da sessão)."""

from __future__ import annotations

from typing import Any

from google.adk.tools import FunctionTool, ToolContext

from aurora.domain import repositorio as repo
from aurora.tools.contexto import apartamento_da_sessao, confirmacao_aprovada


def listar_meus_visitantes(tool_context: ToolContext) -> dict[str, Any]:
    """Lista os visitantes autorizados do apartamento do morador desta conversa."""
    apto = apartamento_da_sessao(tool_context)
    return {"status": "ok", "visitantes": repo.listar_visitantes(apto)}


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict[str, Any]:
    """Autoriza a entrada de um visitante no prédio numa data.

    Chame esta tool diretamente quando o morador pedir. O próprio sistema
    sempre pede a confirmação ao morador pelo aplicativo; não peça
    confirmação na conversa.

    Args:
        nome: nome completo do visitante.
        data: data da visita no formato AAAA-MM-DD.
    """
    apto = apartamento_da_sessao(tool_context)
    nome = " ".join((nome or "").split())
    if not 3 <= len(nome) <= 80:
        return {"status": "dados_invalidos", "mensagem": "Informe o nome completo do visitante."}
    if not repo.data_valida(data):
        return {"status": "dados_invalidos", "mensagem": "Data inválida. Use AAAA-MM-DD."}
    # Trava final da Garantia 1: liberar acesso só com aprovação do sistema.
    if not confirmacao_aprovada(tool_context):
        return {"status": "recusada", "mensagem": "A autorização não foi confirmada."}

    await repo.autorizar_visitante(apto, nome, data, call_id=tool_context.function_call_id)
    return {
        "status": "autorizado",
        "nome": nome,
        "data": data,
        "mensagem": "Entrada liberada. O morador já confirmou; nada mais a confirmar.",
    }


listar_meus_visitantes_tool = FunctionTool(listar_meus_visitantes)
# Regra 3: autorizar visitante libera acesso, então pede confirmação sempre.
autorizar_visitante_tool = FunctionTool(autorizar_visitante, require_confirmation=True)

TOOLS_VISITANTES = [listar_meus_visitantes_tool, autorizar_visitante_tool]
