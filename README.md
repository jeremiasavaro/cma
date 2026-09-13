# Career Fit Intelligence API

**An intelligence layer over the job market.** Not another job board — a system that tells you exactly how your profile fits a target role, what gaps you have, and what's worth learning next.

## What It Is

You give it your CV and a target role. It analyzes real job postings and tells you:

- **Market Fit Score** — how compatible your current profile is with the target role
- **Skill gaps** — what you're missing, ranked by priority and market demand
- **Salary estimation** — what the market pays for this role (with confidence intervals)
- **Salary premiums** — which skills command higher pay
- **Unlocked opportunities** — how many more jobs become available if you learn a specific skill
- **Career paths** — possible evolution toward other roles you might not have considered

The analysis comes from **3.3M+ real job postings** across 205K+ companies and 80+ ATS platforms, aggregated by [Freehire](https://freehire.me).

### What It Is NOT

This is not a job board. Freehire already solves job collection and normalization. This API sits on top of that data as an **intelligence layer** — it answers "how do I fit?" instead of "what jobs exist?"

### Key Design Principle

**LLM only for unstructured text. Statistics for everything else.**

The LLM (Groq / Llama 3.1) is used exclusively for understanding unstructured data — extracting a structured profile from your free-text CV. All numbers (fit scores, salary estimates, skill demand, premiums) come from statistical models and reproducible database queries. This keeps results deterministic and auditable.

## Features

| Feature | Description |
|---------|-------------|
| CV → Structured Profile | Parse free-text CV into skills, experience, education |
| Market Fit Score | Current fit (0–1) and potential fit if gaps are filled |
| Skill Gap Analysis | Missing skills with market frequency, importance, and learning time |
| Salary Estimation | P25 / median / P75 with confidence level and sample size |
| Skill Salary Premiums | Which skills increase salary and by how much |
| Unlocked Opportunities | Jobs unlocked per new skill acquired |
| Career Paths | Alternative roles with market fit and required gaps |
| Temporal Snapshots | Historical data enables trend analysis (skill demand, salary evolution) |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     API (FastAPI)                       │
│               POST /v1/analyze                         │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │   LLM Pipeline      │    │  Statistical Engine   │
    │  (CV → Profile)     │    │  (Scores, Gaps, $)   │
    │  Groq / Llama 3.1   │    │  scikit-learn, etc.   │
    └──────────┬──────────┘    └──────────┬──────────┘
               │                          │
    ┌──────────▼──────────────────────────▼──────────┐
    │              PostgreSQL + pgvector              │
    │   Jobs, Profiles, Skills, Salaries, Snapshots  │
    └──────────────────────┬─────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   Ingestion Worker      │
              │   Freehire API → DB     │
              │   Daily snapshots       │
              └─────────────────────────┘
```

**Layers:**

- **`api/`** — Routes and request/response schemas (Pydantic)
- **`services/`** — Business logic (CV parsing, matching, salary estimation)
- **`repositories/`** — Data access layer (database queries)
- **`models/`** — SQLAlchemy ORM models (database tables)
- **`ml/`** — Trained models for salary prediction and matching
- **`ingestion/`** — Freehire API client and daily snapshot worker

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Validation | Pydantic v2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL + pgvector (vector search) |
| Migrations | Alembic |
| HTTP client | httpx (for Freehire API) |
| Data processing | pandas / polars |
| ML | scikit-learn, LightGBM, XGBoost |
| Embeddings | sentence-transformers (local, no API key) |
| NLP | spaCy |
| LLM | Groq (Llama 3.1 70B) via OpenAI-compatible API |
| Scheduler | APScheduler (daily ingestion) |
| Caching | Redis |
| Package manager | uv |
| Containers | Docker Compose |
| Linting | ruff + mypy |
| Testing | pytest + pytest-asyncio |

## Project Structure

```
career-fit-api/
├── app/
│   ├── config.py              # Pydantic Settings (reads .env)
│   ├── database.py            # SQLAlchemy async engine + sessions
│   ├── main.py                # FastAPI factory, lifespan, CORS
│   ├── api/
│   │   ├── routes/            # health.py, analyze.py
│   │   └── schemas/           # request.py, response.py
│   ├── models/                # ORM models (job, skill, salary, etc.)
│   ├── services/              # Business logic (to be implemented)
│   ├── repositories/          # Data access (to be implemented)
│   ├── ml/                    # Trained models (to be implemented)
│   ├── ingestion/             # Freehire ingestion worker (to be implemented)
│   └── utils/                 # Shared utilities
├── tests/                     # Unit + integration tests
├── alembic/                   # Database migrations
├── docker/
│   ├── Dockerfile             # Multi-stage (dev + production)
│   ├── Dockerfile.worker      # Ingestion worker image
│   └── docker-compose.yml     # Local dev environment
├── scripts/                   # Utility scripts
├── .env.example               # Environment variable template
├── .gitignore
└── pyproject.toml             # Dependencies + tool config
```

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A free [Groq API key](https://console.groq.com) (for CV extraction)

### 1. Clone and configure

```bash
git clone <repo-url>
cd career-fit-api

# Create your .env from the example
cp .env.example .env

# Edit .env and add your Groq API key
# LLM_API_KEY=gsk_your_key_here
```

### 2. Start the stack

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts:

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | FastAPI application |
| Docs | http://localhost:8000/docs | Swagger UI (dev mode only) |
| DB | localhost:5432 | PostgreSQL + pgvector |
| Redis | localhost:6379 | Cache / future queues |
| Worker | — | Background ingestion (daily) |

### 3. Verify it's running

```bash
curl http://localhost:8000/v1/health
# {"status":"healthy","database":"connected"}
```

### 4. Try an analysis

```bash
curl -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "cv": "Senior backend engineer with 8 years of experience in Python, Django, and PostgreSQL. Worked at fintech companies building payment systems and REST APIs. BSc in Computer Science.",
    "target": {
      "role": "Senior Backend Engineer",
      "location": "Remote",
      "seniority": "senior",
      "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"]
    }
  }'
```

> **Note:** The `/v1/analyze` endpoint returns `501 Not Implemented` until the services layer is built. The scaffolding and schemas are ready — the core logic needs to be implemented.

## API Reference

### `GET /v1/health`

Health check. Verifies API and database connectivity.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### `POST /v1/analyze`

Main analysis endpoint. Receives a CV and target role, returns a full market analysis.

**Request body:**
```json
{
  "cv": "Full CV text (minimum 100 characters)",
  "target": {
    "role": "Target role title",
    "location": "Country or city (optional)",
    "work_mode": "remote | hybrid | onsite (optional)",
    "seniority": "junior | mid | senior | lead | principal (optional)",
    "skills": ["Required", "skills", "(optional)"]
  },
  "analysis": {
    "level": "basic | standard | full",
    "include_salary": true,
    "include_skill_gaps": true,
    "include_unlocked_opportunities": true,
    "include_career_paths": false,
    "include_salary_premiums": true
  }
}
```

**Response (planned):**
```json
{
  "profile_id": "...",
  "target_role": "Senior Backend Engineer",
  "market_fit": {
    "current": 0.72,
    "potential": 0.94,
    "breakdown": { "skills": 0.8, "experience": 0.9, "seniority": 0.7 }
  },
  "skill_gaps": [
    {
      "skill": "Kubernetes",
      "market_frequency": 0.35,
      "importance": "medium",
      "priority": 0.6,
      "estimated_learning_weeks": 8
    }
  ],
  "salary": {
    "currency": "USD",
    "p25": 120000,
    "median": 145000,
    "p75": 170000,
    "confidence": "high",
    "sample_size": 1200
  },
  "salary_premiums": [
    { "skill": "Kubernetes", "premium_pct": 12.5, "confidence": "high", "sample_size": 800 }
  ],
  "unlocked_opportunities": [
    { "skill": "Kubernetes", "additional_compatible_jobs": 340, "relative_increase": 0.18 }
  ],
  "career_paths": [],
  "confidence": { "overall": "high", "salary": "high" },
  "metadata": { "job_postings_analyzed": 5000 },
  "analyzed_at": "2026-09-11T12:00:00Z"
}
```

### Notes on the Market Fit Score

The score is a **market compatibility index**, not a "probability of hiring." The dataset contains job postings, not hiring outcomes. The score tells you how well your profile matches what the market is asking for — not whether a specific company would hire you.

All statistics include **confidence intervals** with sample sizes, so you know how reliable each number is.

## Data Source

### Freehire

The API uses [Freehire](https://freehire.me) as its data source — an open-source project that aggregates job postings from ATS (Applicant Tracking System) platforms.

- **3.3M+** job postings
- **205K+** companies
- **80+** ATS platforms
- API: `https://freehire.me/api/v1/jobs` (keyless)

### Snapshot Strategy

The ingestion worker runs **daily** and:

1. Fetches new/updated postings from Freehire
2. Normalizes data (skills, roles, salaries)
3. Upserts into the local PostgreSQL database
4. Creates daily snapshots for temporal analysis

This enables:
- Skill demand trends over time
- Salary evolution tracking
- Role market changes

## Development

### Local setup (without Docker)

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy env file
cp .env.example .env
# Edit .env with your database URL and Groq API key

# Run the API
uvicorn app.main:app --reload

# Run tests
pytest

# Lint and type check
ruff check app/
mypy app/
```

### Useful commands

```bash
# Start only the database (for local dev)
docker compose -f docker/docker-compose.yml up db redis -d

# View logs
docker compose -f docker/docker-compose.yml logs -f app

# Stop everything
docker compose -f docker/docker-compose.yml down

# Reset database (deletes all data)
docker compose -f docker/docker-compose.yml down -v
```

### Adding a new feature

1. Define schemas in `app/api/schemas/` (request + response)
2. Create route in `app/api/routes/`
3. Add ORM models in `app/models/` if needed
4. Implement business logic in `app/services/`
5. Add data access in `app/repositories/`
6. Write tests in `tests/`
7. Run `alembic revision --autogenerate -m "description"` for migrations

## Status

| Component | Status |
|-----------|--------|
| Project scaffolding | Done |
| Configuration (pydantic-settings) | Done |
| Database (SQLAlchemy async + pgvector) | Done |
| ORM models | Done |
| API routes + schemas | Done |
| Docker setup | Done |
| Health endpoint | Done |
| **Analyze endpoint** | **Not implemented** (returns 501) |
| Services layer | Not implemented |
| Ingestion worker | Not implemented |
| ML models | Not implemented |
| Tests | Not implemented |
| Alembic migrations | Not created yet |

The foundation is solid. The core intelligence — CV parsing, market analysis, skill matching, salary estimation — needs to be built in the `services/`, `ingestion/`, and `ml/` layers.

## License

MIT
