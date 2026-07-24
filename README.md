# Longitudinal Medical Intelligence System (LMIS)

LMIS is a multi-agent AI architecture designed for clinical document understanding and longitudinal decision support. Unlike generic medical QA systems or point-in-time summarizers, LMIS ingests messy real-world medical data (PDFs, scanned images, handwritten notes) and builds a cryptographically-auditable, longitudinal patient timeline. It then uses retrieved medical guidelines to generate verified, evidence-grounded insights.

## Architecture Highlights

1. **Multi-Agent LangGraph Pipeline**: A 9-agent state machine orchestrates the extraction process, ensuring separation of concerns:
   - **Ingestion & Triage**: Classifies documents and checks quality.
   - **OCR & Layout**: Uses PaddleOCR and TrOCR for robust text extraction.
   - **Medical NER**: Extracts entities (medications, labs, diagnoses) using specialized biomedical models, handling negation and assertion status.
   - **Normalization**: Maps raw entities to standard ontologies (LOINC, RxNorm, ICD-10) using fuzzy matching.
   - **Trend & Timeline**: Detects clinically significant longitudinal changes (e.g., eGFR decline over 12 months) and monitoring gaps.
   - **Knowledge Retrieval**: Fetches relevant medical guidelines (e.g., ADA, KDIGO) based on the patient's state.
   - **Clinical Reasoning**: Generates potential insights based on the trends and retrieved knowledge.
   - **Verification & Critic**: Critiques and verifies every generated insight to prevent hallucinations before surfacing to the user.
   - **Orchestration**: Manages the state machine via LangGraph and Celery.

2. **Full-Stack Stack**:
   - **Backend**: FastAPI (Python), SQLAlchemy (Async), PostgreSQL (Relational Data), Qdrant (Vector Store), MinIO (Blob Storage), Redis (Caching/Tokenization), Celery (Task Queue).
   - **Frontend**: Next.js (React), TailwindCSS, TypeScript. Features a premium glassmorphism dark-mode UI with role-based access (Patient, Clinician, Admin).
   - **LLM Abstraction**: Uses `instructor` to guarantee structured Pydantic outputs from Anthropic, OpenAI, Google, or local Ollama models.

3. **Security & Privacy**:
   - **PHI Tokenization**: An on-the-fly regex tokenizer intercepts text before it reaches external LLMs, replacing PII (names, MRNs, dates) with reversible UUID tokens stored in Redis with a TTL.
   - **Data Encryption**: Uses Fernet symmetric encryption for PHI data at rest in PostgreSQL.
   - **Audit Ledger**: Every agent action, model inference, and latency metric is logged with input/output SHA256 hashes.

## Getting Started

1. Copy the environment variables template:
   ```bash
   cd backend
   cp .env.example .env
   ```
2. Add your LLM API keys to the `backend/.env` file (e.g., `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
3. Start the infrastructure (Postgres, Redis, MinIO, Qdrant):
   ```bash
   docker-compose up -d
   ```
4. Start the FastAPI backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. Start the Celery worker (required for document processing):
   ```bash
   cd backend
   celery -A app.worker.celery_app worker --loglevel=info --pool=solo
   ```
6. Start the frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Design System

The frontend employs a modern, dark-themed aesthetic with tailored accents:
- **Colors**: Deep space blues (`#0A0F1E`, `#111827`), vibrant accents (`#3B82F6` for primary actions, `#10B981` for success, `#F59E0B` for warnings, `#EF4444` for critical alerts).
- **Typography**: Inter (sans-serif) for clean readability.
- **Effects**: Glassmorphism (`backdrop-blur`), subtle gradients, and micro-animations for interactive elements.
