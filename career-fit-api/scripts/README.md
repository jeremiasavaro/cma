# Scripts - Herramientas de línea de comandos

Scripts operativos que se corren a mano, fuera del servidor FastAPI.

## ingest.py - Ingestion manual de Freehire

**Qué hace:** ejecuta **un ciclo completo de ingestion** por demanda, sin esperar
al scheduler diario (3 AM UTC). Usa exactamente el mismo pipeline que el
scheduler — `run_ingestion_cycle()` de [`app/ingestion/`](../app/ingestion/README.md):

```
API de Freehire → Client → Normalizer → Upserter → (Snapshot) → commit
```

El script solo traduce las opciones de línea de comandos a filtros de búsqueda,
configura el logging de consola y muestra el resumen final. Toda la lógica
pesada vive en `app/ingestion/`.

### Uso básico

```bash
uv run python scripts/ingest.py [opciones]
```

### Opciones

| Opción | Qué hace | Default |
|--------|----------|---------|
| `--q TEXTO` | Búsqueda por texto libre (como el buscador del sitio) | — |
| `--skills A,B,C` | Filtra por habilidades, separadas por coma (lógica OR: trae empleos con cualquiera de ellas) | — |
| `--country XX` | Filtra por código de país; se puede repetir (`--country US --country AR`) o separar por comas (`--country US,AR`) | — |
| `--days N` | Solo empleos publicados en los últimos N días | 2 (igual que el scheduler) |
| `--max-jobs N` | Corta después de ingerir N empleos (evita consultas gigantes) | 500 |
| `--no-snapshot` | No crea/actualiza el snapshot de mercado del día al final | snapshot activado |
| `-v`, `--verbose` | Logging en nivel DEBUG (muestra paginación y detalles del upsert) | INFO |

### Ejemplos reales

```bash
# Los empleos de los últimos 2 días (lo mismo que hace el scheduler cada noche)
uv run python scripts/ingest.py

# Empleos de Python o FastAPI de la última semana, con logs detallados
uv run python scripts/ingest.py --skills python,fastapi --days 7 -v

# Búsqueda por texto, limitada a 100 empleos, sin snapshot
uv run python scripts/ingest.py --q "backend engineer" --max-jobs 100 --no-snapshot

# Empleos de Estados Unidos y Argentina de los últimos 3 días
uv run python scripts/ingest.py --country US,AR --days 3
```

### Correr contra la base dockerizada

El `DATABASE_URL` por defecto apunta al host `db` (el nombre del servicio dentro
de Docker). Si corrés el script **desde tu máquina** (fuera de Docker), primero
levantá la base y apuntá a `localhost`:

```bash
# 1. Levantar solo PostgreSQL
docker compose -f docker/docker-compose.yml up -d db

# 2. Apuntar a la base desde fuera de Docker
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/career_fit

# 3. Correr la ingestion
uv run python scripts/ingest.py --days 2 -v
```

### Qué pasa al final

- Al terminar se imprime el resumen de `IngestionStats`: empleos insertados,
  actualizados, salteados (con los motivos), empresas y habilidades creadas, y
  salarios registrados.
- Salvo que pases `--no-snapshot`, también se crea o actualiza el
  `MarketSnapshot` del día (las agregaciones de mercado: top habilidades,
  ubicaciones, percentiles salariales).
- Todo el ciclo se confirma (commit) como una sola unidad: si algo falla, se
  deshace completo (rollback) y el script termina con código de salida 1.
  Si todo sale bien, el código de salida es 0.

### Relación con `app/ingestion/`

Este script es solo la "cáscara" de línea de comandos. Los detalles del pipeline
(reintentos HTTP, normalización defensiva, upsert idempotente, savepoints,
snapshots) están documentados en el
[README de ingestion](../app/ingestion/README.md).
