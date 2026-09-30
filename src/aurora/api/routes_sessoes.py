"""Rotas de conversa: sessões, mensagens, confirmações e eventos."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from google.adk.flows.llm_flows.functions import REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
from google.adk.sessions import Session
from google.genai import types

from aurora.api.confirmacoes import (
    chamada_original,
    listar_pendentes,
    tool_executou_apos_aprovacao,
)
from aurora.api.schemas import (
    ConfirmacaoIn,
    CriarSessaoIn,
    CriarSessaoOut,
    MensagemIn,
    RespostaOut,
)
from aurora.config import APP_NAME, USER_ID
from aurora.infra.db import conectar
from aurora.runtime import runner, session_service
from aurora.tools.contexto import CHAVE_APTO

logger = logging.getLogger("aurora.api")
router = APIRouter()

# Um lock por sessão (não global): serializa requisições da mesma sessão sem
# impedir que sessões diferentes rodem em paralelo (Garantia 5, passo 14).
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

_MSG_FALHA = (
    "Desculpe, não consegui concluir o atendimento agora. Tente novamente em instantes."
)


async def _sessao_ou_404(session_id: str) -> Session:
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada.")
    return session


def _apartamento_existe(numero: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM apartamentos WHERE numero = ?", (numero,)).fetchone() is not None


async def _executar(session_id: str, mensagem: types.Content) -> tuple[RespostaOut, Session]:
    """Roda o Runner com a mensagem e monta a resposta no formato do contrato.

    `resposta` junta só o texto dos eventos de agentes desta invocação que não
    carregam chamadas nem respostas de tool; fica "" quando a execução parou
    esperando confirmação.
    """
    textos: list[str] = []
    try:
        async for ev in runner.run_async(
            user_id=USER_ID, session_id=session_id, new_message=mensagem
        ):
            if ev.author == "user" or ev.partial or not ev.content:
                continue
            if ev.get_function_calls() or ev.get_function_responses():
                continue
            for part in ev.content.parts or []:
                if part.text and not part.thought:
                    textos.append(part.text.strip())
    except Exception:  # noqa: BLE001 - nunca devolver 500 por falha do modelo
        logger.exception("Falha ao executar o agente na sessão %s", session_id)
        textos.append(_MSG_FALHA)

    session = await _sessao_ou_404(session_id)
    resposta = RespostaOut(
        resposta="\n\n".join(t for t in textos if t),
        confirmacoes_pendentes=listar_pendentes(session),
    )
    return resposta, session


@router.post("/sessoes", status_code=status.HTTP_201_CREATED, response_model=CriarSessaoOut)
async def criar_sessao(body: CriarSessaoIn) -> CriarSessaoOut:
    apartamento = body.apartamento.strip()
    if not _apartamento_existe(apartamento):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Apartamento inexistente.")
    # Garantia 2: único ponto em que o apartamento entra na sessão. Ele representa
    # o morador autenticado e é o que todas as tools usam dali em diante.
    session = await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state={CHAVE_APTO: apartamento}
    )
    return CriarSessaoOut(session_id=session.id)


@router.post("/sessoes/{session_id}/mensagens", response_model=RespostaOut)
async def enviar_mensagem(session_id: str, body: MensagemIn) -> RespostaOut:
    await _sessao_ou_404(session_id)
    async with _locks[session_id]:
        # Texto do morador é sempre só texto: nunca vira FunctionResponse, então
        # "já estou confirmando" não aprova nada (Garantia 1).
        mensagem = types.Content(role="user", parts=[types.Part(text=body.texto)])
        resposta, _ = await _executar(session_id, mensagem)
        return resposta


@router.post("/sessoes/{session_id}/confirmacoes", response_model=RespostaOut)
async def responder_confirmacao(session_id: str, body: ConfirmacaoIn) -> RespostaOut:
    await _sessao_ou_404(session_id)
    async with _locks[session_id]:
        # Garantia 1: só aceita um id que esteja pendente NESTA sessão, conferido
        # nos eventos persistidos. Id inexistente, de outra sessão ou já
        # respondido recebe 409 e o Runner nem é chamado.
        session = await _sessao_ou_404(session_id)
        if body.id not in {p.id for p in listar_pendentes(session)}:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Não existe confirmação pendente com esse id nesta sessão.",
            )
        id_original, acao = chamada_original(session, body.id)
        # Único lugar do sistema que cria a resposta a uma confirmação.
        resposta = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=body.id,
                        name=REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
                        response={"confirmed": body.confirmado},
                    )
                )
            ],
        )
        saida, session = await _executar(session_id, resposta)
        # Sintoma da "armadilha silenciosa": a aprovação foi aceita, mas a
        # resposta não chegou ao agente que pediu a confirmação e a tool não rodou.
        if body.confirmado and id_original and not tool_executou_apos_aprovacao(session, id_original):
            logger.warning(
                "Confirmação %s aprovada na sessão %s, mas %s não foi executada.",
                body.id, session_id, acao,
            )
        return saida


@router.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list[dict]:
    session = await _sessao_ou_404(session_id)
    return [ev.model_dump(mode="json", exclude_none=True, by_alias=True) for ev in session.events]

