# Murmur Dashboard: UI Concept & Spec

## Design Philosophy

The dashboard communicates system state before you read a single word. An investor glances at it and knows whether things are healthy — like reading a heart monitor without being a doctor.

The name Murmur evokes three things:
- **Murmuration** — flock dynamics, coordinated motion, emergent pattern
- **Whisper** — subtle signals beneath the surface
- **Heart murmur** — detecting abnormality in rhythm

The UI makes all three tangible.

---

## The Three Views

### 1. The Pulse (Hero / Ambient View)

**What it is:** A central, ambient visualization of the system's vital signs. Not a chart. Not a number. The system *breathing*.

**Healthy state:**
- Smooth, rhythmic flow of particles/light through the 6 trust zones
- Cool palette: deep navy (#0a0e17), soft blue (#1a3a5c), muted teal (#2a8a7a)
- Calm, regular rhythm
- The visual equivalent of a steady heartbeat

**Elevated state:**
- Flow becomes slightly turbulent — particles drift off their normal paths
- Warm accents emerge: amber (#d4a574), copper (#c47a4a)
- Rhythm becomes uneven — some zones pulse faster
- You feel something is off before you read anything

**Alert state:**
- Clear disruption — a bright thread of activity cutting against the grain
- Hot accent: coral (#e85d5d), bright red (#ff4444)
- The thread connects zones that shouldn't connect, flows without return
- Background remains dark — the anomaly pops

**What you're actually seeing:** The zone flux matrix rendered as a flow field. Entropy production (sigma_coarse) maps directly to visual turbulence. Provenance-explained activity is dimmed. What remains bright IS the residual — the unexplained.

```
+------------------------------------------------------------------+
|                                                                    |
|                        THE PULSE                                   |
|                                                                    |
|           CONTROL                                                  |
|          /  .  .  \                                                |
|     IDENTITY . . . COMPUTE                                        |
|        |  \  .  / .  |                                            |
|      SECRET . DATA   |          residual_risk: 2.1                |
|         \ . . | . /            confidence: HIGH                   |
|        EXFIL_RISK              status: NORMAL                     |
|                                                                    |
|   [soft particle flow between zones, cool blues, steady rhythm]   |
|                                                                    |
+------------------------------------------------------------------+
```

**Technical implementation:** D3.js force-directed particle system. Each particle = an event. Particles flow along zone-to-zone paths. Speed = event rate. Color = provenance (dim = explained, bright = residual). Turbulence = sigma_coarse magnitude.

---

### 2. The Flow Map (Zone Detail View)

**What it is:** The 6 trust zones as a spatial topology with flowing connections. An anatomical diagram of the system's circulatory system.

**Layout:** Zones arranged by attack progression (top = entry, bottom = target):

```
+------------------------------------------------------------------+
|                                                                    |
|                      CONTROL                                       |
|                    [12 events]                                     |
|                   /          \                                     |
|              ====              ====                                |
|             /                      \                               |
|       IDENTITY                  COMPUTE                           |
|      [28 events]               [4 events]                         |
|          |    \               /     |                              |
|          |     ====     ====       |                              |
|          |          \ /            |                              |
|        SECRET      DATA           |                              |
|       [6 events]  [15 events]     |                              |
|           \         |           /                                  |
|            ===      |      ===                                    |
|                \    |    /                                         |
|              EXFIL_RISK                                           |
|              [0 events]                                           |
|                                                                    |
+------------------------------------------------------------------+
```

**Connection rendering:**
- Line thickness = flux volume (events/window)
- Color: cool blue = normal flux, amber = elevated, red = anomalous
- Provenance-explained flows are ghosted (nearly transparent, ~20% opacity)
- What you SEE is the residual — unexplained activity
- Animated: flows move in direction of event progression

**Healthy system:** Thin, cool, mostly ghosted connections (everything explained by provenance). Calm circulatory system.

**Under attack:** Bright, thick thread from IDENTITY to SECRET or EXFIL_RISK. The "hemorrhage" — flow rushing toward sensitive zones without authorization.

**Interaction:** Click a zone to expand its events. Click a connection to see which actors are producing that flux.

---

### 3. The Lineage View (Drill-Down)

**What it is:** When you click a flagged actor or alert, a clean authorization trace. Not a log — a tree showing who authorized what.

```
+------------------------------------------------------------------+
|  Actor: svc-unknown@project.iam                                   |
|  residual_risk: 8.7  |  provenance: NONE  |  closure: 0.0        |
|                                                                    |
|  Authorization Chain:                                              |
|                                                                    |
|  [?] Unknown origin           <-- BROKEN LINK (no trigger_ref)    |
|    |                                                               |
|    +-- IAM_CREATE_KEY          14:02:31  IDENTITY                 |
|    |     target: svc-unknown-key-1                                |
|    |     INV_002: Key created (sev 5)                             |
|    |     INV_003: Novel key issuer (sev 5)                        |
|    |                                                               |
|    +-- SECRET_ACCESS           14:07:45  SECRET                   |
|    |     target: secret_high                                      |
|    |     INV_006: New actor accessing secret (sev 5)              |
|    |     INV_007: Secret access within 15min of key creation      |
|    |                                                               |
|    +-- [OPEN] Key not revoked  ---- 720h window ----  UNCLOSED   |
|                                                                    |
|  Closure:                                                          |
|    IAM_CREATE_KEY -> IAM_DELETE_KEY: OPEN (not revoked)           |
|    orphaned_privilege_score: 7.5                                  |
|                                                                    |
|  Signals:                                                          |
|    sigma_coarse: 3.2 (elevated)                                   |
|    bridge_new: IDENTITY->SECRET (novel)                           |
|    inv_score: 15.0 (3 invariants fired)                           |
+------------------------------------------------------------------+
```

**Key visual elements:**
- **Broken link:** A visible gap where trigger_ref is NULL. The missing authorization. "Who authorized this?" — nobody.
- **Closure arcs:** Opening actions on left, closing actions on right, connected by an arc. Complete = closed circle. Incomplete = open arc with dashed line to "UNCLOSED."
- **Invariant badges:** Red chips showing which invariants fired and their severity.
- **Zone breadcrumbs:** Color-coded zone transitions showing the trajectory path.

---

## Design Language

| Element | Choice | Rationale |
|---|---|---|
| **Background** | Near-black (#0a0e17) | Control room. "Always watching." Colored signals pop. |
| **Base palette** | Navy (#0d1b2a), Steel (#1b2838), Slate (#2a3a4a) | Subtle depth without distraction. |
| **Healthy accent** | Teal (#2a8a7a), Soft blue (#4a9aca) | Cool = calm = authorized. |
| **Warning accent** | Amber (#d4a574), Copper (#c47a4a) | Warm = attention needed. |
| **Alert accent** | Coral (#e85d5d), Red (#ff4444) | Hot = action required. |
| **Explained/ghosted** | 20% opacity of base flow color | Provenance-explained activity fades to background. |
| **Typography** | Inter or IBM Plex Sans, generous spacing | Clean, technical, readable at distance. |
| **Chrome** | Nearly none. One quiet sidebar. | The visualization IS the interface. |
| **Animation** | Subtle, continuous, 60fps | System is alive. Flows move. Not flashy — ambient. |
| **Information density** | Progressive disclosure | Glance -> click zone -> click actor -> full trace. |

### Color Semantics (Consistent Across All Views)

| Color | Meaning |
|---|---|
| Cool blue/teal | Normal, authorized, explained |
| Ghosted/transparent | Provenance-explained (subtracted from view) |
| Amber/copper | Elevated residual, warrants attention |
| Coral/red | High residual, alert |
| White text on dark | Primary information |
| Gray text | Secondary/contextual |

---

## The Investor Demo Walkthrough

1. **Open Murmur.** The Pulse is calm — cool flows, steady rhythm. "This is your system's authorized world model. Everything is flowing as expected."

2. **Point out the ghosted flows.** "These dim connections? That's your CI/CD pipeline, your scheduled jobs, your orchestration. Murmur knows about them — they're authorized. It subtracted them."

3. **Inject the attack** (pre-staged: key creation + secret access by novel actor). Wait one scoring window (15 min).

4. **The Pulse shifts.** A warm thread appears, flowing from IDENTITY toward SECRET. The rhythm disrupts. "Something just entered the system that Murmur can't explain."

5. **Switch to Flow Map.** The IDENTITY->SECRET connection is bright amber while everything else is ghosted. "This flow has no authorization chain. No pattern match. No trigger reference."

6. **Click the bright thread.** Lineage View opens. The authorization chain starts with a broken link — [?] Unknown origin. Two invariants fired. The key was created but never revoked — open closure arc.

7. **The pitch:** "Murmur didn't flag this because it was unusual. It flagged it because it was *unauthorized*. Your legitimate agent swarms produce signals ten times louder — but they have provenance. This doesn't. That's the difference no other security product can see."

---

## Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| **Backend** | FastAPI | Already in stack for API. Lightweight, async. |
| **Frontend** | React 18 + TypeScript | Component model for progressive disclosure views. |
| **Visualization** | D3.js v7 | Full control over the Pulse and Flow Map. Canvas/SVG rendering for particle systems. |
| **Styling** | Tailwind CSS | Dark theme, utility-first, fast iteration. |
| **State** | React Query / SWR | Poll FastAPI endpoints every 15 min (matches scoring window). |
| **Build** | Vite | Fast dev server, simple config. |

### API Endpoints (FastAPI)

| Endpoint | Returns | Used by |
|---|---|---|
| `GET /api/pulse` | Current sigma_coarse, residual_risk summary, system status | Pulse view |
| `GET /api/zones` | Zone flux matrix, event counts per zone, top connections | Flow Map |
| `GET /api/actors/{window}` | Actor list with scores, provenance, closure | Flow Map click-through |
| `GET /api/lineage/{actor_id}` | Trigger chain, invariants fired, closure state | Lineage view |
| `GET /api/alerts` | Current alerts with suggested actions | Alert queue |
| `GET /api/timeline` | Historical residual_risk per actor | Timeline (if needed) |

### Build Approach

Sprint 4 runs in parallel starting after Sprint 1 validation gate passes. Phased:

1. **After Sprint 1 gate:** Scaffold FastAPI endpoints + React app. Build Pulse view with mock data. Validate visual language.
2. **During Sprint 2:** Build Flow Map with mock data. Integrate Pulse with real API (sigma_coarse + basic scoring available).
3. **After Sprint 3:** Build Lineage view. Integrate all views with full API (provenance + closure data available). Polish.
4. **Final:** Demo walkthrough rehearsal. Investor-ready.

---

## Files

| File | Purpose |
|---|---|
| `src/report/api.py` | FastAPI endpoints |
| `src/report/frontend/` | React + D3 app |
| `src/report/frontend/src/views/Pulse.tsx` | Pulse ambient view |
| `src/report/frontend/src/views/FlowMap.tsx` | Zone topology view |
| `src/report/frontend/src/views/Lineage.tsx` | Authorization trace view |
| `src/report/frontend/src/views/AlertQueue.tsx` | Alert list |
| `src/report/frontend/src/components/` | Shared components |
| `src/report/frontend/tailwind.config.js` | Dark theme config |
