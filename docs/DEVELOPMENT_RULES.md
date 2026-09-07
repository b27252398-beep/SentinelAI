# Development Rules

## Coding Standards
- **Python**: Follow PEP 8 guidelines. Use type hints for all function signatures. Use `black` and `ruff` for formatting and linting.
- **TypeScript**: Strict type-checking enabled. Follow ESLint standard rules. Prefer functional components and hooks in React.
- **General**: No placeholder components or mocked services just to appear complete. Build incrementally and robustly.

## Security Rules
- Secrets and API keys must never be committed to the repository (use `.env` files).
- Inputs from external systems or users must be validated and sanitized.
- All endpoints outside of login must enforce RBAC and authentication checks.

## Testing Expectations
- Write unit tests for business logic using `pytest`.
- Write integration tests for database operations and API endpoints.
- End-to-end user flows must be tested via Playwright.
- PRs should not be merged without passing CI and adequate test coverage.

## Git Practices
- Git is mandatory for version control (Note: Git is currently missing from the system environment and must be installed).
- Feature branches (e.g., `feature/auth-module`, `bugfix/fix-latency-check`).
- Meaningful commit messages.
- No direct commits to `main` once the baseline is established.

## Dependency Management Rules
- Use `requirements.txt` or `Poetry` for Python dependencies with pinned versions.
- Use `package.json` and `npm` or `yarn` lockfiles for Node dependencies.
- Avoid unnecessarily large dependencies. Justify every third-party library introduced.

## AI Implementation Rules
- AI must explicitly cite evidence when formulating a hypothesis.
- AI must distinguish between observed facts, inferences, and recommendations.
- Keep prompts versioned and testable.
- AI features must be built to handle edge cases gracefully, providing fallbacks when LLM endpoints fail.

## Scope Rules
- **No Uncontrolled Scope Expansion**: Stick strictly to the MVP requirements. Do not invent new features without discussion and Architecture Decision Records (ADRs).
