## ADDED Requirements

### Requirement: Frontend linting and build validation
`frontend-react/` SHALL include ESLint (`.eslintrc.cjs` or `eslint.config.js`) and Prettier configurations with `npm run lint` and `npm run build` scripts. Build output artifacts (`tsconfig.tsbuildinfo`) SHALL be ignored by `.gitignore` and removed from git tracking.

#### Scenario: Frontend linting
- **WHEN** `npm run lint` is executed in `frontend-react/`
- **THEN** TypeScript and React component syntax is checked against ESLint rules

#### Scenario: Clean git status after frontend build
- **WHEN** `npm run build` is run locally
- **THEN** transient build artifacts (like `tsconfig.tsbuildinfo`) are ignored by git
