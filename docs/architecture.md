# KRAKEN Consolidated Architecture

KRAKEN (Knowledge Retrieval & Autonomous Knowledge Execution Network) is a production-grade autonomous AI system designed for automated IT service desk operations, knowledge retrieval, and human-in-the-loop (HITL) action execution.

For details on the internal LangGraph reasoning state machine, node contracts, and prompt versioning, see [Agent Pipeline](agent-pipeline.md).

---

## 1. System Topology Diagram

The following diagram illustrates the consolidated architecture layout, in-process routing, and backing storage components.

```mermaid
flowchart TD
    Client["Client / React Frontend / CLI"]
    
    subgraph AppProcess["KRAKEN Consolidated Application Process (Port 8000)"]
        Gateway["Gateway Router (Port 8000)<br/>• Auth & Rate Limiting<br/>• Prompt Guard Middleware<br/>• Subsystem Lifespan Manager"]
        Orchestrator["Orchestrator Subsystem<br/>• LangGraph State Machine<br/>• ReAct Loop & HITL Interrupt"]
        Knowledge["Knowledge Subsystem<br/>• Vector Search<br/>• Document Loaders"]
        Action["Action Subsystem<br/>• IT Ticket Execution<br/>• Path-Validated Workspace I/O"]
        Approval["Approval Subsystem<br/>• HITL Decision Queue<br/>• CSRF Token Validation"]
        Memory["Memory Subsystem<br/>• Short-Term Session Buffer<br/>• Long-Term Vector Memory"]
        Audit["Audit Subsystem<br/>• Cryptographic Hash-Chain<br/>• Append-Only Log Store"]
    end

    Qdrant[("Qdrant Vector DB<br/>(Knowledge RAG, Semantic Cache & Episodic Memory)")]
    PostgreSQL[("PostgreSQL Database<br/>(Audit Logs & Ticket State)")]
    Redis[("Redis<br/>(Rate Limiter, Session Buffer & HITL Queue)")]

    Client -->|X-API-Key| Gateway
    Gateway -.->|In-Process ASGI| Orchestrator
    Gateway -.->|In-Process ASGI| Approval
    
    Orchestrator -.->|In-Process ASGI| Knowledge
    Orchestrator -.->|In-Process ASGI| Memory
    Orchestrator -.->|In-Process ASGI| Action
    Orchestrator -.->|In-Process ASGI| Approval
    Orchestrator -.->|In-Process ASGI| Audit

    Knowledge --> Qdrant
    Memory --> Redis
    Memory --> Qdrant
    Approval --> Redis
    Audit --> PostgreSQL
    Action --> PostgreSQL
```

---

## 2. Human-in-the-Loop (HITL) Approval Sequence Diagram

High-risk actions (such as ticket escalation or destructive file operations) trigger a HITL pause. The execution graph yields state and awaits human review via the Gateway approval endpoints.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant GW as Gateway / App Process
    participant Orch as Orchestrator Subsystem
    participant Appr as Approval Subsystem
    participant Redis as Redis Store
    actor Admin as Admin / Reviewer
    participant Act as Action Subsystem
    participant Audit as Audit Subsystem

    User->>GW: POST /v1/run { message, session_id }
    GW->>Orch: In-Process /run
    Orch->>Orch: Evaluate intent & risk level (CRITICAL)
    
    rect rgb(255, 240, 240)
        Note over Orch,Appr: High-Risk Action Detected — Initiate HITL Pause
        Orch->>Appr: In-Process POST /pending { approval_id, action_name, payload }
        Appr->>Redis: SET kraken:approval:{id} & SADD kraken:approval:index
        Orch-->>GW: Return status="pending_approval", approval_id
        GW-->>User: Return PendingApproval payload
    end

    rect rgb(240, 255, 240)
        Note over Admin,Appr: Admin Reviews & Decides
        Admin->>GW: GET /approve/{approval_id}/details
        GW->>Appr: In-Process Details Fetch
        Appr-->>GW: Return Action Details + CSRF Token
        GW-->>Admin: Return Details
        Admin->>GW: POST /approve/{approval_id}/decision { decision: "approve", csrf_token }
        GW->>Appr: In-Process Decision Submit
        Appr->>Redis: GETDEL kraken:approval:{id}
        Appr->>Orch: Resume graph with Command(resume={"approved": true})
    end

    Orch->>Act: In-Process POST /execute { action: "escalate_ticket", payload }
    Act->>Audit: In-Process POST /log { action_name, risk_level, status: "SUCCESS" }
    Act-->>Orch: Return ActionResult
    Orch-->>GW: Return QueryResponse
    GW-->>User: Final Answer & Confirmation
```

---

## 3. Subsystem Responsibilities

| Subsystem | Port / Route | Primary Responsibility | Backing Store |
| :--- | :--- | :--- | :--- |
| **Gateway** | 8000 | Reverse proxy, API key validation, prompt guard security filter, rate limiting, sub-app lifespan orchestration. | In-memory sliding window / Redis |
| **Orchestrator** | In-Process | LangGraph agent execution loop, tool routing, checkpoint persistence, HITL interrupt. | Qdrant & PostgreSQL (checkpoints) |
| **Knowledge** | In-Process | SLA rules and operational doc loading, embedding generation, Qdrant vector retrieval. | Qdrant Vector Cloud |
| **Action** | In-Process | Risk-classified IT action handlers (tickets, workspace file I/O). | PostgreSQL (`tickets`) |
| **Approval** | In-Process & `:8000/approve/*` | Human-in-the-Loop (HITL) pause handling, CSRF-protected web review and API proxy endpoints. | Redis |
| **Memory** | In-Process | Short-term message history buffer and long-term episodic memory storage. | Redis & Qdrant (`kraken_episodic_memory`) |
| **Audit** | In-Process | Cryptographically chained, append-only security audit log. | PostgreSQL (`audit_log`) |
