# Reference sheets · 2026-11-06

All geometry is local/procedural; no external models, textures or photographs are redistributed.

## Gimbal and camera

- Exact source: `models/imx477-hq/figure/scene.json` at repository baseline 30b5ca7. The three printable parts, screw geometry, camera PCB and lens reference envelopes are reused without decimation.
- Reference views: existing `figure/preview.png`, `front-preview.png`, `top-preview.png`, `exploded-preview.png` and the source triangulation. Camera nominal dimensions are independently recorded in the existing DESIGN.md and Waveshare mechanical documentation: https://www.waveshare.net/wiki/IMX477_12.3MP_Camera .
- PCB 38×38 mm, hole spacing 30×30 mm. Original motor envelopes 42×42×42 mm, actual integrated driver body unknown. Lens Ø40 mm and assumed PCB thickness are reference envelopes, not measured user hardware.
- Visible parts: original base, upper support, camera carrier, two motor stators/end caps/shafts/plugs, motor and camera fasteners, PCB, C/CS mount, lens rings/glass, CSI latch.
- Facing: Blender -Y / glTF +Z. Pan: Blender Z / glTF Y. Tilt: Blender X / glTF X at height 0.126 m. The optical-axis origin is the lens front.

## Jetson Nano developer-kit reference

- Type: 4 GB Jetson Nano developer-kit reference carrier and module; carrier revision is intentionally unspecified.
- Source: https://developer.nvidia.com/embedded/jetson-nano-developer-kit ; board reference envelope 100×80 mm, consistent with the original project Jetson Nano baseline. Board layout dimensions other than this envelope are illustrative and marked unverified in the catalog.
- Silhouette: green carrier PCB, stacked USB connectors and Ethernet housing along one edge, CSI latch along another, 40-pin header, a raised compute module with a finned black heatsink. Reference view for comparing proportions is a dimension blockout, because external image downloads have not been requested.
- Heatsink footprint 42×42 mm / 18 mm tall, connector placement, header pin pitch representation and module envelope are visual assumptions, not mechanical reference dimensions.
- Ports exported as named anchors represent **logical** UART/CSI links, not exact GPIO pin assignments.

## Integrated UART driver / supply

- No exact Waveshare motor/driver SKU was given. A 38×38 mm dark PCB/control cap is fitted behind each original motor envelope to explain the integrated controller; it is not a supplier's product model or a verified fit.
- Driver details: perimeter mounting screw heads, logic chip, small components and a highlighted logical UART/power attachment. No fake model number, protocol bytes or encoder telemetry.
- Motor supply: a generic dark enclosure with a barrel output; no voltage/current/polarity rating is asserted. Nano supply is assumed available separately; this lesson checks the motor supply logical paths.

## Material and scale checks

Use the original CAD dimensions at 0.001 scale. Keep camera mounts and fasteners single-sided and retain their source topology. Add modest bevels only to new reference electronics, using dark aluminium, green solder mask and metal connector materials. Review exported front, three-quarter and board detail previews before app implementation.
