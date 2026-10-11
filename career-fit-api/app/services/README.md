# Services - Lógica de Negocio (Parcialmente Implementada)

## Visión general

Los servicios implementan la lógica de negocio compleja. Dependen de repositorios para acceso a datos.

```
API Endpoint
    ↓
Service (lógica de negocio)
    ↓
Repository (acceso a datos)
    ↓
Base de datos
```

Actualmente hay dos servicios stubs:
1. **LLM Services** — Integración con OpenAI/Groq
2. **CV Services** — Extracción y normalización de CVs

## LLM Services (app/services/llm/)

### Propósito
Proporcionar una abstracción sobre proveedores de LLM (Language Models). Desacopla la lógica de negocios del proveedor específico.

### Archivo: client.py

**Clase:** `LLMClient`

**Métodos stubs (TODO):**

#### `complete(messages, model=None, response_format=None) -> str`
Envía una solicitud de chat y devuelve la respuesta de texto.

**Parámetros:**
- `messages`: Lista de mensajes en formato OpenAI: `[{"role": "user", "content": "..."}]`
- `model`: Opcional, sobrescribe `settings.LLM_MODEL`
- `response_format`: Opcional, ej: `{"type": "json_object"}` para modo JSON

**Retorna:** String con la respuesta

**Implementación planeada:**
- Usar `httpx` (ya disponible) para llamar al endpoint (`settings.LLM_BASE_URL`)
- Soporte para proveedores OpenAI-compatibles (Groq, OpenAI, Anthropic)
- LiteLLM como fallback
- Reintentos con backoff exponencial (tenacity ya importado)
- Tracking de uso de tokens (para monitoreo de costo)
- Soporte streaming para parsing largo de CVs

**Ejemplo de uso (cuando se implemente):**
```python
from app.services.llm.client import LLMClient
from app.config import get_settings

client = LLMClient()
response = await client.complete(
    messages=[
        {"role": "system", "content": "Eres un experto en RH..."},
        {"role": "user", "content": "Extrae habilidades del CV: ..."}
    ],
    model="llama-3.1-70b-versatile"
)
print(response)  # "Python, PostgreSQL, AWS, ..."
```

#### `structured_output(messages, schema, model=None) -> dict`
Envía una solicitud y parsea la respuesta en un diccionario que cumple un JSON schema.

**Parámetros:**
- `messages`: Lista de mensajes
- `schema`: JSON schema que la respuesta debe cumplir
- `model`: Opcional

**Retorna:** Dict validado contra el schema

**Implementación planeada:**
- Usar JSON mode (OpenAI) o function calling para forzar estructura
- Validar respuesta contra schema antes de retornar
- Reintentos si la respuesta no cumple
- Tracking de tokens

**Ejemplo (cuando se implemente):**
```python
from app.services.llm.client import LLMClient
from app.services.cv.schemas import UserProfile

client = LLMClient()
profile = await client.structured_output(
    messages=[...],
    schema=UserProfile.model_json_schema(),
    model="llama-3.1-70b-versatile"
)
# Retorna dict como UserProfile (con skills, experience, education, etc.)
```

### Archivo: prompts.py

**Qué hace:** Define templates de prompts para tareas específicas.

**Templates (actualmente vacíos, TODO):**

```python
CV_EXTRACTION_PROMPT_TEMPLATE = ""  # EMPTY - TO DO

SKILL_NORMALIZATION_PROMPT_TEMPLATE = ""  # EMPTY - TO DO
```

**Funciones:**

#### `build_cv_extraction_prompt(cv_text: str) -> list[dict]`
Construye un prompt para extraer estructura del CV.

**Entrada:** Texto bruto de CV

**Salida:** Lista de mensajes en formato OpenAI:
```python
[
    {"role": "system", "content": "Eres un experto..."},
    {"role": "user", "content": "Extrae estructura del CV..."}
]
```

**Implementación planeada:**
- Usar `CV_EXTRACTION_PROMPT_TEMPLATE`
- Agregar few-shot examples (ejemplos de entrada/salida)
- Guiar al LLM a devolver JSON con estructura UserProfile

#### `build_skill_normalization_prompt(raw_skills: list[str]) -> list[dict]`
Construye un prompt para normalizar nombres de habilidades.

**Entrada:** Lista de skills crudas ["Python", "py", "PY", "node", "nodejs"]

**Salida:** Mensajes OpenAI

**Implementación planeada:**
- Usar `SKILL_NORMALIZATION_PROMPT_TEMPLATE`
- Pasar taxonomía de skills (desde BD)
- Pedir mapeo de raw → skills canónicas

### Archivo: schemas.py

**Esquemas internos (request/response del LLM, no expuestos en API):**

```python
class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class CompletionRequest(BaseModel):
    messages: list[LLMMessage]
    model: str
    response_format: dict | None
    temperature: float
    max_tokens: int

class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class CompletionResponse(BaseModel):
    content: str
    model: str
    usage: TokenUsage

class StructuredOutputRequest(BaseModel):
    messages: list[LLMMessage]
    schema_: dict  # JSON schema
    model: str

# TODO: más esquemas según se implemente
```

## CV Services (app/services/cv/)

### Propósito
Extraer y normalizar información de CVs. Convierte texto bruto en estructura normalizada.

### Archivo: extractor.py

**Clase:** `CVExtractor`

**Métodos stubs (TODO):**

#### `extract(cv_text: str) -> UserProfile`
Parsea CV en estructura normalizada.

**Entrada:** Texto bruto de CV (puede ser muy informal)

**Salida:** `UserProfile` (ver schemas.py)

**Implementación planeada:**
- Llama `app.services.llm.prompts.build_cv_extraction_prompt(cv_text)`
- Llama `LLMClient.structured_output()` con schema UserProfile
- Llama `self.normalize_skills()` sobre skills extraídas
- Maneja edge cases: sin skills, seniority ambiguo, secciones faltantes

**Ejemplo (cuando esté implementado):**
```python
from app.services.cv.extractor import CVExtractor

extractor = CVExtractor()
profile = await extractor.extract(cv_text)
# profile.skills = [Skill(name="Python", years_experience=5), ...]
# profile.experience = [ExperienceRecord(...), ...]
# profile.education = [Education(...), ...]
```

#### `normalize_skills(raw_skills: list[str]) -> list[Skill]`
Mapea nombres de skills crudos a canonical.

**Entrada:** ["Python", "py", "Django", "DRF", ...]

**Salida:** [Skill(name="Python", ...), Skill(name="Django", ...)]

**Implementación planeada:**
- Llamar `SkillNormalizer.normalize()` para cada skill
- Validar que existen en BD (o crear si se autoriza)
- Retornar lista de Skill objects

### Archivo: normalizer.py

**Clase:** `SkillNormalizer`

**Método (TODO):**

#### `normalize(raw_name: str) -> str | None`
Mapea un nombre de skill crudo al canónico.

**Entrada:** "python", "Py", "PY", "Python 3.11"

**Salida:** "Python" (o None si no es mapeable)

**Implementación planeada (MVP):**
1. Exact match en tabla Skill
2. Match en aliases de Skill
3. Fuzzy matching (similar names)
4. Later: embeddings para matching semántico

**Estrategia actual en código:**
```python
# TODO: MVP approach
# 1. Exact lookup in Skill.name
# 2. Alias lookup in Skill.aliases
# 3. Later: fuzzy matching / embeddings

class SkillNormalizer:
    def __init__(self, skills_repo: SkillRepository):  # Future DI
        self.skills = skills_repo
    
    def normalize(self, raw_name: str) -> str | None:
        # TODO: implement
        ...
```

### Archivo: schemas.py

**Esquemas para extracción y estructura de CV (internos, no API):**

```python
class Skill(BaseModel):
    name: str  # Canonical
    years_experience: float | None

class ExperienceRecord(BaseModel):
    company: str
    role: str
    start_date: date | None  # TODO: strategy para parsear free text
    end_date: date | None
    description: str | None
    skills_used: list[str]

class Education(BaseModel):
    institution: str
    degree: str  # "BS", "MS", etc.
    field_of_study: str
    end_date: date | None

class UserProfile(BaseModel):
    """Estructura extraída de un CV."""
    skills: list[Skill]
    experience: list[ExperienceRecord]
    roles: list[str]  # Puestos anteriores
    education: list[Education]
    languages: list[str]
    seniority: str  # REQUIRED - "junior", "mid", "senior", etc.
    industries: list[str]
    management_experience: bool

# TODO: date parsing strategy (free text vs strict ISO)
```

## Servicios Faltantes (NOT IMPLEMENTED)

Cuando se implemente `/v1/analyze`, estos servicios también serán necesarios:

### MatchingScorer
Calcula qué tan bien se ajusta un perfil a un rol objetivo.
- Input: Profile, target Job(s)
- Output: Market fit score (0-100)
- Lógica: Skill match + experience alignment + seniority + location

### SkillGapAnalyzer
Identifica qué skills faltan y prioriza por demanda × impacto × salario.
- Input: Profile, target role
- Output: list[SkillGap]

### SalaryEstimator
Estima salario usando percentiles de mercado o modelos ML.
- Input: Profile, target role, location
- Output: SalaryEstimate (p25, p50, p75)
- Datos: MarketSnapshot + SalaryObservation

### RecommendationEngine
Genera oportunidades desbloqueadas y rutas de carrera.
- Input: Profile, skill gaps, market data
- Output: UnlockedOpportunity[], CareerPath[]

## Patrón de inyección de dependencias

Los servicios deben recibir repositorios (no crearlos internamente).

```python
# ✓ CORRECTO
class CVExtractor:
    def __init__(self, skill_repo: SkillRepository):
        self.skills = skill_repo
    
    async def normalize_skills(self, raw_skills):
        return [
            await self.skills.get_by_name(raw)
            for raw in raw_skills
        ]

# ❌ INCORRECTO - Crea repo internamente
class CVExtractor:
    async def normalize_skills(self, raw_skills):
        session = get_session()  # NO - tight coupling
        repo = SkillRepository(session)
        ...
```

## Integración en endpoint

Cuando `/v1/analyze` se implemente:

```python
@router.post("/analyze")
async def analyze_cv(
    request: AnalyzeRequest,
    session: AsyncSession = Depends(get_session)
):
    # Instanciar servicios con inyección de dependencias
    extractor = CVExtractor(SkillRepository(session))
    scorer = MatchingScorer(JobRepository(session), SkillRepository(session))
    
    # 1. Extract profile from CV
    profile = await extractor.extract(request.cv)
    
    # 2. Query market data for target role
    jobs = await job_repo.get_by_title(request.target.role)
    
    # 3. Calculate fit
    market_fit = await scorer.score(profile, jobs)
    
    # 4. Identify gaps, salary, opportunities (servicios faltantes)
    
    # 5. Return analysis (session auto-commit at this level)
    return AnalyzeResponse(...)
```

## Configuración del LLM (desde app/config.py)

```python
LLM_PROVIDER: str = "groq"  # Provider a usar
LLM_API_KEY: str = ""  # Clave de API
LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
LLM_MODEL: str = "llama-3.1-70b-versatile"
LLM_TEMPERATURE: float = 0.1  # Determinístico (bajo)
LLM_MAX_TOKENS: int = 4000
LLM_TIMEOUT: float = 60.0  # Segundos
```

Para activar, coloca tu API key en `.env`:
```
LLM_API_KEY=your_groq_key_here
```

## Próximos pasos

1. Implementar `LLMClient.complete()` con httpx
2. Implementar `LLMClient.structured_output()` con JSON mode
3. Escribir prompts en `prompts.py`
4. Implementar `CVExtractor.extract()`
5. Implementar `SkillNormalizer.normalize()`
6. Crear servicios faltantes (MatchingScorer, etc.)
7. Implementar endpoint `/v1/analyze`

Ver:
- `app/README.md` — Arquitectura general
- `app/api/README.md` — Endpoint que consumirá estos servicios
- `app/repositories/README.md` — Cómo acceder a datos
