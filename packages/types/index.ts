/**
 * Shared domain types.
 *
 * The canonical definitions live in `apps/web/lib/types.ts` while the frontend is the only
 * TypeScript consumer. This package re-exports them so a second consumer (an employer portal,
 * a mobile app, a partner SDK) can depend on the contract without importing from `apps/web`.
 *
 * When a second consumer appears, move the definitions here and have the web app import from
 * this package instead — no other change is required.
 */
export type * from "../../apps/web/lib/types";
