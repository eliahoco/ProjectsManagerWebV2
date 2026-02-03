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

Once running, visit:
- Swagger UI: http://localhost:8401/docs
- ReDoc: http://localhost:8401/redoc

## Structure

```
backend/
├── app/          # Main application
├── api/          # API routes
├── models/       # Database models
├── services/     # Business logic
└── tests/        # Test suite
```
