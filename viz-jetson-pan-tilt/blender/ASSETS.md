# Asset pack

Units: metres. Facing: Blender **−Y**, exported glTF **+Z**. The original CAD uses millimetres and is scaled by 0.001. No clips, textures, downloads or external model licences.

| File / nodes | Pivot and use | Size / source |
| --- | --- | --- |
| gimbal.glb / Base | Fixed origin, source base | 80×80×63 mm CAD |
| gimbal.glb / YawMotor | Fixed stator, includes M3×10 fasteners and illustrative driver | Original 42 mm envelope |
| gimbal.glb / PanPivot | Browser Y axis at origin | Carries YawRotor, UpperStructure, TiltMotor and TiltPivot |
| gimbal.glb / UpperStructure | Origin under PanPivot | Original CAD upper support |
| gimbal.glb / TiltMotor | Origin under PanPivot | Original motor envelope, M3×6 fasteners, illustrative driver |
| gimbal.glb / TiltPivot | Browser [0,0.126,0], rotation −X for positive elevation | Original mechanical axis |
| gimbal.glb / TiltRotor | Origin under PanPivot; follows tilt motor placement and −X tilt rotation | Original motor shaft, separated from stator |
| gimbal.glb / CameraAssembly | Origin under TiltPivot | Carrier, PCB, lens, CSI connector and camera fasteners |
| nano.glb / NanoBoard | Board centre, PCB at 3 mm | 100×80 mm board; layout unverified reference envelope |
| supply.glb / MotorSupply | Ground centre | Generic 39×31 mm enclosure; unrated logical motor supply |

Named connection anchors are exported as empty nodes, with browser coordinates recorded in `app/public/assets/catalog.json`. Camera CSI and optical anchors inherit both pivots; the tilt driver's anchor inherits pan only. The catalog records the CAD SHA-256 and all exported nodes.

`refs/assets.md` records every assumption and source. Main shape references are the existing local assembly/front/top images; the Nano uses a dimension blockout because reference image downloads were not requested. This is below an exact carrier-revision product model, and the driver caps do not establish physical fit.

Previews are generated at `blender/previews/`. Original CAD triangles are not decimated. GLB materials are single-sided. The behavior tests check exported hierarchy, moving anchors and preservation of each original CAD triangle count.
