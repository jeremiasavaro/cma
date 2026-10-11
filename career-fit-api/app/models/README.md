# Models - Las 15 tablas de base de datos

## Visión general

La base de datos está dividida en 3 dominios:

1. **Mercado laboral** (Freehire): jobs, companies, skills, roles, salaries, snapshots
2. **Perfiles de usuarios**: profiles, profile skills, profile experience
3. **Análisis**: analyses, analysis skill gaps, analysis salaries, analysis recommendations

## Las 15 tablas

### Dominio 1: Mercado Laboral (9 tablas)

#### 1. **jobs** (app/models/job.py)
**Qué guarda:** Empleos individuales del API de Freehire.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK, autoincrement |
| external_id | string(100) | ID único de Freehire, source de idempotencia |
| title | string(500) | Título del puesto |
| description | text | Descripción completa |
| location | string(200) | "Remote", "Buenos Aires, Argentina", etc. |
| work_mode | string(20) | "remote", "hybrid", "onsite" |
| company_id | int FK | → companies.id |
| posted_at | datetime | Cuándo se publicó |
| source_url | string(1000) | URL al posting original |
| raw_data | JSONB | Respuesta completa del API (para reprocessing) |
| created_at | datetime | Cuándo se insertó en nuestra BD |
| updated_at | datetime | Última actualización |

**Índices:** `(title, location)`, `(company_id, posted_at)`, `(work_mode, posted_at)`

**Relaciones:**
- `company: Company` (muchos employos → 1 empresa)
- `skills: list[JobSkill]` (many-to-many via JobSkill)
- `roles: list[JobRole]` (many-to-many via JobRole)
- `salary_observations: list[SalaryObservation]` (1 empleo → muchas salaries)

#### 2. **companies** (app/models/company.py)
**Qué guarda:** Empresas que publican empleos.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK, autoincrement |
| external_id | string(300) | company_slug de Freehire (único) |
| name | string(300) | Nombre de empresa |
| description | text | Descripción de empresa |
| website | string(500) | URL del sitio web |
| headquarters | string(200) | Ubicación principal |
| industry | string(100) | Industria (Tech, Finance, etc.) |
| company_size | string(50) | "1-10", "11-50", "50-250", etc. |
| raw_data | JSONB | Datos adicionales de Freehire |
| created_at | datetime | |
| updated_at | datetime | |

**Índices:** external_id (único)

**Relaciones:**
- `jobs: list[Job]` (1 empresa → muchos empleos)

#### 3. **skills** (app/models/skill.py)
**Qué guarda:** Habilidades normalizadas (diccionario único de skills).

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK, autoincrement |
| name | string(200) | Nombre canónico ("Python", "React", "AWS") |
| category | string(50) | "programming", "framework", "cloud", "database", "tool", "soft" |
| aliases | JSONB array | Variantes ["py", "python3.11", ...] |
| description | text | Qué es esta habilidad |
| is_active | boolean | Si se usa actualmente en el mercado |
| raw_data | JSONB | Metadata adicional |
| created_at | datetime | |
| updated_at | datetime | |

**Índices:** `name` (único), `(category, is_active)`

**Relaciones:**
- `job_skills: list[JobSkill]` (many-to-many)
- `profile_skills: list[ProfileSkill]` (many-to-many)

**Propósito:** Garantizar que "Python", "py", "python3" mapeen a la misma habilidad canónica. Facilita comparación entre demanda de mercado y habilidades de usuario.

#### 4. **roles** (app/models/role.py)
**Qué guarda:** Roles/puestos normalizados.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK, autoincrement |
| name | string(200) | Nombre canónico ("Backend Engineer", "Data Scientist") |
| category | string(100) | "engineering", "data", "product", "sales", etc. |
| level | string(50) | "junior", "mid", "senior", "lead", "principal" |
| aliases | JSONB array | Variantes ["Back-end Engineer", "Server-side Engineer"] |
| description | text | |
| is_active | boolean | |
| raw_data | JSONB | |
| created_at | datetime | |
| updated_at | datetime | |

**Índices:** `name` (único)

**Relaciones:**
- `job_roles: list[JobRole]` (many-to-many)
- `profile_roles: list[ProfileRole]` (many-to-many)

#### 5. **job_skill** (app/models/job_skill.py)
**Qué guarda:** Relación entre empleos y habilidades requeridas.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| job_id | int FK | → jobs.id |
| skill_id | int FK | → skills.id |
| confidence | float | 0.0-1.0, confianza que se requiere esta skill |
| is_required | boolean | Skill mandatoria vs. nice-to-have |
| source | string(100) | "posted" (del posting), "llm" (extraído por IA) |

**Índices:** `(job_id, skill_id)` (único), `(skill_id, job_id)`

**Relaciones:**
- `job: Job` (many)
- `skill: Skill` (many)

#### 6. **job_role** (app/models/job_role.py)
**Qué guarda:** Relación entre empleos y roles.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| job_id | int FK | → jobs.id |
| role_id | int FK | → roles.id |
| confidence | float | 0.0-1.0, qué tan bien mapea este empleo al rol |
| source | string(100) | "posted", "llm" |

**Índices:** `(job_id, role_id)` (único)

#### 7. **salary_observation** (app/models/salary_observation.py)
**Qué guarda:** Datos salariales extraídos de postings.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| job_id | int FK | → jobs.id |
| min_salary | decimal | Mínimo anual (en USD si possible) |
| max_salary | decimal | Máximo anual |
| median_salary | decimal | Mediana (si se proporciona) |
| currency | string(10) | "USD", "ARS", etc. (no se convierte) |
| period | string(20) | "yearly" (almacenamos todo como anual) |
| source | string(100) | "posted" (del posting), etc. |
| confidence | float | 0.0-1.0, confianza del dato |
| raw_data | JSONB | Datos salariales originales |
| created_at | datetime | |
| updated_at | datetime | |

**Relaciones:**
- `job: Job` (many → 1)

#### 8. **market_snapshot** (app/models/market_snapshot.py)
**Qué guarda:** Snapshot diario del mercado laboral (agregaciones).

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| date | date | Día del snapshot (único) |
| total_jobs | int | Total de empleos en el mercado ese día |
| total_companies | int | Número de empresas activas |
| jobs_by_skill | JSONB | Top 50 habilidades más demandadas |
| jobs_by_location | JSONB | Top 50 ubicaciones |
| jobs_by_work_mode | JSONB | Conteos por remote/hybrid/onsite |
| salary_by_skill | JSONB | Percentiles (p25, p50, p75) por skill |
| salary_by_location | JSONB | Percentiles por location |
| created_at | datetime | |
| updated_at | datetime | |

**Propósito:** Análisis histórico (tendencias del mercado) sin re-agregar cada vez.

### Dominio 2: Perfiles de Usuarios (5 tablas)

#### 9. **profiles** (app/models/profile.py)
**Qué guarda:** Perfil de usuario.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| user_id | string | ID del usuario (de sistema auth externo) |
| email | string(300) | Email |
| full_name | string(300) | Nombre completo |
| current_role | string(200) | Puesto actual |
| current_company | string(300) | Empresa actual |
| target_roles | JSONB array | Roles que aspira |
| salary_expectations | JSONB | Rango salarial esperado |
| raw_data | JSONB | CV o datos adicionales |
| created_at | datetime | |
| updated_at | datetime | |

**Índices:** user_id (único)

**Relaciones:**
- `skills: list[ProfileSkill]` (many-to-many)
- `experience: list[ProfileExperience]` (1 → many)
- `analyses: list[Analysis]` (1 → many)

#### 10. **profile_skill** (app/models/profile_skill.py)
**Qué guarda:** Habilidades del usuario con proficiencia.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| profile_id | int FK | → profiles.id |
| skill_id | int FK | → skills.id |
| proficiency | int | 1-5 (scale) |
| years_experience | float | Años usando esta skill |
| is_primary | boolean | Skill principal vs. secundaria |
| source | string(100) | "cv" (extraído de CV), "form" (ingresado manualmente) |
| created_at | datetime | |

**Índices:** `(profile_id, skill_id)` (único)

#### 11. **profile_experience** (app/models/profile_experience.py)
**Qué guarda:** Experiencia laboral del usuario.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| profile_id | int FK | → profiles.id |
| company | string(300) | Nombre empresa |
| role | string(200) | Título del puesto |
| role_id | int FK | → roles.id (rol normalizado, nullable) |
| start_date | date | |
| end_date | date | |
| description | text | Descripción de responsabilidades |
| skills_used | JSONB array | Habilidades usadas |
| created_at | datetime | |

**Propósito:** Mapear experiencia a roles normalizados. Usado para matching.

### Dominio 3: Análisis (2 tablas + 3 detalles)

#### 12. **analyses** (app/models/analysis.py)
**Qué guarda:** Resultado de un análisis de usuario vs. rol objetivo.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| profile_id | int FK | → profiles.id |
| target_role | string(200) | Rol objetivo (ej: "Senior Backend Engineer") |
| target_location | string(200) | Ubicación objetivo |
| market_fit_score | float | 0-100, qué tan bien se ajusta |
| analysis_level | string(50) | "basic", "standard", "full" |
| raw_response | JSONB | Respuesta completa |
| created_at | datetime | |

**Relaciones:**
- `skill_gaps: list[AnalysisSkillGap]` (1 → many)
- `salaries: list[AnalysisSalary]` (1 → many)
- `recommendations: list[AnalysisRecommendation]` (1 → many)

#### 13. **analysis_skill_gap** (app/models/analysis_skill_gap.py)
**Qué guarda:** Habilidades que faltan en el usuario para el rol objetivo.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| analysis_id | int FK | → analyses.id |
| skill_name | string(200) | Nombre de la habilidad |
| priority_score | float | 1.0 = crítica, 0.1 = opcional |
| market_demand | int | Cuántos empleos requieren esta skill |
| match_impact | float | Cuánto mejoraría el fit si la aprende |
| estimated_learning_time | int | Meses estimados para dominar |

#### 14. **analysis_salary** (app/models/analysis_salary.py)
**Qué guarda:** Estimaciones salariales.

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| analysis_id | int FK | → analyses.id |
| scenario | string(100) | "current", "target", "stretched" |
| p25_salary | decimal | Percentil 25 |
| p50_salary | decimal | Mediana |
| p75_salary | decimal | Percentil 75 |
| method | string(100) | "percentile" (del mercado), "model" (ML), "rule" |
| confidence | float | Confianza de la estimación |

#### 15. **analysis_recommendation** (app/models/analysis_recommendation.py)
**Qué guarda:** Recomendaciones de acción (aprender skills, cambiar roles, etc.).

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int | PK |
| analysis_id | int FK | → analyses.id |
| type | string(100) | "skill_to_learn", "role_transition", "location_move" |
| target_name | string(300) | Qué aprender/cambiar |
| fit_score_delta | float | Cuánto subiría el fit si lo hace |
| priority | int | 1 (crítica) a 5 (baja) |
| estimated_time | int | Meses para lograrlo |

## Relaciones visualizadas

```
Mercado Laboral
───────────────────
Job
  ├─ Company (N:1) — qué empresa publica el empleo
  ├─ JobSkill (1:N) — qué skills requiere
  │   └─ Skill (1:N)
  ├─ JobRole (1:N) — qué roles se clasifica como
  │   └─ Role (1:N)
  └─ SalaryObservation (1:N) — datos salariales

MarketSnapshot — agregaciones diarias de lo anterior


Usuario & Análisis
──────────────────
Profile
  ├─ ProfileSkill (1:N) — skills del usuario
  │   └─ Skill (1:N)
  ├─ ProfileExperience (1:N) — historial laboral
  │   └─ Role (1:N) [role_id normalizado]
  └─ Analysis (1:N) — análisis realizados
      ├─ AnalysisSkillGap (1:N)
      ├─ AnalysisSalary (1:N)
      └─ AnalysisRecommendation (1:N)
```

## Convenciones de base de datos

1. **Timestamps:** Siempre `created_at` (no se cambia) + `updated_at` (se actualiza)
2. **Soft deletes:** No implementados; deletions son hard (CASCADE donde sea necesario)
3. **Lazy loading:** Todas las relaciones usan `lazy="selectin"` (eager, N+1-safe)
4. **Cascade:** Jobs, Experiences, Skills deletes = cascada a sus relaciones
5. **Índices:** Judiciosamente agregados para queries comunes (skill-by-name, job-by-external_id)
6. **JSONB:** Para datos semi-estructurados (raw_data, agregaciones de snapshot)
7. **Herencia:** Todas las tablas heredan de `Base` (app/database.py::Base)

## Queries comunes

**Empleos con todas sus skills:**
```python
job = await session.get(Job, job_id)
# job.skills ya está cargado (lazy="selectin")
for job_skill in job.skills:
    print(job_skill.skill.name, job_skill.confidence)
```

**Empresas + sus empleos:**
```python
company = await session.get(Company, company_id)
# company.jobs ya está cargado
```

**Snapshot: datos de mercado por ubicación:**
```python
snapshot = await manager.get_today_snapshot(session)
top_locations = snapshot.jobs_by_location[:10]
salaries_in_sf = snapshot.salary_by_location.get("San Francisco")
```

Ver `app/repositories/README.md` para operaciones CRUD de bajo nivel.
