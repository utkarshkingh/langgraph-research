# Generic image for both services. The SERVICE build arg picks which app to run.
# Mirrors the production pattern: one image, Azure Container Apps runs it twice with
# different startup commands (or you parameterize the entrypoint).
FROM python:3.12-slim

WORKDIR /app

# Copy the source, then install the package and the Azure extra.
COPY . .
RUN pip install --no-cache-dir ".[azure]"

# Which service: "orchestrator" (8080) or "research_agent" (8081).
ARG SERVICE=orchestrator
ENV SERVICE=${SERVICE}
ENV PORT=8080

# Everything is configured with env vars (LLM, Postgres, search, auth): see .env.example.
CMD ["sh", "-c", "uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port ${PORT}"]
