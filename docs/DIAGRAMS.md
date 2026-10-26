# Diagrams

## 1. Session state machine

```mermaid
stateDiagram-v2
    [*] --> unassigned: Create session

    unassigned --> assigned: Assign provider
    assigned --> accepted_by_provider: Provider accepts
    accepted_by_provider --> in_progress: User starts\n(balance ≥ 5 × cost)
    in_progress --> completed: User ends
    in_progress --> completed: Provider ends
    in_progress --> completed: System ends\n(Insufficient Balance)

    completed --> [*]
```

**Rules**

- Only listed transitions are allowed; anything else returns **HTTP 400**.
- A user may have at most one `in_progress` session.
- `per_minute_cost` is set at create and used for all billing on that session.
- Billing uses `minutes_billed` so the same target minute is not charged twice.

---

## 2. ER-style overview

```mermaid
erDiagram
    USER ||--|| PROFILE : has
    USER ||--|| WALLET : has
    USER ||--o{ RECHARGE_TRANSACTION : initiates
    USER ||--o{ CONSULTATION_SESSION : books_as_user
    USER ||--o{ CONSULTATION_SESSION : serves_as_provider

    USER {
        int id PK
        string username
        string password
    }

    PROFILE {
        int id PK
        int user_id FK
        string role "user|provider"
    }

    WALLET {
        int id PK
        int user_id FK
        decimal balance
    }

    RECHARGE_TRANSACTION {
        int id PK
        int user_id FK
        decimal amount
        string reference UK
        string status "pending|success|failed"
        datetime created_at
    }

    CONSULTATION_SESSION {
        int id PK
        int user_id FK
        int provider_id FK "nullable"
        string status
        decimal per_minute_cost
        int minutes_billed
        datetime started_at
        datetime ended_at
        string ended_by "user|provider|system"
        string end_reason
    }
```

**Relationships**

| Link | Cardinality | Notes |
|------|-------------|--------|
| User ↔ Profile | 1:1 | Role; auto-created on user signup (signal) |
| User ↔ Wallet | 1:1 | Prepaid balance |
| User → RechargeTransaction | 1:N | Mock payment attempts; `reference` unique |
| User → Session (as user) | 1:N | Customer / payer |
| User → Session (as provider) | 1:N | Nullable until assigned |
