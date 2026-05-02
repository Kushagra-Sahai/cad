# Docker Notes

The root `docker-compose.yml` defines the runnable stack:

- `backend`: FastAPI, OCR, drug lookup, RAG, LLM, Watson speech integrations.
- `frontend`: React app served by Nginx.
- `mongo`: query logs and medicine cache.
- `ollama`: optional local LLM runtime.

Runtime configuration is kept in the root `.env` file.
