# PLP Assessment API — WMS Integration Backend

AI-powered candidate assessment service exposed as a stateless REST API.  
Designed to be consumed by the WMS frontend via API key authentication.

## Quick Start

```bash
# 1. Install dependencies
cd wms_api
pip install -r requirements.txt

# 2. Configure environment

# Edit .env with your API_KEY, OPENAI_API_KEY, REDIS_URL

# 3. Start Redis (must be running)
# Windows: redis-server.exe
# Linux:   redis-server

# 4. Start the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## API Reference

### Authentication

All endpoints except `/api/v1/health` require the header:

```
X-API-Key: <your-configured-api-key>
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/health` | ❌ | Service readiness check |
| `POST` | `/api/v1/evaluate` | ✅ | Submit session for evaluation |
| `GET` | `/api/v1/status/{job_id}` | ✅ | Poll job status / get results |
| `POST` | `/api/v1/results/{job_id}/ack` | ✅ | Acknowledge receipt, clear cache |

---

### POST `/api/v1/evaluate`

Submit a full session (up to 10 questions) for AI evaluation.

**Request:**
```json
{
  "session_id": "wms-session-abc123",
  "candidate_name": "John Doe",
  "candidate_id": "EMP-001",
  "module_title": "Customer Handling Assessment",
  "questions": [
    {
      "question_id": "q1",
      "question_text": "A customer can't access Citrix due to a password problem...",
      "recording_url": "https://storage.example.com/recordings/q1.webm",
      "standard_responses": [
        "I understand how frustrating this must be...",
        "I would apologize for the inconvenience..."
      ]
    }
  ],
  "scoring_weights": {
    "courtesy": 1.5,
    "empathy": 1.5,
    "respect": 1.2,
    "tone": 1.0,
    "communication": 1.3
  }
}
```

**Response (202):**
```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "received",
  "message": "Job received. 5 questions queued for evaluation.",
  "poll_url": "/api/v1/status/f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

---

### GET `/api/v1/status/{job_id}`

**Processing:**
```json
{
  "job_id": "f47ac10b-...",
  "status": "processing",
  "progress": "3/5 evaluated",
  "elapsed_seconds": 45.2,
  "message": "Downloading and processing audio recordings..."
}
```

**Completed:**
```json
{
  "job_id": "f47ac10b-...",
  "status": "completed",
  "session_id": "wms-session-abc123",
  "processing_time_seconds": 72.5,
  "overall_score": 7.5,
  "overall_summary": "Across 5 responses with an average score of 7.5/10...",
  "overall_strengths": ["Polite and empathetic tone"],
  "overall_weaknesses": ["Could show more ownership"],
  "question_results": [
    {
      "question_id": "q1",
      "transcript": "Hi, I understand you're having trouble...",
      "total_score": 8.0,
      "courtesy_score": 8.5,
      "empathy_score": 7.0,
      "respect_score": 8.0,
      "tone_score": 7.5,
      "communication_score": 8.0,
      "strengths": ["Acknowledged customer frustration"],
      "improvement_areas": ["Could provide clearer next steps"],
      "summary": "The candidate showed genuine empathy..."
    }
  ]
}
```

---

### POST `/api/v1/results/{job_id}/ack`

Acknowledge receipt of results. Deletes the job from Redis.

```json
{"message": "Results acknowledged and cleared."}
```

---

## Flow

```
WMS Frontend                    PLP Assessment API                Redis
    │                                  │                            │
    ├─POST /evaluate──────────────────►│                            │
    │  (API key + 5 questions)         ├──create job───────────────►│
    │◄─202 {job_id}────────────────────┤                            │
    │                                  │                            │
    │                           [Background: download→transcribe→evaluate]
    │                                  │                            │
    ├─GET /api/v1/status/{job_id}─────►│◄──read job─────────────────┤
    │◄─{status: "processing"}──────────┤                            │
    │                                  │                            │
    ├─GET /api/v1/status/{job_id}─────►│◄──read job─────────────────┤
    │◄─{status: "completed", ...}──────┤                            │
    │                                  │                            │
    ├─POST /results/{job_id}/ack──────►│──delete job────────────────►│
    │◄─{message: "acknowledged"}───────┤                            │
```

---

## Environment Variables

See `.env.example` for all options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | — | **Required.** Shared secret for WMS frontend |
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model for evaluation |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `USE_FASTER_WHISPER` | `true` | Use local transcription |
| `MAX_RETRIES` | `3` | Auto-retry on failure |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed origins |

---

## Performance

Target: **2-3 minutes** for a 5-question session.

All questions are processed **concurrently**:
- Audio downloads: async IO (parallel)
- Transcription: semaphore-limited (max 3 concurrent)
- OpenAI evaluation: semaphore-limited (max 5 concurrent)
- Overall summary: generated after all questions complete

Typical timing: **60-90 seconds** for 5 questions.
