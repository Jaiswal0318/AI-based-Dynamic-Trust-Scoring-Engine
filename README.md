## AI-Based Dynamic Trust Scoring Engine for Zero Trust Networks

This project is a minimal **reference implementation** of an AI-based dynamic trust
scoring engine suitable for Zero Trust Network architectures.

It exposes a **FastAPI** service that ingests contextual risk signals about a user,
device, and resource, and returns:

- **trust_score**: continuous value in \[0, 1\] (higher = more trusted)
- **decision**: `allow`, `challenge`, or `deny`
- **reasons**: human-readable explanations of the decision

The trust score itself is produced by a small **Logistic Regression** model
(`scikit-learn`) trained on synthetic data that mimics typical Zero Trust risk
patterns (user risk, device posture, anomalous behavior, time-of-day, past
incidents, and resource sensitivity).

---

### 1. Problem Statement

In a Zero Trust Network, no user or device is inherently trusted, even if they
are inside the network perimeter. Every access request should be **continuously
evaluated** using up-to-date contextual signals.

The goal of this engine is to:

- **Aggregate multiple risk signals** about user, device, network, and behavior.
- **Compute a dynamic trust score** using a machine-learning model.
- **Map the trust score to a decision** (`allow` / `challenge` / `deny`) according
  to configurable thresholds.
- **Explain the decision** in human-readable terms for audit and tuning.

---

### 2. High-Level Design

- **API Layer**: FastAPI application (`app/main.py`) exposing:
  - `GET /health` – health check.
  - `POST /score` – computes trust score and decision for a given `AccessContext`.
- **Schema Layer**: Pydantic models (`app/schemas.py`) defining:
  - `AccessContext` – input signals.
  - `TrustScoreResponse` – output.
- **Model Layer**: `DynamicTrustModel` (`app/model.py`):
  - Trains a Logistic Regression model on synthetic risk data at startup.
  - Encodes request context into model features.
  - Produces a trust score and an approximate feature contribution breakdown.
- **Policy Layer**:
  - Simple thresholds convert the trust score into `allow` / `challenge` / `deny`.

---

### 3. Local Setup (without Docker)

From your project root (`AI-Based Dynamic Search`):

```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows PowerShell: .venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

You can open automatic interactive docs at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

You can also open the **Zero Trust Dashboard UI** at:

- Dashboard: `http://localhost:8000/`

---

### 4. Security (API key)

All JSON APIs except `/` and `/health` are protected with a simple **API key**:

- **Default API key**: `zt-demo-key`
- **Header name**: `X-API-Key`

You can override the key via environment variable before starting the server:

```bash
set ZT_API_KEY=your-strong-key-here   # PowerShell: $env:ZT_API_KEY="your-strong-key-here"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Example request with API key:

```bash
curl -X POST "http://localhost:8000/score" ^
  -H "X-API-Key: zt-demo-key" ^
  -H "Content-Type: application/json" ^
  -d "{ ...body... }"
```

The dashboard frontend automatically sends this header for its own calls.

---

### 5. Example Request

Send a request to the `/score` endpoint using `curl` or any HTTP client:

```bash
curl -X POST "http://localhost:8000/score" ^
  -H "Content-Type: application/json" ^
  -d "{
    \"user_id\": \"alice\",
    \"device_id\": \"laptop-123\",
    \"resource_id\": \"prod-db\",
    \"user_risk\": 0.2,
    \"device_risk\": 0.3,
    \"location_risk\": 0.2,
    \"network_risk\": 0.3,
    \"behavior_risk\": 0.4,
    \"time_of_day\": 10,
    \"past_incidents\": 0,
    \"sensitive_resource\": true
  }"
```

Typical JSON response:

```json
{
  "trust_score": 0.71,
  "decision": "allow",
  "reasons": [
    "Trust score is high enough to allow access.",
    "Target resource is sensitive, applying stricter thresholds.",
    "Top influencing factors (approximate): behavior_risk=-0.123, device_risk=-0.087, user_risk=-0.075."
  ]
}
```

> Note: Exact numbers will vary because the model uses dynamic scoring.

---

### 6. Docker-Based Deployment

You can containerize and run the service using the provided `Dockerfile`.

From the project root:

```bash
docker build -t dynamic-trust-engine .
docker run --rm -p 8000:8000 dynamic-trust-engine
```

The API will again be accessible at `http://localhost:8000`.

---

### 7. Integration in a Zero Trust Architecture

In a larger Zero Trust system, this engine would typically be invoked:

- By an **Identity Provider (IdP)** or **Access Proxy** whenever a user tries to
  access a protected resource.
- With features populated from:
  - Identity & UEBA systems (`user_risk`, `behavior_risk`).
  - Endpoint management / EDR (`device_risk`).
  - Network telemetry (`location_risk`, `network_risk`).
  - Policy store / inventory (`sensitive_resource`).

Based on the returned `decision`, the caller can:

- **allow**: grant access.
- **challenge**: trigger MFA or step-up verification.
- **deny**: block access and optionally open an incident.

