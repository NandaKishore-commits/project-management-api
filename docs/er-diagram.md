# Database schema (ER diagram)

![ER diagram](er-diagram.png)


```mermaid
erDiagram
    ROLES ||--o{ USERS : "has"
    USERS ||--o{ PROJECTS : "creates"
    USERS ||--o{ PROJECT_MEMBERS : "joins"
    PROJECTS ||--o{ PROJECT_MEMBERS : "has"
    PROJECTS ||--o{ TASKS : "contains"
    USERS |o--o{ TASKS : "assigned to"
    USERS ||--o{ TASKS : "created by"
    USERS |o--o{ TASKS : "last updated by"
    TASKS ||--o{ TASK_COMMENTS : "has"
    USERS ||--o{ TASK_COMMENTS : "writes"
    USERS ||--o{ ACTIVITY_LOGS : "performs"
    PROJECTS |o--o{ ACTIVITY_LOGS : "logged in"
    TASKS |o--o{ ACTIVITY_LOGS : "logged in"

    ROLES {
        int id PK
        string name UK
        string description
    }
    USERS {
        int id PK
        string full_name
        string email UK
        string hashed_password
        int role_id FK
        boolean is_active
        datetime created_at
        datetime updated_at
    }
    PROJECTS {
        int id PK
        string name
        text description
        date start_date
        date end_date
        string status "ACTIVE, ON_HOLD, COMPLETED"
        int created_by FK
        boolean is_deleted
        datetime created_at
        datetime updated_at
    }
    PROJECT_MEMBERS {
        int id PK
        int project_id FK
        int user_id FK
        datetime joined_at
    }
    TASKS {
        int id PK
        string title
        text description
        string status "TODO, IN_PROGRESS, REVIEW, COMPLETED"
        string priority "LOW, MEDIUM, HIGH, CRITICAL"
        date deadline
        int project_id FK
        int assigned_to FK
        int created_by FK
        int updated_by FK
        boolean is_deleted
        datetime created_at
        datetime updated_at
    }
    TASK_COMMENTS {
        int id PK
        int task_id FK
        int user_id FK
        text content
        datetime created_at
    }
    ACTIVITY_LOGS {
        int id PK
        int user_id FK
        int project_id FK
        int task_id FK
        string action
        text details
        datetime created_at
    }
```

`project_members` has a unique pair (`project_id`, `user_id`), so nobody can be added to a project twice.
`alembic_version` is a table Alembic creates for itself, so it is not drawn.