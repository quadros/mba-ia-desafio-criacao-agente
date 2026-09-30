"""Confirmações pendentes, derivadas dos eventos persistidos da sessão.

Não existe estado em memória: uma confirmação está pendente enquanto a sessão
tem uma FunctionCall 'adk_request_confirmation' sem a FunctionResponse de mesmo
id. Por isso a lista sobrevive a reinícios e uma confirmação já respondida
deixa de ser aceita (409) sem nenhum controle extra.
"""

from __future__ import annotations

from typing import Any

from google.adk.flows.llm_flows.functions import REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
from google.adk.sessions import Session

from aurora.api.schemas import Pendente
from aurora.domain import repositorio as repo
from aurora.tools.contexto import normalizar_area


def _detalhes(acao: str, args: dict[str, Any]) -> dict[str, Any]:
    if acao == "reservar_area":
        area = normalizar_area(args.get("area")) or args.get("area")
        return {"area": area, "data": args.get("data"), "taxa": repo.taxa(area or "")}
    if acao == "autorizar_visitante":
        nome = " ".join(str(args.get("nome") or "").split())
        return {"nome": nome, "data": args.get("data")}
    return dict(args)


def listar_pendentes(session: Session) -> list[Pendente]:
    chamadas: dict[str, Any] = {}
    respondidas: set[str] = set()
    for ev in session.events:
        for fc in ev.get_function_calls():
            if fc.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME and fc.id:
                chamadas[fc.id] = fc
        for fr in ev.get_function_responses():
            if fr.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME and fr.id:
                respondidas.add(fr.id)

    pendentes = []
    for cid, fc in chamadas.items():
        if cid in respondidas:
            continue
        original = (fc.args or {}).get("originalFunctionCall") or {}
        acao = original.get("name") or "desconhecida"
        pendentes.append(
            Pendente(id=cid, acao=acao, detalhes=_detalhes(acao, original.get("args") or {}))
        )
    return pendentes


def chamada_original(session: Session, confirmacao_id: str) -> tuple[str | None, str | None]:
    """(id, nome) da chamada de tool que a confirmação `confirmacao_id` protege."""
    for ev in session.events:
        for fc in ev.get_function_calls():
            if fc.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME and fc.id == confirmacao_id:
                original = (fc.args or {}).get("originalFunctionCall") or {}
                return original.get("id"), original.get("name")
    return None, None


def tool_executou_apos_aprovacao(session: Session, id_original: str) -> bool:
    """True se a tool original respondeu de novo depois do pedido de confirmação.

    A primeira FunctionResponse com esse id é a do pedido de confirmação; se a
    aprovação chegou ao agente certo, a tool roda e grava uma segunda.
    """
    respostas = sum(
        1 for ev in session.events for fr in ev.get_function_responses() if fr.id == id_original
    )
    return respostas >= 2
