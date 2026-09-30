"""Aplicação FastAPI e comando de subida (uv run aurora-api)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from aurora.api.routes_sessoes import router as router_sessoes
from aurora.api.routes_verificacao import router as router_verificacao
from aurora.infra.seed import semear_se_vazio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Só cria o schema e semeia um banco novo; nunca restaura dados existentes.
    semear_se_vazio()
    yield


app = FastAPI(title="Residencial Aurora — assistente virtual", lifespan=lifespan)
app.include_router(router_sessoes)
app.include_router(router_verificacao)


def run() -> None:
    uvicorn.run("aurora.main:app", host="0.0.0.0", port=8000)
