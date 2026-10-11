# Career Fit Intelligence API - Mapa General

## ¿Qué es esta aplicación?

Es una API que analiza el perfil profesional de una persona (CV) contra el mercado laboral actual para determinar:
- Qué tan bien se ajusta a un rol objetivo
- Qué habilidades le faltan
- Cuál sería su salario esperado
- Qué nuevas oportunidades se abrirían si aprende ciertas habilidades

La aplicación obtiene datos de empleos reales de Freehire, los normaliza y los almacena en PostgreSQL.

## Estructura de carpetas

```
app/
├── config.py              # Configuración central (DB URL, API keys, etc.)
├── database.py            # Conexión a PostgreSQL y sesiones
├── main.py                # FastAPI application factory
│
├── models/                # Tablas de base de datos (15 total)
│   ├── job.py            # Empleos del API de Freehire
│   ├── company.py        # Empresas
│   ├── skill.py          # Habilidades normalizadas
│   ├── role.py           # Roles/puestos normalizados
│   ├── salary_observation.py  # Observaciones salariales
│   ├── market_snapshot.py     # Agregaciones diarias del mercado
│   ├── profile.py        # Perfiles de usuarios
│   ├── analysis.py       # Análisis de usuarios
│   ├── job_skill.py      # Relación: empleo ↔ habilidad
│   ├── job_role.py       # Relación: empleo ↔ rol
│   └── ...
│
├── repositories/          # Capa de acceso a datos
│   ├── base.py           # BaseRepository (CRUD genérico)
│   ├── job_repo.py       # Repositorio para empleos
│   ├── skill_repo.py     # Repositorio para habilidades
│   ├── company_repo.py   # Repositorio para empresas
│   └── ...
│
├── api/                   # Endpoints HTTP
│   ├── routes/
│   │   ├── health.py     # GET /v1/health (verificación básica)
│   │   └── analyze.py    # POST /v1/analyze (análisis de CV)
│   └── schemas/
│       ├── request.py    # Esquemas de entrada (validación Pydantic)
│       └── response.py   # Esquemas de salida
│
├── services/              # Lógica de negocio (parcialmente implementada)
│   ├── llm/
│   │   ├── client.py     # Cliente LLM (Groq/OpenAI)
│   │   ├── prompts.py    # Templates de prompts
│   │   └── schemas.py    # Esquemas internos LLM
│   └── cv/
│       ├── extractor.py  # Extrae estructura del CV (stub)
│       ├── normalizer.py # Normaliza habilidades
│       └── schemas.py    # Esquemas de CV
│
└── ingestion/             # Pipeline de carga de datos de Freehire
    └── freehire/
        ├── client.py     # Cliente HTTP a API de Freehire
        ├── normalizer.py # Convierte registros brutos a nuestros modelos
        ├── upserter.py   # Inserta/actualiza en BD (idempotente)
        ├── scheduler.py  # Ejecutor diario
        └── snapshots/
            └── manager.py # Agregaciones diarias de mercado
```

## Cómo arranca la aplicación

1. **Punto de entrada:** `app/main.py` define `create_app()`, que es una función factory de FastAPI
2. **Lifespan (inicio/cierre):**
   - Al iniciar: `init_db()` crea todas las tablas en PostgreSQL
   - Al cerrar: `close_db()` libera la conexión
3. **Rutas (routers):**
   - `/v1/health` → `app/api/routes/health.py` (verificación)
   - `/v1/analyze` → `app/api/routes/analyze.py` (análisis principal, aún no implementado)
4. **Middleware:** CORS habilitado para todas las fuentes (restricción necesaria en producción)

## Convención de transacciones (Paso 11)

**Regla crítica:** Las transacciones son ATÓMICAS a nivel de sesión.

```
Usuario/Scheduler
    ↓
FastAPI request (crea sesión)
    ↓
Repositories (flush only, nunca commit)
    ↓
Services (flush only, nunca commit)
    ↓
Session owner: commit si OK, rollback si error
```

**Por qué:**
- Una sesión = una transacción = un cambio atómico en BD
- Los repositorios hacen `flush()` para enviar cambios sin confirmar
- El commit ocurre en UN SOLO LUGAR: la sesión que la crea
- Si algo falla, todo se deshace (rollback automático)

Ver `app/database.py::get_session()` para la implementación.

## Rol de config.py

Centraliza TODA la configuración:
- Base de datos (DATABASE_URL, pool size)
- API de Freehire (BASE_URL, timeouts)
- LLM (provider, API key, modelo)
- Análisis (profundidad, límites)
- Logging

Usa Pydantic Settings: lee `.env`, valida tipos, usa defaults.

```python
from app.config import get_settings
settings = get_settings()  # Instancia singleton
print(settings.DATABASE_URL)
```

## Rol de database.py

Gestiona la conexión a PostgreSQL:
- `get_engine()` → singleton AsyncEngine (conexión pool)
- `get_session_factory()` → singleton async_sessionmaker
- `get_session()` → dependency FastAPI (crea sesión + cierra automáticamente)
- `init_db()` → crea tablas (llamado al iniciar)
- `close_db()` → libera conexiones (llamado al cerrar)

SQLAlchemy 2.0 async (`asyncpg`).

## Próximos pasos documentados

Ver:
- `app/ingestion/README.md` — Flujo completo de carga de datos
- `app/models/README.md` — Qué guarda cada tabla
- `app/repositories/README.md` — Capa de acceso a datos
- `app/api/README.md` — Endpoints y esquemas
- `app/services/README.md` — Servicios (LLM, extracción CV)
