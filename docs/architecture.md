# KRAKEN Microservices Architecture

KRAKEN (Knowledge Retrieval & Autonomous Knowledge Execution Network) is a production-grade, multi-agent AI system designed for automated IT service desk operations, knowledge retrieval, and human-in-the-loop (HITL) action execution.

---

## 1. System Topology Diagram

The following diagram illustrates the microservice layout, API boundaries, and backing storage components.

```mermaid
flowchart TD
    Client["Client / React Frontend / CLI"]
    Gateway["API Gateway (Port 8000)<br/>• Auth & Rate Limiting<br/>• Prompt Guard Middleware"]
    Orchestrator["Orchestrator Service (Port 8001)<br/>• LangGraph State Machine<br/>• Semantic Response Cache"]
    Knowledge["Knowledge Service (Port 8002)<br/>• Vector Search<br/>• Document Loaders"]
    Action["Action Service (Port 8003)<br/>• IT Ticket Execution<br/>• Local File I/O"]
    Approval["Approval Service (Port 8004)<br/>• HITL Decision Queue<br/>• Web Approval UI / CSRF"]
    Memory["Memory Service (Port 8005)<br/>• Short-Term (Redis)<br/>• Long-Term (pgvector)"]
    Audit["Audit Service (Port 8006)<br/>• Cryptographic Hash-Chain<br/>• Append-Only Store"]

    Qdrant[("Qdrant Vector DB")]
    PostgreSQL[("PostgreSQL Database<br/>(pgvector extension)")]
    Redis[("Redis / Upstash<br/>(Cache & HITL Queue)")]

    Client -->|X-API-Key| Gateway
    Gateway -->|HTTP /v1/run| Orchestrator
    
    Orchestrator -->|/retrieve| Knowledge
    Orchestrator -->|/session| Memory
    Orchestrator -->|/execute| Action
    Orchestrator -->|/pending| Approval
    Orchestrator -->|/log| Audit

    Knowledge --> Qdrant
    Memory --> Redis
    Memory --> PostgreSQL
    Approval --> Redis
    Audit --> PostgreSQL
    Action --> PostgreSQL
```

---

## 2. Human-in-the-Loop (HITL) Approval Sequence Diagram

High-risk actions (such as ticket status escalation or high-severity changes) trigger a HITL pause. The execution graph yields state and awaits human review via the Approval Service.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant GW as Gateway Service
    participant Orch as Orchestrator
    participant Appr as Approval Service
    participant Redis as Upstash Redis
    actor Admin as Admin / Reviewer
    participant Act as Action Service
    participant Audit as Audit Service

    User->>GW: POST /v1/run { message, session_id }
    GW->>Orch: Proxy request with X-Service-Token
    Orch->>Orch: Evaluate intent & risk level (CRITICAL)
    
    rect rgb(255, 240, 240)
        Note over Orch,Appr: High-Risk Action Detected — Initiate HITL Pause
        Orch->>Appr: POST /pending { approval_id, action_name, payload }
        Appr->>Redis: SET kraken:approval:{id} & SADD kraken:approval:index
        Orch-->>GW: Return status="pending_approval", approval_id
        GW-->>User: Return PendingApproval payload
    end

    rect rgb(240, 255, 240)
        Note over Admin,Appr: Admin Reviews & Decides
        Admin->>Appr: GET /approve/{approval_id} (Renders Web UI + CSRF)
        Admin->>Appr: POST /approve/{approval_id}/decision { decision: "approve", csrf_token }
        Appr->>Redis: GETDEL kraken:approval:{id}
        Appr->>Orch: Resume graph with Command(resume={"approved": true})
    end

    Orch->>Act: POST /execute { action: "escalate_ticket", payload }
    Act->>Audit: POST /log { action_name, risk_level, status: "SUCCESS" }
    Act-->>Orch: Return ActionResult
    Orch-->>GW: Return QueryResponse
    GW-->>User: Final Answer & Confirmation
```

---

## 3. Microservice Responsibilities

| Service | Port | Primary Responsibility | Backing Store |
| :--- | :--- | :--- | :--- |
| **Gateway** | 8000 | Reverse proxy, API key validation, prompt guard security filter, rate limiting. | In-memory sliding window |
| **Orchestrator** | 8001 | LangGraph agent execution loop, tool router, semantic response cache. | Qdrant & PostgreSQL (checkpoints) |
| **Knowledge** | 8002 | SLA rules and operational doc loading, embedding generation, Qdrant vector retrieval. | Qdrant Vector Cloud |
| **Action** | 8003 | Risk-classified IT action handlers (tickets, local file I/O). | PostgreSQL (`tickets`) |
| **Approval** | 8004 | Human-in-the-Loop (HITL) pause handling, CSRF-protected web review UI. | Upstash Redis |
| **Memory** | 8005 | Short-term message history buffer and long-term episodic memory storage. | Redis & PostgreSQL (`pgvector`) |
| **Audit** | 8006 | Cryptographically chained, append-only security audit log. | PostgreSQL (`audit_log`) |
