# @rozgar/config

Shared build configuration.

- `tsconfig.base.json` — the TypeScript settings every TS package should extend.

The environment contract itself lives in the repository root `.env.example`, and is validated at
runtime by `pakjobs_core.config.Settings` (a single Pydantic model used by the API, the worker and
the CLI, so behaviour cannot drift between processes).
