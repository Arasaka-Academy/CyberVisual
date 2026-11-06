# Jetson Nano 双轴视觉云台 · 3D Lesson

Project: `viz-jetson-pan-tilt/app`, port **5420**. Mode: **lesson**. Look: **Clean ops world, close to the object**, adapted to the existing warm paper/copper assembly figure. Approved 2026-11-06.

## Approved goal

Chinese browser lessons explaining a Jetson Nano controlling two Waveshare 42 mm integrated serial-driver stepper motors over logical UART links, with an IMX477 HQ camera on top returning images over CSI. Five lessons, one primary operation each, plus a build-your-own sandbox. Deliver the interactive app, static build, screenshots and run instructions. The user chose **no film**. Publishing was added to the authorized scope on 2026-11-06, including a main merge/push and the existing GitHub Pages site.

| Lesson | Operation | Observable behavior |
| --- | --- | --- |
| 认识整机 | Assembly slider | Parts travel from a bench tray into the existing CAD assembly |
| 水平转动 | Pan slider, ±90° | The entire upper structure, tilt motor and camera turn around the vertical axis |
| 俯仰转动 | Tilt slider, ±35° | The carrier and camera rotate around the original 126 mm high X axis |
| UART 怎样控制运动 | Send target button | A semantic command travels from Nano to each integrated driver, then both axes move |
| 图像怎样回来 | Capture button | A frame rendered from the actual simulated camera pose travels back over CSI |

Sandbox: place Nano, yaw motor, upper structure, tilt motor, camera and motor supply from the parts tray; wire the logical UART, CSI and power interfaces; report missing parts, missing supply and mismatched connections; Run/Stop; no movement after Stop. Supply and ports are conceptual, not a physical wiring guide.

## Real structure, scale and hierarchy

- Source: `../models/imx477-hq/figure/scene.json` (57 CAD mesh parts) and `parameters.json`; original dimensions are millimetres. Export at 0.001 scale, using glTF's conversion from Blender Z-up to browser Y-up.
- Base and yaw stator stay fixed. Pan rotates around vertical; upper support and tilt stator inherit it. Tilt pivots around the original CAD X axis at Z=126 mm; the carrier, camera and its fasteners inherit both axes. Positive tilt raises the optical axis.
- IMX477 PCB: 38 × 38 mm, 30 × 30 mm hole pitch; source: https://www.waveshare.net/wiki/IMX477_12.3MP_Camera and existing design records. Lens is the existing Ø40 mm reference envelope, not a selected optical model.
- Nano carrier board: nominal 100 × 80 mm developer-kit reference envelope; source: https://developer.nvidia.com/embedded/jetson-nano-developer-kit . Connector locations and heatsink are an illustrative layout, not a mechanical drawing of a specified carrier revision.
- The exact Waveshare integrated driver SKU is unknown. Retain the original 42 mm motor envelopes and show an illustrative onboard driver. UART uses human-readable target messages, without claiming a real baud rate, pinout, addressing scheme, measured position or acknowledgement.
- IMX477 CSI and motor connections are logical paths with named anchors; moving endpoints are calculated from the same transforms as the model. Flexible cables are illustrative and are not validated bend-radius or routing designs. No unlimited pan.

## Style card

Visual thesis: a precise, quiet engineering workbench with real CAD proportions, dark motor laminations, pale printed supports and a restrained copper highlight.

Content: title and chapter navigation; a dominant 3D workbench beside the current explanation; a single primary lesson control; compact pose readouts; previous/next navigation. The sandbox expands the explanation area into a parts tray and logical port editor.

Interaction: parts slide from their tray to assembly positions; a selected axis uses a restrained arc and local material emphasis; semantic UART and CSI packets move along anchored connections only when the relevant process is active.

| Attribute | Choice |
| --- | --- |
| Camera | Close three-quarter view, about 28–35° elevation; 32° FOV; fit board and gimbal; stage-specific targets with smooth transitions |
| Palette | Paper #f4f3ee; panel #ffffff; ink #252c2a; muted #727b76; copper #a45b32; pale supports #e2e0d8; motor #303638; data teal #2d827b |
| Light | Large warm key from front-left, soft contact shadows, neutral fill, no bloom |
| Materials | Matte supports, brushed end caps, dark laminations, green PCB, restrained blue lens glass |
| Density | Model is the primary surface; only current chapter labels; no KPI dashboard |
| Themes | Paper, graphite, blueprint; scene and UI change together; remembered locally |
| References | Existing `figure/preview.png`; https://ciechanow.ski/gears/ ; https://ciechanow.ski/cameras-and-lenses/ . References guide pedagogy and composition, not copied assets or text. |

No external model/image/audio downloads are required. Existing local CAD and procedural reference-envelope assets are used. Build Nano and illustrative integrated drivers in the installed Blender 3.6 with compatible static glTF export; record assumptions and inspect the exported assets before starting the app pass.

## Architecture and acceptance

- Independent Vite + React + React Three Fiber + drei application. Exact dependency versions and lockfile. Relative asset URLs for a static subdirectory deployment.
- One simulation state owns assembly, pan, tilt, UART/capture phases and sandbox. Fixed time increments; reduced-motion support; switching chapter resets that chapter; reset is always available. No real serial or camera access.
- The image is rendered from a dedicated virtual camera with the current pan/tilt pose and explicitly labelled as virtual. Captured image and pose metadata remain paired.
- Unit tests cover transform composition, command timing, invalid wiring, missing power and Stop freezing the sandbox. Browser acceptance at 1920×1080, 1280×720 and 390 px, all themes, keyboard, reduced motion, reload, all lessons and sandbox.
- Inspect screenshots for incorrect axis hierarchy, intersections, unattached cable endpoints, unreadable labels, model clipping and mobile overflow. Record real browser results and remaining physical-hardware gaps.

## Progress

- [x] Pass 1: CAD asset conversion, procedural board/driver models, references and asset review
- [x] Pass 2: simulation, five lessons, sandbox and themes
- [x] Acceptance: 18 behavior/asset tests, production build, 15 browser checks, 23 screenshots and documentation

Final results: [ACCEPTANCE.md](ACCEPTANCE.md). Direct-open offline build: `app/dist/lesson.html`.
