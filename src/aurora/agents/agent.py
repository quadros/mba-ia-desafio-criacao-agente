"""Ponto de entrada para depuração no adk web (expõe o root_agent).

    uv run adk web src/aurora/agents     # app "agents" (modo de agente único)

No adk web, crie a sessão com state {"apartamento": "101"}: sem ele as tools de
reservas e visitantes recusam a execução (apartamento_da_sessao).
"""

from aurora.agents import root_agent

__all__ = ["root_agent"]
