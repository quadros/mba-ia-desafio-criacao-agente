"""Acesso ao contexto da sessão a partir das tools."""

from __future__ import annotations

import unicodedata
from typing import Optional

from google.adk.tools import ToolContext

# Chave do state da sessão com o apartamento do morador autenticado. Ela é
# gravada uma única vez, em POST /sessoes (aurora.api.routes_sessoes), e
# nenhuma tool escreve nela.
CHAVE_APTO = "apartamento"


class SessaoSemApartamento(RuntimeError):
    """A sessão não foi criada pela API (não tem apartamento no state)."""


def apartamento_da_sessao(tool_context: ToolContext) -> str:
    """Apartamento dono da sessão, lido do state; nunca de um argumento do modelo."""
    apto = tool_context.state.get(CHAVE_APTO)
    if not apto or not isinstance(apto, str):
        raise SessaoSemApartamento("Sessão sem apartamento: crie a sessão pela API.")
    return apto


def confirmacao_aprovada(tool_context: ToolContext) -> bool:
    """True só quando esta chamada foi aprovada pela rota de confirmações."""
    conf = tool_context.tool_confirmation
    return conf is not None and conf.confirmed is True


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


_ALIASES_AREA = {
    "salao-de-festas": "salao-de-festas",
    "salao de festas": "salao-de-festas",
    "salao": "salao-de-festas",
    "salao_de_festas": "salao-de-festas",
    "churrasqueira": "churrasqueira",
    "churrasco": "churrasqueira",
    "quadra": "quadra",
    "quadra poliesportiva": "quadra",
    "quadra-poliesportiva": "quadra",
}


def normalizar_area(area: Optional[str]) -> Optional[str]:
    """Converte o que o modelo escreveu no id da área ('salão' -> 'salao-de-festas')."""
    if not area or not isinstance(area, str):
        return None
    return _ALIASES_AREA.get(_sem_acento(area), _sem_acento(area))


def traduzir_recusa(tool, args, tool_context: ToolContext, tool_response):
    """after_tool_callback: deixa inequívoco para o modelo que o morador negou.

    Quando a confirmação é negada, o ADK devolve só {"error": "This tool call is
    rejected."}, que o modelo pode confundir com "data indisponível" e repetir
    em pedidos seguintes. Nada é executado em nenhum dos casos.
    """
    conf = tool_context.tool_confirmation
    if conf is not None and not conf.confirmed:
        return {
            "status": "negada_pelo_morador",
            "mensagem": (
                "O morador NEGOU a confirmação no aplicativo; nada foi feito. "
                "Isto não significa indisponibilidade. Se ele pedir de novo, "
                "chame a tool novamente."
            ),
        }
    return None
