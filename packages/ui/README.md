# @rozgar/ui

The design system.

While the Next.js app is the only consumer, the components live in `apps/web/components/ui` so
they stay colocated with the Tailwind theme that defines their tokens:

| Component | File |
|---|---|
| `Button`, `ButtonLink`, `Spinner` | `apps/web/components/ui/Button.tsx` |
| `Input`, `Select`, `Textarea`, `Checkbox` | `apps/web/components/ui/Input.tsx` |
| `Badge`, `JobSourceBadge`, `MatchScore` | `apps/web/components/ui/Badge.tsx` |
| `Modal`, `Drawer` | `apps/web/components/ui/Modal.tsx` |
| `ToastProvider`, `useToast` | `apps/web/components/ui/Toast.tsx` |
| `EmptyState`, `ErrorState`, `UnauthorizedState`, `Skeleton`, `JobListSkeleton`, `LoadingBlock` | `apps/web/components/ui/states.tsx` |
| `JobCard`, `CompanyLogo`, `JobActions` | `apps/web/components/jobs/` |
| `SearchBar`, `FilterPanel`, `Pagination`, `SearchResults` | `apps/web/components/search/` |
| `Navbar`, `Footer` | `apps/web/components/layout/` |

Design tokens (brand palette, ink scale, radii, shadows, animations) are defined once as Tailwind
v4 `@theme` variables in `apps/web/app/globals.css`.

**Extraction path:** when a second React app appears (employer portal, admin SPA), move
`components/ui` here, add a build step, and update the web app's imports. Nothing else depends on
their location.
