# Authentication and RBAC Architecture

## Authentication Mechanism
- **JWT (JSON Web Tokens)**: Used for stateless API authentication.
- Tokens contain the `user_id` and `roles`.
- Expiration: Short-lived access tokens (e.g., 15 minutes) with HttpOnly refresh cookies for MVP.

## Role Hierarchy & Matrix
1. **Administrator**: Full system access, service configuration, user management, audit logs.
2. **Incident Manager**: Can manage incident lifecycles, approve/reject recommendations, and assign engineers.
3. **Engineer**: Can view incidents, inspect telemetry, trigger AI investigations, but CANNOT approve recommendations.
4. **Viewer**: Read-only access to dashboards and incidents.

| Resource | Action | Admin | Manager | Engineer | Viewer |
| :--- | :--- | :---: | :---: | :---: | :---: |
| Users/Roles | Create/Update | Yes | No | No | No |
| Services | Create/Update | Yes | Yes | No | No |
| Incidents | Create | Yes | Yes | No | No |
| Incidents | Update Status | Yes | Yes | Yes | No |
| Investigations| Trigger | Yes | Yes | Yes | No |
| Recommendations| Approve/Reject| Yes | Yes | No | No |
| All Read APIs | GET | Yes | Yes | Yes | Yes |

## Enforcement
- **Backend Authorization**: FastAPI dependency injection `Depends(require_role(['Administrator']))` or `Depends(require_permission('users:read'))` enforces RBAC at the route level. Returning `401 Unauthorized` if no token is present, and `403 Forbidden` if the user has insufficient privileges.
- **Password Security**: Passwords are hashed using the **Argon2id** algorithm via `pwdlib`. Secrets are not logged and are strictly configured via environment variables.
- **Frontend Authorization**: Conditionally renders UI elements based on the decoded JWT roles to prevent unauthorized actions from being visible (e.g., hiding the "Approve" button for non-managers).
- **Audit**: All actions by authenticated users (modifying incidents, triggering investigations, approvals) are intercepted and written to the `audit_logs` table.
