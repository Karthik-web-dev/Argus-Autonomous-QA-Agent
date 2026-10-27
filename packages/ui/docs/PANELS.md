# Run workspace panels

The UI keeps the repository's React + Vite setup. D-02 adds a run workspace at `/replay`; it uses the F-01 generated `RunEvent` type and replays the golden `fixtures/run_events.ndjson` file without starting a browser or calling the API.

## Layout zones

- **Run context:** run id and current replay state in the top bar.
- **Panel navigation:** panel registry entries appear in the left rail (horizontal on narrow screens).
- **Primary panel:** the selected panel renders in the main workspace.
- **Replay controls and activity:** speed, play/pause/reset, and typed event activity.

The source dossier reference is not present in this checkout (the local dossier is a placeholder), so these zones provide the repo's current run workspace scaffold rather than claiming exact parity with §14.1.

## Add a panel in one file

Add one file matching `*-panel.tsx` under `packages/ui/lib/panels`. Panel modules are discovered at build time and self-register, so adding a panel does not require editing a central list:

```tsx
import type { PanelProps } from "./registry";
import { registerPanel } from "./registry";

export function CoveragePanel({ runId }: PanelProps) {
  return <section aria-label="Coverage">Coverage for {runId}</section>;
}
registerPanel({ id: "coverage", title: "Coverage", component: CoveragePanel });
```

The registry rejects duplicate or empty ids. Panels can subscribe to the run state with `useRunStore((state) => state.events)` and should narrow event payload values before rendering them.

For a live backend run, `useRunEvents(runId)` from `@/lib/use-run-events` exposes validated F-01 `RunEvent[]`, connection status, the last SSE event id, an error message, and final metrics. It reconnects with `Last-Event-ID` after a dropped stream.

## Fixture replay

Run `pnpm --filter @argus/ui dev` from the repo root and open `http://localhost:5173/replay`. The golden fixture starts replaying automatically; adjust playback speed, pause/resume, or reset. The checked-in fixture is bundled from the root `fixtures` directory. No API token or live target URL is used.
