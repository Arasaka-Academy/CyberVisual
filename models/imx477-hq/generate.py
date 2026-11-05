#!/usr/bin/env python3
"""Generate millimetre 3MFs and the exact mesh scene used by the anatomy figure.

Python 3.12+: trimesh, manifold3d, numpy, scipy, shapely, rtree, lib3mf.
Run from any directory. Original user-supplied meshes are never overwritten.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import manifold3d as mf
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent if (HERE.parent / "底座.STL").is_file() else HERE / "inputs"
OUT = HERE / "print"
FIGURE = HERE / "figure"
PARAM = {
    "revision": "C-centred-camera-and-lens",
    "unit": "mm",
    "pcb_width": 38.0,
    "pcb_height": 38.0,
    "pcb_thickness_assumed": 1.6,
    "pcb_hole_diameter": 2.5,
    "pcb_hole_pitch": 30.0,
    "pcb_rear_clearance": 5.0,
    "camera_mount_clearance_hole": 2.8,
    "camera_support_diameter": 6.0,
    "camera_back_frame_size": [46.0, 46.0, 3.0],
    "camera_back_frame_opening": [28.0, 28.0],
    "camera_nut_pocket_across_flats": 5.3,
    "camera_nut_pocket_depth": 1.5,
    "camera_nut_across_flats": 5.0,
    "camera_nut_thickness": 2.0,
    "camera_washer_thickness": 0.5,
    "camera_washer_maximum_diameter": 5.5,
    "camera_screw_length": 12.0,
    "camera_screw_head_diameter": 4.5,
    "camera_screw_head_height": 2.5,
    "camera_screw_stack_nominal": 10.6,
    "camera_screw_tip_beyond_nut_nominal": 1.4,
    "shaft_bore_diameter": 5.3,
    "shaft_bore_flat_offset": 2.1,
    "shaft_bore_depth": 18.5,
    "m3_tap_pilot": 2.6,
    "upper_counterbore_diameter": 6.2,
    "upper_counterbore_depth": 2.2,
    "upper_remaining_grip": 2.8,
    "m3x6_thread_engagement": 3.2,
    "camera_pcb_back_centre": [0.0, 27.8, 126.0],
    "camera_height_above_tilt_axis": 0.0,
    "camera_neutral_envelope_centre_xy": [0.0, 0.0],
    "camera_neutral_envelope_size": [40.0, 55.6, 40.0],
    "camera_centering_basis": "Neutral PCB, lens, C/CS seat and connector envelope; not centre of mass.",
    "tilt_motor_translation_from_source": [62.0, 0.0, 37.0],
    "yaw_head_clearance_recess_depth": 2.0,
    "tilt_axis_z": 126.0,
    "reference_lens_diameter": 40.0,
    "reference_lens_front_y": -27.8,
    "pitch_check_range_degrees": [-35, 35],
    "pitch_check_step_degrees": 1,
    "hardware": {"M3x10": 4, "M3x6": 4, "M3x5": 1, "M2.5x12": 4,
                 "M2.5_hex_nut_AF5_thickness2": 4, "M2.5_insulating_washer_thickness0.5": 4},
}
CAMERA_X, PCB_BACK_Y, CAMERA_Z = PARAM["camera_pcb_back_centre"]
TILT_Z = PARAM["tilt_axis_z"]
MOTOR_TRANSLATION = PARAM["tilt_motor_translation_from_source"]
CAMERA_HOLES = tuple(itertools.product((CAMERA_X - 15, CAMERA_X + 15),
                                     (CAMERA_Z - 15, CAMERA_Z + 15)))
PCB_BACK_Y = PARAM["camera_pcb_back_centre"][1]
PCB_FRONT_Y = PCB_BACK_Y - PARAM["pcb_thickness_assumed"]
FRAME_FRONT_Y = PCB_BACK_Y + PARAM["pcb_rear_clearance"]
FRAME_BACK_Y = FRAME_FRONT_Y + PARAM["camera_back_frame_size"][2]
NUT_SEAT_Y = FRAME_BACK_Y - PARAM["camera_nut_pocket_depth"]
SCREW_SEAT_Y = PCB_FRONT_Y - PARAM["camera_washer_thickness"]


def box(lo, hi):
    lo, hi = np.array(lo, float), np.array(hi, float)
    return mf.Manifold.cube(tuple(hi - lo)).translate(tuple(lo))


def cylinder(axis, centre, start, end, radius, segments=72):
    value = mf.Manifold.cylinder(end - start, radius, circular_segments=segments)
    if axis == "x":
        value = value.rotate((0, 90, 0))
        return value.translate((start, centre[0], centre[1]))
    if axis == "y":
        value = value.rotate((-90, 0, 0))
        return value.translate((centre[0], start, centre[1]))
    return value.translate((centre[0], centre[1], start))


def union(*values):
    return mf.Manifold.batch_boolean(values, mf.OpType.Add)


def polygon_xz(points, y0, y1):
    # Local (u,v,w) = (world x, -world z, world y), determinant +1.
    polygon = [(x, -z) for x, z in points]
    area2 = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
    section = mf.CrossSection([polygon if area2 > 0 else polygon[::-1]])
    value = mf.Manifold.extrude(section, y1 - y0)
    return value.transform(((1, 0, 0, 0), (0, 0, 1, y0), (0, -1, 0, 0)))


def mesh_of(value):
    # Eliminate boolean seams shorter than 0.001 micrometre before exporting.
    # Coplanar boolean seams can otherwise leave zero-area triangles.
    raw = value.simplify(1e-6).to_mesh64()
    result = trimesh.Trimesh(vertices=np.asarray(raw.vert_properties)[:, :3],
                             faces=np.asarray(raw.tri_verts), process=True)
    result.remove_unreferenced_vertices()
    return result


def solid_of(mesh):
    return mf.Manifold(mf.Mesh(np.asarray(mesh.vertices, dtype=np.float32),
                               np.asarray(mesh.faces, dtype=np.uint32)))


def load_sources():
    base = trimesh.load_mesh(SOURCE / "底座.STL")
    base.apply_transform(np.array([[1, 0, 0, -40], [0, 0, -1, 40],
                                    [0, 1, 0, 0], [0, 0, 0, 1]], float))
    upper = trimesh.load_mesh(SOURCE / "上座.STL")
    index = np.argmax(np.where(upper.face_normals[:, 0] > .99, upper.area_faces, 0))
    n = upper.face_normals[index]
    c, s = n[0], -n[2]
    upper.apply_transform(np.array([
        [c, 0, -s, -c * 64.85 + s * 40],
        [-s, 0, -c, s * 64.85 + c * 40],
        [0, 1, 0, -.295], [0, 0, 0, 1],
    ]))
    # The supplied 5 mm plate has no head pockets: M3x6 otherwise engages only
    # 1 mm. Keep its shape/interfaces, add four 2.2 mm deep head recesses.
    u = solid_of(upper)
    for y, z in itertools.product((-15.5, 15.5), (73.5, 104.5)):
        u -= cylinder("x", (y, z), -16.03, -13.8, 3.1)
    # The source base's head pockets are 1.4 mm deep. A 3 mm socket head
    # protrudes 1.6 mm; an annular relief keeps the rotating upper clear of it.
    relief = cylinder("z", (0, 0), 62.99, 65.0, 25.5)
    relief -= cylinder("z", (0, 0), 62.9, 65.1, 18.5)
    u -= relief
    # Keep the source yaw socket and the relieved base. Rehome its actual
    # tilt motor plate, holes and counterbores onto a raised, braced arm.
    lower = u ^ box((-40, -30, 62), (25, 30, 68.0004))
    yaw_socket = u ^ box((-8, -8, 67.9), (8, 8, 74))
    motor_plate = (u ^ box((-16.1, -21.1, 68.0005), (-10.9, 21.1, 110.1))).translate(MOTOR_TRANSLATION)
    beam = box((14, -21, 65.5), (51, 21, 73))
    column = box((46, -21, 72), (51, 21, 105.2))
    ribs = [polygon_xz([(16, 72), (46.2, 72), (46.2, 104)], y0, y1)
            for y0, y1 in [(-21, -16), (16, 21)]]
    centred_upper = union(lower, yaw_socket, motor_plate, beam, column, *ribs)
    return base, mesh_of(centred_upper), float(math.degrees(math.atan2(s, c)))


def carrier():
    # Camera is in the XZ plane, optical axis -Y, tilt shaft along X.
    # Four 5 mm bosses support only the PCB mounting corners. Metal nuts
    # carry the screw threads; no printed M2.5 thread or snap retention.
    ring = box((CAMERA_X - 23, FRAME_FRONT_Y, CAMERA_Z - 23),
               (CAMERA_X + 23, FRAME_BACK_Y, CAMERA_Z + 23))
    ring -= box((CAMERA_X - 14, FRAME_FRONT_Y - .1, CAMERA_Z - 14),
                (CAMERA_X + 14, FRAME_BACK_Y + .1, CAMERA_Z + 14))
    values = [ring]
    for centre in CAMERA_HOLES:
        values.append(cylinder("y", centre, PCB_BACK_Y, FRAME_FRONT_Y + .1,
                               PARAM["camera_support_diameter"] / 2))
    hub = box((-38, -7, 82), (-18, 7, 96))
    # Radial bore flat is on +Y, matching the radial M3 pilot.
    bore = cylinder("x", (0, 89), -36.5, -17.9, 2.65)
    bore = bore ^ box((-36.6, -3, 86), (-17.8, 2.1, 92))
    hub = hub.translate(MOTOR_TRANSLATION)
    # An outboard arm clears the Ø40 lens, then wraps behind the PCB.
    # Its back spreader joins the frame between the two right mounting nuts.
    side_arm = box((21, 0, TILT_Z - 7), (28, FRAME_BACK_Y, TILT_Z + 7))
    spreader = box((14, FRAME_FRONT_Y, TILT_Z - 7), (28, FRAME_BACK_Y, TILT_Z + 7))
    body = union(*values, hub, side_arm, spreader)
    # Cut after joining the side arm, which overlaps the blind shaft bore.
    # Cutting the hub first would let the arm refill the shaft-tip clearance.
    body -= bore.translate(MOTOR_TRANSLATION)
    body -= cylinder("y", (-23, 89), 2.0, 7.1, 1.3).translate(MOTOR_TRANSLATION)
    for centre in CAMERA_HOLES:
        body -= cylinder("y", centre, PCB_BACK_Y - .1, FRAME_BACK_Y + .1,
                         PARAM["camera_mount_clearance_hole"] / 2)
        body -= cylinder("y", centre, NUT_SEAT_Y, FRAME_BACK_Y + .1,
                         PARAM["camera_nut_pocket_across_flats"] / math.sqrt(3), 6)
    return body


def grounded(mesh):
    result = mesh.copy()
    result.apply_translation(-result.bounds[0])
    return result


def print_meshes(base, upper, body):
    body = body.copy()
    body.apply_transform(np.array([[0, -1, 0, 0], [0, 0, 1, 0],
                                   [-1, 0, 0, 0], [0, 0, 0, 1]], float))
    return {"01-base": grounded(base), "02-upper-m3x6": grounded(upper),
            "03-camera-carrier": grounded(body)}


NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
ET.register_namespace("", NS)


def write_3mf(path, meshes, positions=None):
    model = ET.Element(f"{{{NS}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    for name, value in [("Title", "CyberVisual IMX477 HQ printable parts"),
                        ("Designer", "CyberVisual"),
                        ("Description", "Unsliced geometry; use PETG. Original STL units interpreted as mm. See README.zh-CN.md.")]:
        ET.SubElement(model, f"{{{NS}}}metadata", {"name": name}).text = value
    resources = ET.SubElement(model, f"{{{NS}}}resources")
    materials = ET.SubElement(resources, f"{{{NS}}}basematerials", {"id": "1"})
    colours = ["#D8D8D8FF", "#C5C9CEFF", "#F09D56FF", "#F5BC79FF"]
    for name, colour in zip(meshes, colours):
        ET.SubElement(materials, f"{{{NS}}}base", {"name": name, "displaycolor": colour})
    build = ET.SubElement(model, f"{{{NS}}}build")
    for i, (name, mesh) in enumerate(meshes.items()):
        item = ET.SubElement(resources, f"{{{NS}}}object", {
            "id": str(i + 2), "type": "model", "name": name, "pid": "1", "pindex": str(i)})
        geometry = ET.SubElement(item, f"{{{NS}}}mesh")
        vertices = ET.SubElement(geometry, f"{{{NS}}}vertices")
        for x, y, z in mesh.vertices:
            ET.SubElement(vertices, f"{{{NS}}}vertex", {"x": f"{x:.6f}", "y": f"{y:.6f}", "z": f"{z:.6f}"})
        triangles = ET.SubElement(geometry, f"{{{NS}}}triangles")
        for a, b, c in mesh.faces:
            ET.SubElement(triangles, f"{{{NS}}}triangle", {"v1": str(a), "v2": str(b), "v3": str(c)})
        xyz = (positions or {}).get(name, (0, 0, 0))
        ET.SubElement(build, f"{{{NS}}}item", {"objectid": str(i + 2),
            "transform": "1 0 0 0 1 0 0 0 1 " + " ".join(str(v) for v in xyz)})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))


def camera_reference():
    pcb = box((-60, -17.6, 76), (-22, -16, 114))
    for x, z in itertools.product((-56, -26), (80, 110)):
        pcb -= cylinder("y", (x, z), -17.7, -15.9, 1.25)
    parts = {
        "camera-pcb": pcb,
        "camera-cs-seat": cylinder("y", (-41, 95), -27.6, -17.6, 14),
        "camera-cs-ring": cylinder("y", (-41, 95), -32.6, -27.6, 15),
        "lens-rear": cylinder("y", (-41, 95), -39.6, -32.6, 17),
        "lens-aperture": cylinder("y", (-41, 95), -45.6, -39.6, 19),
        "lens-focus": cylinder("y", (-41, 95), -63.6, -45.6, 20),
        "lens-rim": cylinder("y", (-41, 95), -70.6, -63.6, 19),
        "lens-glass": cylinder("y", (-41, 95), -71.6, -70.6, 15.5),
        "csi-connector": box((-52, -21.2, 76), (-30, -17.6, 79)),
        "csi-latch": box((-52, -22, 76), (-30, -21.2, 77.5)),
    }
    return {name: val.translate((CAMERA_X + 41, PCB_BACK_Y + 16, CAMERA_Z - 95))
            for name, val in parts.items()}


def hardware_reference():
    objects = {}
    # The reference motors show only their external envelope and seams.
    for tag, x0, x1 in [("front", -11, -5), ("stack", -5, 25), ("rear", 25, 31)]:
        objects["tilt-motor-" + tag] = box((x0, -21, 68), (x1, 21, 110))
    objects["tilt-shaft"] = cylinder("x", (0, 89), -35, -11, 2.5) - box((-35.1, 2, 86), (-10.9, 3, 92))
    objects["tilt-plug"] = box((25, -7, 110), (31, 7, 114))
    for tag, z0, z1 in [("rear", 13, 19), ("stack", 19, 49), ("front", 49, 55)]:
        objects["yaw-motor-" + tag] = box((-21, -21, z0), (21, 21, z1))
    objects["yaw-shaft"] = cylinder("z", (0, 0), 55, 73, 2.5) - box((-3, -3, 55), (3, -2, 73))
    objects["yaw-plug"] = box((-7, -25, 13), (7, -21, 19))
    for i, (x, y) in enumerate(itertools.product((-15.5, 15.5), repeat=2)):
        objects[f"m3x10-{i}-shank"] = cylinder("z", (x, y), 51.6, 61.6, 1.5, 24)
        objects[f"m3x10-{i}-head"] = cylinder("z", (x, y), 61.6, 64.6, 2.75, 48) - cylinder("z", (x, y), 63.1, 64.7, 1.35, 6)
    for i, (y, z) in enumerate(itertools.product((-15.5, 15.5), (73.5, 104.5))):
        objects[f"m3x6-{i}-shank"] = cylinder("x", (y, z), -13.8, -7.8, 1.5, 24)
        objects[f"m3x6-{i}-head"] = cylinder("x", (y, z), -16.8, -13.8, 2.75, 48) - cylinder("x", (y, z), -16.9, -15.3, 1.35, 6)
    objects["m3x5-shank"] = cylinder("y", (-23, 89), 2, 7, 1.5, 24)
    objects["m3x5-head"] = cylinder("y", (-23, 89), 7, 10, 2.75, 48) - cylinder("y", (-23, 89), 8.5, 10.1, 1.35, 6)
    for name in list(objects):
        if name.startswith(("tilt", "m3x6", "m3x5")):
            objects[name] = objects[name].translate(MOTOR_TRANSLATION)
    for i, centre in enumerate(CAMERA_HOLES):
        objects[f"m2p5x12-{i}-shank"] = cylinder("y", centre, SCREW_SEAT_Y,
            SCREW_SEAT_Y + PARAM["camera_screw_length"], 1.25, 36)
        objects[f"m2p5x12-{i}-head"] = cylinder("y", centre,
            SCREW_SEAT_Y - PARAM["camera_screw_head_height"], SCREW_SEAT_Y,
            PARAM["camera_screw_head_diameter"] / 2, 48) - cylinder("y", centre,
            SCREW_SEAT_Y - 2.6, SCREW_SEAT_Y - 1.2, 2 / math.sqrt(3), 6)
        objects[f"m2p5-washer-{i}"] = cylinder("y", centre, SCREW_SEAT_Y, PCB_FRONT_Y,
            PARAM["camera_washer_maximum_diameter"] / 2, 48) - cylinder("y", centre,
            SCREW_SEAT_Y - .1, PCB_FRONT_Y + .1, 1.35, 36)
        objects[f"m2p5-nut-{i}"] = cylinder("y", centre, NUT_SEAT_Y,
            NUT_SEAT_Y + PARAM["camera_nut_thickness"],
            PARAM["camera_nut_across_flats"] / math.sqrt(3), 6) - cylinder("y", centre,
            NUT_SEAT_Y - .1, NUT_SEAT_Y + PARAM["camera_nut_thickness"] + .1, 1.25, 36)
    return objects


def validate_parts(parts):
    report = {}
    for name, mesh in parts.items():
        report[name] = {
            "watertight": bool(mesh.is_watertight), "consistent_winding": bool(mesh.is_winding_consistent),
            "connected_components": len(mesh.split(only_watertight=False)),
            "vertices": len(mesh.vertices), "triangles": len(mesh.faces),
            "size_mm": np.round(mesh.extents, 5).tolist(), "volume_mm3": round(float(mesh.volume), 4),
            "minimum_z_mm": round(float(mesh.bounds[0, 2]), 7),
        }
        r = report[name]
        assert r["watertight"] and r["consistent_winding"] and r["connected_components"] == 1 and mesh.volume > 0, (name, r)
        assert abs(mesh.bounds[0, 2]) < 1e-5, (name, "off print bed")
    return report


def validate_3mf(path, count):
    import lib3mf
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.ReadFromFile(str(path))
    warnings = [reader.GetWarning(i) for i in range(reader.GetWarningCount())]
    iterator = model.GetBuildItems()
    n = 0
    while iterator.MoveNext():
        n += 1
    assert n == count, (path, n)
    assert not warnings, (path, warnings)
    # Reopen through an independent mesh importer, including build transforms.
    scene = trimesh.load(path, force="scene")
    assert len(scene.geometry) == count
    return {"lib3mf_build_items": n, "lib3mf_warnings": warnings,
            "trimesh_geometry_count": len(scene.geometry), "bounds_mm": np.round(scene.bounds, 4).tolist()}


def overlap_volume(a, b):
    ab = np.asarray(a.bounding_box()).reshape(2, 3)
    bb = np.asarray(b.bounding_box()).reshape(2, 3)
    if np.any(ab[1] <= bb[0]) or np.any(bb[1] <= ab[0]):
        return 0.
    return (a ^ b).volume()


def camera_fasteners(hardware):
    return {n: v for n, v in hardware.items() if n.startswith("m2p5")}


def validate_assembly(base, upper, body, hardware, camera):
    fixed = {"base": solid_of(base), "upper": solid_of(upper)}
    fixed.update({name: val for name, val in hardware.items() if "motor-" in name or name.endswith("-plug")})
    fixed.update({n: v for n, v in hardware.items() if n.startswith(("m3x6", "m3x10")) and n.endswith("head")})
    moving = {"carrier": body, **camera, **camera_fasteners(hardware),
              "tilt-shaft": hardware["tilt-shaft"],
              **{n: v for n, v in hardware.items() if n.startswith("m3x5")}}
    collisions = []
    min_gap = 99.
    for degrees in range(-35, 36):
        for name, value in moving.items():
            posed = value.translate((0, 0, -TILT_Z)).rotate((degrees, 0, 0)).translate((0, 0, TILT_Z))
            for target, still in fixed.items():
                volume = overlap_volume(posed, still)
                if volume > .002:
                    collisions.append({"angle": degrees, "moving": name, "fixed": target, "intersection_mm3": round(volume, 5)})
                if target == "upper" and name == "carrier":
                    min_gap = min(min_gap, posed.min_gap(still, 10))
    seated_collisions = []
    cam_hw = camera_fasteners(hardware)
    pairs = [("carrier", n) for n in [*camera, *cam_hw]]
    pairs.append(("carrier", "tilt-shaft"))
    pairs += list(itertools.product(cam_hw, camera))
    pairs += list(itertools.combinations(cam_hw, 2))
    for a, b in pairs:
        volume = overlap_volume(moving[a], moving[b])
        if volume > .002:
            seated_collisions.append({"a": a, "b": b, "intersection_mm3": round(volume, 5)})
    return {"angles_degrees": [-35, 35], "sample_step_degrees": 1,
            "sample_count": 71, "collisions": collisions, "seated_collisions": seated_collisions,
            "carrier_to_upper_min_gap_mm": round(min_gap, 4),
            "scope": "Rigid printed parts, all camera screws/nuts/washers, motor screw heads, reference motors and stated reference lens; excludes cable motion, loads and real hardware."}


def phase(s, a, b):
    return max(0., min(1., (s - a) / (b - a)))


def validate_yaw(base, upper, hardware):
    # A head can intersect a rotating base even if it clears in one pose.
    fixed = {"base": solid_of(base), **{n: v for n, v in hardware.items() if n.startswith("m3x10") and n.endswith("head")}}
    collisions = []
    u = solid_of(upper)
    for degrees in range(0, 360, 5):
        posed = u.rotate((0, 0, degrees))
        for name, val in fixed.items():
            volume = (posed ^ val).volume()
            if volume > .002:
                collisions.append({"angle": degrees, "fixed": name, "intersection_mm3": round(volume, 5)})
    return {"sample_step_degrees": 5, "sample_count": 72, "collisions": collisions,
            "scope": "Upper seat versus base and four original M3 socket heads; excludes cable twisting and yaw stops."}


def disassembly_offset(name, s):
    movement = phase(s, .65, 1)
    group = np.array((-20 * movement, 0, 15 * movement))
    if name.startswith(("m2p5x12", "m2p5-washer")):
        # Withdraw fully before moving outward, away from the reference lens.
        i = int(name.split("-")[1 if name.startswith("m2p5x12") else 2])
        side = -1 if CAMERA_HOLES[i][0] < CAMERA_X else 1
        return group + (14 * side * phase(s, .16, .28), -18 * phase(s, 0, .16), 0)
    if name.startswith("m2p5-nut"):
        return group + (0, 4 * phase(s, .55, .65), 0)
    if name.startswith(("camera-", "lens-", "csi-")) and name != "camera-carrier":
        return group + (0, -30 * phase(s, .3, .55), 0)
    return group


def validate_disassembly(body, camera, hardware, base, upper):
    collisions = []
    cam_hw = camera_fasteners(hardware)
    parts = {"carrier": body, **camera, **cam_hw}
    pairs = [("carrier", n) for n in [*camera, *cam_hw]]
    pairs += list(itertools.product(cam_hw, camera))
    pairs += list(itertools.combinations(cam_hw, 2))
    for s in np.linspace(0, 1, 81):
        posed = {n: v.translate(disassembly_offset(n, float(s))) for n, v in parts.items()}
        for a, b in pairs:
            volume = overlap_volume(posed[a], posed[b])
            if volume > .002:
                collisions.append({"share": round(float(s), 4), "a": a, "b": b, "intersection_mm3": round(volume, 5)})
        common = (0, 0, 15 * phase(float(s), .65, 1))
        fixed = {"base": solid_of(base), "upper": solid_of(upper).translate(common)}
        for name, value in hardware.items():
            if "motor-" in name or name.endswith(("-plug", "-shaft")) and not name.startswith(("m3", "m2p5")) or name.startswith(("m3x6", "m3x10")) and name.endswith("head"):
                fixed[name] = value.translate(common) if name.startswith(("tilt", "m3x6")) else value
        for a, one in posed.items():
            for b, two in fixed.items():
                volume = overlap_volume(one, two)
                if volume > .002:
                    collisions.append({"share": round(float(s), 4), "a": a, "b": b, "intersection_mm3": round(volume, 5)})
    return {"sample_count": 81, "collisions": collisions,
            "scope": "Camera screws/washer withdrawal then outward movement; camera forward, nuts rearward, carrier leaves actual reference D shaft. Includes upper, base, motor envelopes and motor screw heads. Does not model helical thread motion, loose-nut handling or hand/tool reach."}


def validate_combined_pan_pitch(base, body, camera, hardware):
    fixed = solid_of(base)
    collisions = []
    base_lo, base_hi = base.bounds
    for pitch in range(-35, 36, 5):
        for yaw in range(0, 360, 15):
            for name, val in {"carrier": body, **camera, **camera_fasteners(hardware)}.items():
                value = val.translate((0, 0, -TILT_Z)).rotate((pitch, 0, 0)).translate((0, 0, TILT_Z)).rotate((0, 0, yaw))
                bounds = np.asarray(value.bounding_box()).reshape(2, 3)
                if np.any(bounds[1] <= base_lo) or np.any(bounds[0] >= base_hi):
                    continue
                volume = (value ^ fixed).volume()
                if volume > .002:
                    collisions.append({"pitch": pitch, "yaw": yaw, "moving": name, "intersection_mm3": round(volume, 5)})
    return {"pitch_step_degrees": 5, "yaw_step_degrees": 15, "sample_count": 360,
            "collisions": collisions, "scope": "Moving camera, all camera fasteners, reference lens and carrier versus the real original base through combined pan/pitch samples; excludes flexible wiring."}


def validate_camera_mount(body, hardware):
    holes = np.asarray(CAMERA_HOLES)
    assert np.allclose(np.ptp(holes, axis=0), [30, 30])
    shanks = {n: v for n, v in hardware.items() if n.startswith("m2p5x12") and n.endswith("shank")}
    clearance_volumes = []
    for centre in CAMERA_HOLES:
        gauge = cylinder("y", centre, PCB_BACK_Y, FRAME_BACK_Y,
                         PARAM["camera_mount_clearance_hole"] / 2 - .001)
        clearance_volumes.append(round(overlap_volume(gauge, body), 7))
    assert max(clearance_volumes) < .002, "Camera mounting bores obstructed"
    stack = (PARAM["camera_washer_thickness"] + PARAM["pcb_thickness_assumed"]
             + PARAM["pcb_rear_clearance"] + PARAM["camera_back_frame_size"][2]
             - PARAM["camera_nut_pocket_depth"] + PARAM["camera_nut_thickness"])
    protrusion = PARAM["camera_screw_length"] - stack
    assert 1. <= protrusion <= 2.0
    assert len(shanks) == 4
    # Four screw/washer stacks and nuts must clear the actual carrier at rest.
    assert not any(overlap_volume(v, body) > .002 for v in camera_fasteners(hardware).values())
    # Rear-insertion gauges for the four nuts, matching their real hex shape.
    insertion_collisions = []
    for name, value in camera_fasteners(hardware).items():
        if not name.startswith("m2p5-nut"):
            continue
        for d in np.linspace(0, 4, 17):
            volume = overlap_volume(value.translate((0, float(d), 0)), body)
            if volume > .002:
                insertion_collisions.append({"nut": name, "rearward_mm": float(d), "intersection_mm3": volume})
    assert not insertion_collisions
    return {"hole_centres_xz_mm": holes.tolist(), "hole_pitch_xz_mm": [30, 30],
            "camera_screws": len(shanks), "printed_bore_gauge_intersections_mm3": clearance_volumes,
            "nominal_stack_including_nut_mm": round(stack, 4),
            "nominal_tip_beyond_nut_mm": round(protrusion, 4),
            "nut_insertion_sample_count": 68, "nut_insertion_collisions": insertion_collisions,
            "scope": "Nominal 1.6mm PCB, 0.5mm washer, 2mm hex nut; plain screw thread envelope, not actual thread engagement, torque, tool-access or PCB component validation."}


def scene_part(name, value, category, explode):
    mesh = value if isinstance(value, trimesh.Trimesh) else mesh_of(value)
    # Keep the original accurate triangles; no bounding-box stand-ins.
    return {"name": name, "category": category, "explode": explode,
            "vertices": np.round(mesh.vertices, 5).tolist(), "faces": mesh.faces.tolist()}


def validate_centering(base, camera):
    camera_bounds = np.asarray(union(*camera.values()).bounding_box()).reshape(2, 3)
    base_centre = base.bounds.mean(axis=0)
    camera_centre = camera_bounds.mean(axis=0)
    offset = camera_centre[:2] - base_centre[:2]
    assert np.allclose(offset, 0, atol=1e-5), ("Camera not centred", offset)
    assert np.allclose(camera_centre, [0, 0, TILT_Z], atol=1e-5)
    return {"neutral_camera_bounds_mm": camera_bounds.round(5).tolist(),
            "base_centre_xy_mm": base_centre[:2].round(5).tolist(),
            "camera_envelope_centre_mm": camera_centre.round(5).tolist(),
            "centre_offset_xy_mm": offset.round(5).tolist(),
            "scope": "At zero pitch: real PCB shape and stated reference C/CS lens/connector envelopes, excluding mount and motor. This is geometric centring, not mass balance or a guarantee for another lens."}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURE.mkdir(parents=True, exist_ok=True)
    base, upper, angle = load_sources()
    body = carrier()
    body_mesh = mesh_of(body)
    parts = print_meshes(base, upper, body_mesh)
    report = {"parameters": PARAM, "source_upper_unrotation_degrees": angle,
              "parts": validate_parts(parts), "sources_sha256": {}}
    for p in SOURCE.glob("*.STL"):
        report["sources_sha256"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    # Rev B supersedes the generated Rev A snap cap. Original input STLs stay.
    for ext in ("stl", "3mf"):
        (OUT / f"04-snap-cap.{ext}").unlink(missing_ok=True)
    for name, mesh in parts.items():
        mesh.export(OUT / f"{name}.stl")
        write_3mf(OUT / f"{name}.3mf", {name: mesh})
    positions = {"01-base": (5, 5, 0), "02-upper-m3x6": (100, 5, 0),
                 "03-camera-carrier": (100, 60, 0)}
    write_3mf(OUT / "IMX477-HQ-print-layout.3mf", parts, positions)
    report["three_mf"] = {p.name: validate_3mf(p, len(parts) if "layout" in p.name else 1) for p in OUT.glob("*.3mf")}
    hardware, camera = hardware_reference(), camera_reference()
    report["camera_centering"] = validate_centering(base, camera)
    report["camera_mount"] = validate_camera_mount(body, hardware)
    report["assembly"] = validate_assembly(base, upper, body, hardware, camera)
    report["yaw"] = validate_yaw(base, upper, hardware)
    report["disassembly"] = validate_disassembly(body, camera, hardware, base, upper)
    report["combined_pan_pitch"] = validate_combined_pan_pitch(base, body, camera, hardware)
    scene = [scene_part("base", base, "base", [0, 0, 0]),
             scene_part("upper", upper, "structure", [0, 0, 15]),
             scene_part("camera-carrier", body_mesh, "new", [-20, 0, 15])]
    for name, val in hardware.items():
        offset = (disassembly_offset(name, 1).tolist() if name.startswith("m2p5") else
                  [-20, 8, 15] if name.startswith("m3x5") else
                  [0, 0, 15] if name.startswith("tilt") or name.startswith("m3x6") else [0, 0, 0])
        scene.append(scene_part(name, val, "fastener" if name.startswith(("m3", "m2p5")) else "motor", offset))
    for name, val in camera.items():
        scene.append(scene_part(name, val, "glass" if name == "lens-glass" else "camera", [-20, -30, 15]))
    (FIGURE / "scene.json").write_text(json.dumps({"parameters": PARAM, "parts": scene}, ensure_ascii=False, separators=(",", ":")))
    (HERE / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (HERE / "parameters.json").write_text(json.dumps(PARAM, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"parts": report["parts"], "three_mf": report["three_mf"], "assembly": report["assembly"]}, ensure_ascii=False, indent=2))
    assert not report["assembly"]["collisions"], "Pitch envelope has collisions; see validation.json"
    assert not report["assembly"]["seated_collisions"], "Camera retention has collisions; see validation.json"
    assert not report["yaw"]["collisions"], "Yaw head clearance has collisions; see validation.json"
    assert not report["disassembly"]["collisions"], "Disassembly sequence has collisions; see validation.json"
    assert not report["combined_pan_pitch"]["collisions"], "Combined pan/pitch has collisions; see validation.json"
    print("CAD validation passed")


if __name__ == "__main__":
    main()
