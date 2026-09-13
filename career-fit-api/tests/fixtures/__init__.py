"""Shared test fixtures / sample data used across unit and integration tests."""

SAMPLE_CV_TEXT = """
Jane Doe
Senior Backend Engineer

Summary
Backend engineer with 6+ years of experience building scalable APIs and
distributed systems in Python and Go. Strong background in PostgreSQL,
Redis, and event-driven architectures. Comfortable owning services from
design through production operation.

Experience
Senior Backend Engineer - Acme Corp (2021 - Present)
- Designed and maintained microservices handling 10M+ requests/day.
- Migrated legacy monolith to async FastAPI services, cutting p99 latency by 40%.
- Mentored two junior engineers and led on-call rotation.

Backend Engineer - Globex Inc (2018 - 2021)
- Built internal tooling for data ingestion pipelines using Python and Airflow.
- Implemented CI/CD pipelines with GitHub Actions and Docker.

Skills: Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, Go

Education
B.Sc. in Computer Science - State University (2014 - 2018)
""".strip()
