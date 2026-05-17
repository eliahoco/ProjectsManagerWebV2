# ProjectsManagerWebV2 Backend

FastAPI backend for CodeBoard - AI-automated task management.

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings

# Run development server
uvicorn app.main:app --reload --port 8401
```

## API Documentation

Available **only when `ENVIRONMENT=development` (or `dev`)** is set in
`.env`. Production / staging / unset locks the route map down (CB-2668).

- Swagger UI: http://localhost:8401/docs
- ReDoc: http://localhost:8401/redoc
- OpenAPI schema: http://localhost:8401/openapi.json

If any of these returns 404, your `.env` is in production mode — set
`ENVIRONMENT=development` and restart the backend. See
`backend/docs/DOC_PIPELINE_RUNBOOK.md` §3a for the rationale.

## Structure

```
backend/
├── app/          # Main application
├── api/          # API routes
├── models/       # Database models
├── services/     # Business logic
└── tests/        # Test suite
```
