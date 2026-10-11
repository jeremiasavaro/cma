# Repositories - Capa de Acceso a Datos

## ¿Qué es un repositorio?

Un repositorio es la capa que se comunica con la base de datos. Es el ÚNICO lugar donde se hace SQL (via SQLAlchemy).

**Regla de oro:** Los servicios NO hablan directamente con SQLAlchemy. Usan repositorios.

```
API/Service
    ↓
Repository (conoce SQL, conoce el modelo)
    ↓
SQLAlchemy + PostgreSQL
```

**Beneficio:** Cambiar de BD (PostgreSQL → MySQL) solo requiere reescribir repositorios, no toda la app.

## BaseRepository - CRUD genérico

Archivo: `app/repositories/base.py`

**Qué hace:** Implementa CRUD básico para cualquier modelo SQLAlchemy.

```python
class BaseRepository(Generic[ModelType]):
    """Generic async CRUD para un modelo SQLAlchemy."""
    
    async def get_by_id(id: int) -> ModelType | None
    async def list(limit=50, offset=0) -> list[ModelType]
    async def create(**kwargs) -> ModelType
    async def update(instance, **kwargs) -> ModelType
    async def delete(instance) -> None
```

**Nota sobre transacciones:** Todos los métodos hacen `flush()`, NUNCA `commit()`.

- `flush()` = envía cambios SQL pendientes a PostgreSQL sin confirmar la transacción
- `commit()` = confirma. Ocurre UNA SOLA VEZ, en el propietario de la sesión

Ver `app/database.py::get_session()` donde el commit ocurre.

### Métodos base

#### `get_by_id(id: int)`
Obtiene un registro por PK.
```python
job = await job_repo.get_by_id(123)
# Devuelve Job o None
```

#### `list(limit: int = 50, offset: int = 0)`
Pagina registros.
```python
jobs = await job_repo.list(limit=10, offset=0)  # Primeros 10
jobs = await job_repo.list(limit=10, offset=10)  # Siguientes 10
```

#### `create(**kwargs)`
Crea un nuevo registro.
```python
job = await job_repo.create(
    title="Backend Engineer",
    location="Buenos Aires",
    company_id=5
)
# Ya tiene ID (se hizo refresh automático)
```

#### `update(instance, **kwargs)`
Actualiza un registro ya cargado.
```python
job = await job_repo.get_by_id(123)
job = await job_repo.update(job, title="Senior Backend Engineer")
```

#### `delete(instance)`
Elimina un registro.
```python
job = await job_repo.get_by_id(123)
await job_repo.delete(job)
```

## Repositorios Concretos

### 1. JobRepository (app/repositories/job_repo.py)

Extiende `BaseRepository[Job]`.

**Métodos extra:**
- `get_by_external_id(external_id: str)` → `Job | None`
  - Busca por el ID único de Freehire
  - Usado en ingestion para detectar duplicados (upsert)

### 2. SkillRepository (app/repositories/skill_repo.py)

Extiende `BaseRepository[Skill]`.

**Métodos extra:**
- `get_by_name(name: str)` → `Skill | None`
  - Busca por nombre canónico (normalmente lowercase)
  - Usado para normalización e ingestion

### 3. CompanyRepository (app/repositories/company_repo.py)

Extiende `BaseRepository[Company]`.

**Métodos extra:**
- `get_by_external_id(external_id: str)` → `Company | None`
  - Busca por slug de empresa
  - Usado en ingestion para reutilizar empresas

### 4. ProfileRepository (app/repositories/profile_repo.py)

Extiende `BaseRepository[Profile]`.

**Métodos extra:**
- `get_by_user_id(user_id: str)` → `Profile | None`
  - Busca el perfil de un usuario específico
  - Cada usuario tiene 0 o 1 perfil

### 5. AnalysisRepository (app/repositories/analysis_repo.py)

Extiende `BaseRepository[Analysis]`.

**Métodos extra:**
- `get_by_profile_id(profile_id: int)` → `list[Analysis]`
  - Obtiene todos los análisis de un usuario
  - Útil para historial

### 6. RoleRepository (app/repositories/role_repo.py)

Extiende `BaseRepository[Role]`.

**Métodos extra:**
- `get_by_name(name: str)` → `Role | None`
  - Busca por nombre canónico de rol
  - Normalización similar a skills

## Patrón de uso en código

### En ingestion (freehire/upserter.py)

```python
class FreehireUpserter:
    def __init__(self, session: AsyncSession):
        self.jobs = JobRepository(session)
        self.companies = CompanyRepository(session)
        self.skills = SkillRepository(session)
    
    async def upsert_batch(self, raw_jobs):
        for raw in raw_jobs:
            # Buscar o crear empresa
            company = await self.companies.get_by_external_id(
                raw["company_slug"]
            )
            if not company:
                company = await self.companies.create(
                    external_id=raw["company_slug"],
                    name=raw["company_name"]
                )
            
            # Buscar o crear empleo (por external_id = upsert)
            job = await self.jobs.get_by_external_id(raw["id"])
            if job:
                job = await self.jobs.update(job, title=raw["title"], ...)
            else:
                job = await self.jobs.create(
                    external_id=raw["id"],
                    title=raw["title"],
                    company_id=company.id,
                    ...
                )
```

### En un endpoint (api/routes/analyze.py, cuando esté implementado)

```python
@router.post("/analyze")
async def analyze_cv(
    request: AnalyzeRequest,
    session: AsyncSession = Depends(get_session)
):
    # Session maneja commit/rollback automáticamente
    profile_repo = ProfileRepository(session)
    
    # Buscar perfil del usuario
    profile = await profile_repo.get_by_user_id(user_id)
    if not profile:
        # Crear uno nuevo
        profile = await profile_repo.create(
            user_id=user_id,
            full_name=request.cv_info.name,
            ...
        )
    
    # Análisis (aún no implementado)
    analysis = await analysis_repo.create(
        profile_id=profile.id,
        target_role=request.target.role,
        market_fit_score=calculate_fit(...)
    )
    
    # Aquí la sesión hace commit automáticamente (get_session)
    return analysis
```

## Composición de repositorios en servicios

Los servicios dependen de repositorios, no de SQLAlchemy directo.

```python
class MatchingScorer:
    """Calcula qué tan bien se ajusta un perfil a un empleo."""
    
    def __init__(self, job_repo: JobRepository, skill_repo: SkillRepository):
        self.jobs = job_repo
        self.skills = skill_repo
    
    async def score(self, profile: Profile, target_role: str) -> float:
        # Buscar empleos con el rol objetivo
        jobs = await self.jobs.get_by_title(target_role)  # (hypothetical)
        
        # Calcular score según matching de skills
        score = 0.0
        for skill in profile.skills:
            # Buscar demanda en el mercado
            ...
        return score
```

## Transacciones: La regla de oro

**Paso 11 (desde el código):**

```
Repositorio:   flush()  → SQL push sin confirmar
Servicio:      flush()  → SQL push sin confirmar
Session owner: commit() → CONFIRMACIÓN REAL
              rollback() → DESHACER TODO
```

**Ejemplo:** Si en una transacción:
1. `CompanyRepository.create()` → flush ✓
2. `JobRepository.create()` → flush ✓
3. `SkillRepository.create()` → ERROR

Entonces:
- BD ve cambios 1 y 2 enviados (flushed) pero NO confirmados (not committed)
- SQLAlchemy rollback automático → BD vuelve a estado inicial
- Cliente recibe error, BD está limpia (no hay estado intermedio)

**NO HACER en repositorio:**
```python
await session.commit()  # ❌ PROHIBITED
```

**HACER:**
```python
await session.flush()   # ✓ OK
```

## Caching per-run en upserter

El upserter es el único que carea una excepción: hace caching local para no re-queryar lo mismo N veces por batch.

```python
class FreehireUpserter:
    def __init__(self, session):
        self._company_cache: dict[str, Company] = {}  # Cache local
        self._skill_cache: dict[str, Skill] = {}
    
    async def upsert_batch(self, raw_jobs):
        for raw in raw_jobs:
            company_slug = raw["company_slug"]
            # Antes: consultar BD
            if company_slug in self._company_cache:
                company = self._company_cache[company_slug]
            else:
                company = await self.companies.get_by_external_id(...)
                if company:
                    self._company_cache[company_slug] = company
                # ... crear si no existe
```

**Ventaja:** En un batch de 500 empleos, evita 400+ queries redundantes a la misma empresa.

## Queries personalizadas

A veces necesitas algo más complejo que CRUD base.

```python
class JobRepository(BaseRepository[Job]):
    async def get_by_title_and_location(
        self,
        title: str,
        location: str
    ) -> list[Job]:
        """Busca empleos por título y ubicación."""
        result = await self.session.execute(
            select(Job).where(
                (Job.title.ilike(f"%{title}%")) &
                (Job.location.ilike(f"%{location}%"))
            )
        )
        return list(result.scalars().all())
```

**Nota:** `ilike` = case-insensitive LIKE (PostgreSQL).

## Próximos pasos

Ver:
- `app/database.py` — Cómo se crean/cierran sesiones
- `app/models/README.md` — Qué campos tiene cada tabla
- `app/ingestion/README.md` — Ejemplo real de uso (upserter)
