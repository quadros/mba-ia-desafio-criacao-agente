"""Runtime do ADK: serviço de sessão persistido, App e Runner (singletons)."""

from __future__ import annotations

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from sqlalchemy import event

from aurora.agents import root_agent
from aurora.config import APP_NAME, SESSIONS_DB_PATH


def _pragmas_sqlite(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def criar_session_service() -> DatabaseSessionService:
    # Garantia 3: sessões e eventos gravados em SQLite (var/sessions.db), num
    # arquivo separado do banco de domínio para não disputarem o mesmo lock.
    SESSIONS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    service = DatabaseSessionService(
        db_url=f"sqlite+aiosqlite:///{SESSIONS_DB_PATH}",
        connect_args={"timeout": 30},
    )
    event.listen(service.db_engine.sync_engine, "connect", _pragmas_sqlite)
    return service


session_service = criar_session_service()

# is_resumable=True: a resposta de uma confirmação retoma a invocação pausada e
# é entregue ao agente autor da chamada de tool (o especialista), inclusive
# depois de reiniciar a API, porque tudo o que o Runner usa para decidir está
# nos eventos persistidos.
app = App(
    name=APP_NAME,
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)

runner = Runner(app=app, session_service=session_service)
