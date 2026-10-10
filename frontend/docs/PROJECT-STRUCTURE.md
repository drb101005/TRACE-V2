# Project structure notes

- `src/App.jsx`: public entry page, backend authentication, and API-backed audit workspace.
- `src/api.js`: bearer-token API client for backend workflows.
- `src/styles.css`: responsive styles for public, login, workspace, tables, timeline, modal and mobile breakpoints.
- `src/main.jsx`: React DOM bootstrap.
- `public/`: static assets served from the site root.
- `e2e/`: Playwright browser tests.
- `playwright.config.js`: starts Vite on `127.0.0.1:5173` and records traces/screenshots on failures.
