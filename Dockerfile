# One image for both services. SERVICE picks which app runs.
#   docker build --build-arg SERVICE=research_agent --build-arg PORT=8001 .
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[postgres,azure]"

ARG SERVICE=orchestrator
ARG PORT=8000
ENV SERVICE=${SERVICE} PORT=${PORT}
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port ${PORT}"]
