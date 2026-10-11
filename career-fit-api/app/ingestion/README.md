# Ingestion - Pipeline de datos de Freehire

## Flujo general

```
API de Freehire
    ↓
Client (HTTP con reintentos)
    ↓
Normalizer (convierte datos brutos)
    ↓
Upserter (guarda en BD, idempotente)
    ↓
Market Snapshots (agregaciones diarias)
```

## Componentes

### 1. freehire/client.py - Cliente HTTP a Freehire

**Qué hace:** Obtiene empleos del API de Freehire con paginación y manejo de errores.

**Características:**
- Cliente async (`httpx.AsyncClient`)
- **Reintentos inteligentes:**
  - Errores transitorios: 429 (límite de rate), 503 (servicio no disponible), errores de red
  - Espera exponencial: 1-30 segundos entre intentos (tenacity)
  - Máximo 5 intentos antes de fallar
  
- **Seguridad:**
  - Rechaza números JSON no válidos (Infinity, -Infinity, NaN) — previene ataques
  - Límite de 10 MB por respuesta (previene OOM si upstream está comprometido)
  - Valida la estructura esperada: `{"data": [...], "meta": {...}}`

- **Paginación:**
  - API limita a 10k registros por consulta (offset + limit ≤ 10,000)
  - Dataset total: ~2M+ empleos, imposible descargar todo
  - Estrategia: consultas estrechas con filtros (ej: `posted_within_days=2`)

- **Filtros disponibles:**
  - `q`: búsqueda por texto
  - `skills`: filtrar por habilidades (comma-separated OR logic)
  - `countries`, `regions`, `cities`: ubicación
  - `salary_min`, `salary_max`: rango salarial
  - `experience_years_min`, `experience_years_max`: años experiencia
  - `posted_within_days`: empleos publicados hace N días (ventana incremental)
  - `visa_sponsorship`: si patrocina visa
  - `requires_clearance`: si requiere clearance
  - `sort`: `created_at`, `posted_at`, `view_count`, `salary_min`, `salary_max`
  - `order`: `asc` o `desc`

**Punto de entrada:** `search_jobs()` (una página) o `iter_jobs()` (iteración automática con paginación).

### 2. freehire/normalizer.py - Normalización de datos brutos

**Qué hace:** Convierte cada registro bruto del API a nuestros modelos (Job, Company, Skill, SalaryObservation).

**Principios:**
- **Nunca lanza excepciones:** Si algo está mal, devuelve `(None, skip_reason)` 
- **Tolerance a datos defectuosos:** Campos null, tipos inesperados, valores absurdos
- **Defensive:** sanitización, límites de largo, validación de rangos

**Decisiones críticas en normalización:**

| Decisión | Implementación | Por qué |
|----------|-----------------|--------|
| **Identidad de empleo** | `external_id` (único de Freehire) | Permite detectar duplicados y actualizaciones |
| **Identidad empresa** | `external_id = company_slug` fallback: slug del nombre | Normaliza nombres distintos de misma empresa |
| **Salarios anualizados** | Multiplica por período (hourly×2080, monthly×12, etc.) | Comparabilidad entre diferentes períodos |
| **Sin conversión moneda** | Guarda moneda original + valor | Datos multinacionales; conversión es análisis, no ingestion |
| **Cap de habilidades** | Máximo 50 habilidades por empleo | Previene tablas de Skill/JobSkill sin control |
| **Validación salarial** | 0 < annual < $100M | Rechaza salarios absurdos o negativos |
| **Sanitización** | Elimina caracteres NUL, reemplaza NaN/Inf con None | Entrada externa = untrusted |
| **Límites de columna** | Strings truncados según schema (ej: título ≤500 caracteres) | Previene errores de base de datos |

**Funciones principales:**
- `normalize_job(raw_dict)` → `(NormalizedRecord, skip_reason)` o `(None, skip_reason)`
- `NormalizedRecord` = contenedor con: job, company, skills, salary

**Skip reasons comunes:**
- `not_a_dict`: payload no es diccionario
- `missing_identity`: no tiene external_id ni slug
- `missing_title`: título vacío o faltante
- `missing_company`: sin empresa (algunas queries lo permiten, otras no)

### 3. freehire/upserter.py - Upsert idempotente

**Qué hace:** Inserta o actualiza registros en la BD garantizando idempotencia (ejecutar 2 veces = mismo resultado que 1 vez).

**Orden de operaciones por registro:**
1. Inserta o busca Company (cache per-run)
2. Inserta o busca Job (por `external_id`)
3. Para cada habilidad: inserta o busca Skill (cache per-run)
4. Relaciona Job ↔ Skill via JobSkill
5. Inserta SalaryObservation (una por job, source="posted")

**Idempotencia:**
- Job.external_id: único, UPDATE si existe
- Company.external_id (slug): único, reutiliza si existe
- Skill.name: único, reutiliza si existe
- JobSkill: (job_id, skill_id) único = aditivo, no duplica

**Savepoints por registro:**
```python
async with session.begin_nested():  # Transacción anidada (savepoint)
    # Upsert del registro
```
Si un registro falla, solo ése se deshace; el batch continúa. Evita "un registro malo = todo el batch se pierde".

**Stats:**
- `jobs_inserted`, `jobs_updated`, `jobs_skipped`
- `companies_created`, `skills_created`, `salaries_upserted`
- `skip_reasons`: dict con motivos de rechazo

### 4. freehire/scheduler.py - Ejecutor diario

**Qué hace:** Ejecuta la ingestion automáticamente cada día a una hora UTC fija.

**Configuración:**
- `INGESTION_DAILY_HOUR` (default: 3 = 3 AM UTC)
- Ciclo: esperar → ejecutar → logging → volver a empezar

**Puntos de entrada:**
- `run_ingestion_cycle()` → ejecuta una vez (manual o para tests)
- `run_scheduler()` → loop infinito (producción)

**Manejo de errores:**
- Excepciones en el ciclo se loguean pero se tragan (swallow)
- El loop continúa, reintenta al día siguiente
- Resiliente a outages transitorios de Freehire o BD

### 5. snapshots/manager.py - Agregaciones de mercado

**Qué hace:** Crea un `MarketSnapshot` diario con estadísticas agregadas.

**Agregaciones:**
- Total de empleos, total de empresas
- Top 50 empleos por habilidad (más demandadas)
- Top 50 empleos por ubicación (con más oportunidades)
- Distribución por modo de trabajo (remote/hybrid/onsite)
- Percentiles salariales (p25, p50, p75) por habilidad
- Percentiles salariales por ubicación

**Idempotencia:** Una snapshot por día. Re-ejecutar el mismo día = actualiza en lugar de duplicar.

## Ciclo manual (para testing/debugging)

```python
from app.database import get_session_factory
from app.ingestion.freehire.scheduler import run_ingestion_cycle

async def test():
    factory = get_session_factory()
    async with factory() as session:
        await run_ingestion_cycle(session)
        await session.commit()  # Confirmación manual aquí
```

## Decisiones de ingestion grounded en el código

Todas las decisiones anteriores están codificadas:

| Archivo | Línea | Decisión |
|---------|-------|----------|
| `normalizer.py:40` | `_PERIOD_TO_ANNUAL` | Multiplicadores de período a anual |
| `normalizer.py:34` | `_MAX_SKILLS_PER_JOB = 50` | Cap de habilidades |
| `normalizer.py:37` | `_MAX_ANNUAL_SALARY` | Límite salarial ($100M) |
| `client.py:40` | `MAX_RESPONSE_BYTES` | Límite 10 MB |
| `client.py:40` | `MAX_PAGINATION_DEPTH` | Cap 10k registros |
| `client.py:131-136` | `@retry(...)` | Reintentos con backoff exponencial |
| `upserter.py` (en línea con savepoints) | `async with session.begin_nested():` | Savepoint por registro |
| `scheduler.py:59` | `INGESTION_DAILY_HOUR` | Hora UTC fija |

## Flujo end-to-end: un ciclo completo

1. **Scheduler dispara** `run_ingestion_cycle()` a las 3 AM UTC
2. **Client itera empleos** via `iter_jobs(posted_within_days=2)` (últimas 48 horas)
3. **Normalizer procesa cada** diccionario bruto → `(NormalizedRecord, skip_reason)`
4. **Upserter persiste** con savepoints: Company → Job → Skills → Salary
5. **Stats acumulan** jobs_inserted, jobs_updated, jobs_skipped, skip_reasons
6. **SnapshotManager crea/actualiza** MarketSnapshot del día
7. **Session.commit()** confirma TODO (o rollback si algo falló)
8. **Logs** resumen: "Inserted 1234, Updated 567, Skipped 89 (reasons: ...)"
9. **Loop duerme** hasta mañana a las 3 AM

Entonces:
- BD tiene empleos frescos (máximo 48 horas de antigüedad)
- Análisis de usuarios (endpoint /analyze) consulta datos actuales
- Snapshots históricas permiten análisis temporal (tendencias)
