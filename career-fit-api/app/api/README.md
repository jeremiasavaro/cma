# API - Endpoints y Esquemas

## Endpoints actuales

### 1. GET /v1/health

**Propósito:** Verificar que la API y la BD están funcionando.

**Request:** Ninguno (GET sin body).

**Response (200):**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

**Qué verifica:**
- La API está corriendo
- La conexión a PostgreSQL funciona (ejecuta `SELECT 1`)

**Uso:** Health checks (Kubernetes, uptime monitoring, etc.)

**Archivo:** `app/api/routes/health.py`

### 2. POST /v1/analyze (NO IMPLEMENTADO)

**Propósito:** Analizar un CV contra un rol objetivo usando datos de mercado.

**Request body:**
```json
{
  "cv": "Full CV text (min 100 chars)...",
  "target": {
    "role": "Senior Backend Engineer",
    "location": "Buenos Aires, Argentina",
    "work_mode": "remote",
    "seniority": "senior",
    "skills": ["Python", "PostgreSQL", "AWS"]
  },
  "analysis": {
    "level": "full",
    "include_salary": true,
    "include_skill_gaps": true,
    "include_unlocked_opportunities": true,
    "include_career_paths": false,
    "include_salary_premiums": true
  }
}
```

**Response (200):**
```json
{
  "market_fit": {
    "current": 65.5,
    "potential": 82.3,
    "breakdown": {
      "skill_match": 70,
      "experience_match": 60,
      "location_fit": 65,
      "seniority_alignment": 68
    }
  },
  "skill_gaps": [
    {
      "skill": "Kubernetes",
      "priority": 1,
      "market_demand": 450,
      "match_impact": 12.5,
      "learning_time_months": 2
    }
  ],
  "salary": {
    "current": {
      "p25": 40000,
      "p50": 50000,
      "p75": 65000
    },
    "target": {
      "p25": 65000,
      "p50": 80000,
      "p75": 100000
    }
  },
  "salary_premiums": [
    {
      "skill": "Kubernetes",
      "delta": 8000
    }
  ],
  "unlocked_opportunities": [
    {
      "company": "TechCorp",
      "role": "Principal Backend Engineer",
      "salary_range": "90000-120000",
      "fit_score": 78
    }
  ],
  "career_paths": [
    {
      "role": "Tech Lead",
      "sequence": ["Learn Kubernetes", "Mentor juniors"],
      "timeline_months": 12
    }
  ],
  "confidence": {
    "market_fit": "high",
    "salary_estimate": "medium",
    "skill_gaps": "high"
  }
}
```

**Response (501):** Aún no implementado.

**Archivo:** `app/api/routes/analyze.py`

## Esquemas (app/api/schemas/)

### request.py - Validación de entrada

**Enums:**

```python
class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"

class Seniority(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"

class AnalysisLevel(str, Enum):
    BASIC = "basic"        # Rápido, score básico
    STANDARD = "standard"  # Balance
    FULL = "full"          # Detallado, con recomendaciones
```

**Modelos:**

#### TargetRole
```python
class TargetRole(BaseModel):
    role: str  # "Senior Backend Engineer"
    location: str | None = None  # "Buenos Aires, Argentina"
    work_mode: WorkMode | None = None
    seniority: Seniority | None = None
    skills: list[str] = []  # Skills que buscamos en el rol
```

#### AnalysisConfig
```python
class AnalysisConfig(BaseModel):
    level: AnalysisLevel = AnalysisLevel.FULL
    include_salary: bool = True
    include_skill_gaps: bool = True
    include_unlocked_opportunities: bool = True
    include_career_paths: bool = False
    include_salary_premiums: bool = True
```

#### AnalyzeRequest
```python
class AnalyzeRequest(BaseModel):
    cv: str  # min 100 caracteres
    target: TargetRole
    analysis: AnalysisConfig = AnalysisConfig()  # Default si no se proporciona
```

### response.py - Esquemas de salida

**Modelos:**

#### MarketFit
```python
class MarketFit(BaseModel):
    current: float  # 0-100, qué tan bien se ajusta ahora
    potential: float  # 0-100, si aprende skills críticas
    breakdown: dict[str, float]  # Componentes: skill_match, experience_match, ...
```

#### SkillGap
```python
class SkillGap(BaseModel):
    skill: str
    priority: int  # 1=crítica, 5=baja
    market_demand: int  # Cuántos empleos requieren esta skill
    match_impact: float  # Cuánto subiría el fit (0-100)
    learning_time_months: int
```

#### SalaryEstimate
```python
class SalaryEstimate(BaseModel):
    p25: int  # Percentil 25 (anual, USD)
    p50: int  # Mediana
    p75: int  # Percentil 75
```

#### SalaryPremium
```python
class SalaryPremium(BaseModel):
    skill: str
    delta: int  # Delta salarial (USD) si posee la skill
```

#### UnlockedOpportunity
```python
class UnlockedOpportunity(BaseModel):
    company: str
    role: str
    salary_range: str  # "90000-120000"
    fit_score: float  # 0-100
```

#### CareerPath
```python
class CareerPath(BaseModel):
    role: str
    sequence: list[str]  # Pasos ("Learn Kubernetes", "Mentor juniors")
    timeline_months: int
```

#### AnalyzeResponse
```python
class AnalyzeResponse(BaseModel):
    market_fit: MarketFit
    skill_gaps: list[SkillGap]
    salary: dict[str, SalaryEstimate]  # {"current": {...}, "target": {...}}
    salary_premiums: list[SalaryPremium]
    unlocked_opportunities: list[UnlockedOpportunity]
    career_paths: list[CareerPath]
    confidence: dict[str, str]  # {"market_fit": "high", ...}
```

## Cómo agregar un nuevo endpoint

1. **Crear archivo en `app/api/routes/`:**
   ```python
   from fastapi import APIRouter
   
   router = APIRouter(tags=["your_feature"])
   
   @router.get("/your-endpoint")
   async def your_endpoint(...):
       """Descripción clara."""
       pass
   ```

2. **Definir esquemas si es necesario:**
   - Inputs en `app/api/schemas/request.py`
   - Outputs en `app/api/schemas/response.py`

3. **Registrar en `app/main.py`:**
   ```python
   from app.api.routes import your_feature
   
   app.include_router(your_feature.router, prefix=settings.API_PREFIX)
   ```

4. **Usar dependencias FastAPI:**
   ```python
   @router.get("/jobs/{job_id}")
   async def get_job(
       job_id: int,
       session: AsyncSession = Depends(get_session)
   ):
       # session maneja commit/rollback automáticamente
       repo = JobRepository(session)
       job = await repo.get_by_id(job_id)
       return job
   ```

## Validación automática (Pydantic)

FastAPI + Pydantic validan tipos y rangos automáticamente.

```python
# Invalid request → 422 Unprocessable Entity
POST /v1/analyze
{
  "cv": "short",  # < 100 chars → ERROR
  "target": {
    "role": "Backend Engineer",
    "work_mode": "invalid"  # No en WorkMode enum → ERROR
  }
}
```

## Error handling

Global exception handler en `app/main.py`:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )
```

**En producción (DEBUG=False):** Los errores internos se ocultan, solo se retorna mensaje genérico.

**En desarrollo (DEBUG=True):** Se retorna el traceback completo.

## CORS

Configurado en `app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Restringir en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**En producción:** Cambiar a:
```python
allow_origins=[
    "https://yourdomain.com",
    "https://app.yourdomain.com",
]
```

## Documentación automática

FastAPI genera docs automáticamente:
- Swagger UI: `/docs` (si `DEBUG=True`)
- ReDoc: `/redoc` (si `DEBUG=True`)

En producción (`DEBUG=False`), estos se desactivan por seguridad.

## Pruebas de endpoint

```bash
# Health check
curl http://localhost:8000/v1/health

# Análisis (aún 501)
curl -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"cv": "Long CV text...", "target": {"role": "..."}}'
```

## Próximos pasos documentados

Ver:
- `app/services/README.md` — Servicios que procesan lógica (aún stubs)
- `app/models/README.md` — Esquemas de BD detrás de estos modelos Pydantic
