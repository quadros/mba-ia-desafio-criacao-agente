"""Rotas de verificação: leem o banco direto, sem passar pelo modelo."""

from __future__ import annotations

from fastapi import APIRouter

from aurora.api.schemas import ReservaOut, VisitanteOut
from aurora.domain import repositorio as repo

router = APIRouter()


@router.get("/apartamentos/{numero}/reservas", response_model=list[ReservaOut])
def reservas_do_apartamento(numero: str) -> list[dict]:
    return repo.listar_reservas(numero)


@router.get("/apartamentos/{numero}/visitantes", response_model=list[VisitanteOut])
def visitantes_do_apartamento(numero: str) -> list[dict]:
    return repo.listar_visitantes(numero)
