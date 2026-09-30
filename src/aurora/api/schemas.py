"""Modelos de entrada e saída da API (contrato do enunciado)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CriarSessaoIn(BaseModel):
    apartamento: str = Field(min_length=1, max_length=10)


class CriarSessaoOut(BaseModel):
    session_id: str


class MensagemIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


class ConfirmacaoIn(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    confirmado: bool


class Pendente(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class RespostaOut(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[Pendente]


class ReservaOut(BaseModel):
    codigo: str
    area: str
    data: str


class VisitanteOut(BaseModel):
    nome: str
    data: str
