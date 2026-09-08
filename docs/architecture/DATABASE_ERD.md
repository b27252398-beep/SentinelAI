# Database Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ USER_ROLES : has
    ROLES ||--o{ USER_ROLES : belongs_to
    USERS ||--o{ SERVICES : owns
    USERS ||--o{ INCIDENTS : assigned_to
    USERS ||--o{ RECOMMENDATION_DECISIONS : decides
    USERS ||--o{ AUDIT_LOGS : performs
    
    SERVICES ||--o{ INCIDENTS : experiences
    SERVICES ||--o{ ANOMALIES : triggers
    
    INCIDENTS ||--o{ INCIDENT_EVENTS : contains
    INCIDENTS ||--o{ ANOMALIES : groups
    INCIDENTS ||--o| INVESTIGATIONS : has
    
    INVESTIGATIONS ||--o{ INVESTIGATION_EVIDENCE : gathers
    INVESTIGATIONS ||--o{ HYPOTHESES : generates
    
    HYPOTHESES ||--o{ RECOMMENDATIONS : proposes
    RECOMMENDATIONS ||--o| RECOMMENDATION_DECISIONS : receives

    USERS {
        uuid id PK
        string email
        string password_hash
    }
    SERVICES {
        uuid id PK
        string name
        uuid owner_id FK
    }
    INCIDENTS {
        uuid id PK
        string status
        string severity
        uuid service_id FK
    }
    INVESTIGATIONS {
        uuid id PK
        uuid incident_id FK
        string status
        string prompt_version
        string model_identifier
    }
    INVESTIGATION_EVIDENCE {
        uuid id PK
        uuid investigation_id FK
        jsonb raw_data
    }
    HYPOTHESES {
        uuid id PK
        uuid investigation_id FK
        string description
        boolean is_root_cause
    }
    RECOMMENDATIONS {
        uuid id PK
        uuid hypothesis_id FK
        string action_description
    }
```
