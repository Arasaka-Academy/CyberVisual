---
status: complete
priority: p2
issue_id: "001"
tags: [lesson, threejs, hardware-education]
dependencies: []
---

## Problem Statement

Implement the approved Jetson Nano / two serial-driver 42 mm motors / IMX477 interactive lesson in TOPIC.md.

## Findings

The repository contains 57 CAD mesh parts and an SVG assembly figure. It has no 3D lesson or UART hardware adapter. Exact integrated motor SKU is unknown.

## Proposed Solutions

Reuse CAD in a named glTF hierarchy, add procedural reference-envelope electronics, and drive all lessons and the sandbox from a deterministic browser simulation.

## Recommended Action

Approved by the user: implement the full TOPIC.md plan sequentially in this checkout on codex/jetson-pan-tilt-lesson.

## Acceptance Criteria

- [x] Reviewed source-faithful assets and reference documentation
- [x] Five lessons, sandbox placement/wiring/run/stop, and coherent virtual capture
- [x] 18 behavior/asset tests and static production build pass
- [x] 15 browser checks at all three widths, themes, keyboard and reduced motion
- [x] 23 final screenshots, run guide and honest hardware boundary

## Work Log

- 2026-11-06: implementation started; original checkout was clean at 30b5ca7.
- 2026-11-06: completed sequential asset/app/review passes; production and fully offline entries verified. See ACCEPTANCE.md and evidence/browser-report.json. No real hardware, publication or Git delivery was part of this round.
