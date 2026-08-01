# Architecture

AtlasFlow separates the HTTP boundary, orchestration graph, and external tools so each layer has one clear responsibility.

## Request lifecycle

1. FastAPI validates and normalizes the request before dispatch.
2. The LangGraph guardrail checks scope and safety.
3. The supervisor extracts constraints and chooses the smallest useful agent set.
4. Specialist agents enrich state through isolated MCP servers. A provider failure degrades only that specialist rather than the complete workflow.
5. The itinerary agent integrates available results into a draft.
6. LangGraph persists state in PostgreSQL and interrupts execution for human review.
7. Approval or revision feedback resumes the same thread and produces the final response.

## Production boundaries

- Agent imports are lazy, so `/health`, the UI, and OpenAPI remain available when a provider is temporarily unconfigured.
- Synchronous graph calls run in a worker thread instead of blocking FastAPI's event loop.
- Public errors contain a short reference identifier; full diagnostics stay in server logs.
- `/health` is a liveness probe. `/ready` verifies the core Groq and PostgreSQL configuration.
- The container runs as an unprivileged user and includes its own health check.

## Failure strategy

Hotel, flight, and weather adapters return clearly labeled non-live fallback guidance when their MCP provider is unavailable. Core model or persistence failures stop the workflow and return a traceable, sanitized server error.
