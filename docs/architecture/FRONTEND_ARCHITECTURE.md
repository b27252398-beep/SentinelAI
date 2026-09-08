# Frontend Architecture

The frontend is a Single Page Application (SPA) built using **Next.js (App Router)** and **TypeScript**.

## Application Structure
```text
src/
├── app/                  # Next.js App Router pages
│   ├── (auth)/           # Login routes
│   ├── dashboard/        # Main authenticated area
│   └── incidents/        # Incident workspace
├── components/           # Reusable UI components
├── lib/                  # Utilities, API clients
└── store/                # Global state management
```

## Routing & Layouts
- **`/login`**: Unauthenticated entry point.
- **`/dashboard`**: High-level metrics, active anomalies, recent incidents.
- **`/services`**: Service registry management.
- **`/incidents/[id]`**: Deep dive Incident Workspace.

## Authentication & RBAC
- **Flow**: User logs in -> Receives JWT -> JWT stored in HTTP-only secure cookie -> Sent automatically to API.
- **RBAC UI**: UI components evaluate the user's role context. Example: If an `Engineer` views a recommendation, the "Approve" button is hidden unless they hold `Incident Manager` or `Administrator` rights.

## Incident Workspace Architecture
The incident workspace (`/incidents/[id]`) is the core complex UI, composed of:
1. **Telemetry Views**: Time-series charts for metrics, streaming log viewers.
2. **Investigation UI**: Displays the chronological timeline of correlated events.
3. **Evidence Display**: Renders raw data (**OBSERVED FACTS**) explicitly linked to the incident.
4. **RCA & Hypothesis Display**: Renders AI-generated **INFERENCES** in a distinct visual style (e.g., color-coded borders) to clearly separate them from observed facts.
5. **Recommendation Approval UI**: A specific panel for managers to review, accept, or reject AI recommendations.

## API Communication & State
- **State Management**: React Context / Zustand for user session data.
- **Data Fetching**: React Query (TanStack Query) for fetching API data, handling caching, loading states, and error retries.
- **Error States**: Global error boundary for hard crashes; localized toast notifications for API failures.
