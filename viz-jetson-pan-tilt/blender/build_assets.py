"""Export local CAD and procedural reference electronics. Blender 3.6+; no downloads."""
import bpy
import json
import math
import hashlib
from pathlib import Path
from mathutils import Vector

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
OUT = PROJECT / 'app/public/assets'
PREVIEWS = HERE / 'previews'
OUT.mkdir(parents=True, exist_ok=True)
PREVIEWS.mkdir(parents=True, exist_ok=True)
SOURCE = REPO / 'models/imx477-hq/figure/scene.json'
data = json.loads(SOURCE.read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, color, metal=0, rough=.55):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    shader = m.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metal
    shader.inputs['Roughness'].default_value = rough
    m.use_backface_culling = True
    return m


support = material('Printed_support', (.73, .72, .66), .02, .7)
carrier = material('Copper_carrier', (.66, .37, .20), .12, .48)
metal = material('Brushed_aluminium', (.50, .54, .55), .78, .3)
steel = material('Fastener_steel', (.32, .36, .37), .8, .26)
lamination = material('Motor_laminations', (.085, .102, .105), .5, .43)
black = material('Black_anodised', (.045, .057, .059), .4, .42)
pcb = material('Green_solder_mask', (.026, .18, .112), .12, .6)
driver_pcb = material('Driver_solder_mask', (.035, .13, .15), .1, .6)
plastic = material('Connector_plastic', (.07, .075, .07), .01, .65)
ceramic = material('Ceramic_component', (.25, .23, .15), .03, .7)
gold = material('Gold_contacts', (.68, .45, .17), .75, .27)
lens = material('Lens_optical_coating', (.025, .11, .14), .48, .16)
paper = material('Reference_paper', (.88, .875, .84), 0, .8)


def empty(name, parent=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    return obj


def cube(name, center, size, mat, parent=None, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Small_edge_radius', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new('Weighted_normals', 'WEIGHTED_NORMAL')
    obj.parent = parent
    return obj


def cylinder(name, center, radius, depth, mat, parent=None, axis='Z', vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=center)
    obj = bpy.context.object
    obj.name = name
    if axis == 'X':
        obj.rotation_euler[1] = math.pi / 2
    if axis == 'Y':
        obj.rotation_euler[0] = math.pi / 2
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def select_tree(root):
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for obj in root.children_recursive:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root


def export(root, filename):
    select_tree(root)
    bpy.ops.export_scene.gltf(filepath=str(OUT / filename), export_format='GLB', use_selection=True,
                              export_apply=True, export_yup=True, export_extras=True,
                              export_animations=False, export_materials='EXPORT')


gimbal = empty('Gimbal')
base = empty('Base', gimbal)
yaw_body = empty('YawMotor', gimbal)
pan = empty('PanPivot', gimbal)
yaw_rotor = empty('YawRotor', pan)
upper = empty('UpperStructure', pan)
tilt_body = empty('TiltMotor', pan)
tilt = empty('TiltPivot', pan, (0, 0, .126))
tilt_rotor = empty('TiltRotor', tilt)
tilt_rotor['lessonPart'] = 'tilt'
camera = empty('CameraAssembly', tilt)
groups = {'base': base, 'yaw': yaw_body, 'upper': upper, 'tilt': tilt_body, 'camera': camera}
for key, group in groups.items():
    group['lessonPart'] = key
pan['axis'] = 'vertical pan, degrees'
tilt['axis'] = 'tilt at 126 mm, positive angle raises optical axis'

for part in data['parts']:
    name, category = part['name'], part['category']
    if name == 'base':
        parent, mat = base, support
    elif name == 'upper':
        parent, mat = upper, support
    elif name == 'yaw-shaft':
        parent, mat = yaw_rotor, steel
    elif name == 'tilt-shaft':
        parent, mat = tilt_rotor, steel
    elif name.startswith(('yaw-', 'm3x10')):
        parent, mat = yaw_body, lamination if 'stack' in name else steel if name.startswith('m3') else metal
    elif name.startswith(('tilt-motor', 'tilt-plug', 'm3x6')):
        parent, mat = tilt_body, lamination if 'stack' in name else steel if name.startswith('m3') else metal
    else:
        parent = camera
        mat = carrier if name == 'camera-carrier' else steel
        if name == 'camera-pcb': mat = pcb
        elif category == 'camera': mat = plastic if 'csi-' in name else black
        elif category == 'glass': mat = lens
    offset = .126 if parent in [camera, tilt_rotor] else 0
    vertices = [(v[0] / 1000, v[1] / 1000, v[2] / 1000 - offset) for v in part['vertices']]
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], part['faces'])
    mesh.update()
    mesh.use_auto_smooth = True
    mesh.auto_smooth_angle = .7
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(mat)
    obj['source'] = 'CAD mesh, unchanged topology'


def driver_cap(parent, axis):
    # A labelled illustrative control envelope, not a mechanical claim about a vendor SKU.
    if axis == 'X':
        cube('Tilt_driver_pcb', (.0945, 0, .126), (.0016, .038, .038), driver_pcb, parent, .0004)
        cube('Tilt_driver_controller', (.0965, 0, .126), (.0024, .012, .012), black, parent, .0004)
        for i in range(5):
            cube(f'Tilt_driver_component_{i}', (.096, -.013 + i * .006, .139), (.0014, .003, .002), ceramic, parent, .0002)
        cube('Tilt_driver_socket', (.096, 0, .146), (.004, .013, .004), plastic, parent, .0005)
        for y in [-.015, .015]:
            for z in [.111, .141]:
                cylinder(f'Tilt_driver_screw_{y}_{z}', (.096, y, z), .0015, .001, steel, parent, 'X')
    else:
        cube('Pan_driver_pcb', (0, 0, .0115), (.038, .038, .0016), driver_pcb, parent, .0004)
        cube('Pan_driver_controller', (0, 0, .0095), (.012, .012, .002), black, parent, .0004)
        cube('Pan_driver_socket', (0, -.022, .012), (.013, .006, .006), plastic, parent, .0005)
        for x in [-.015, .015]:
            for y in [-.015, .015]:
                cylinder(f'Pan_driver_screw_{x}_{y}', (x, y, .010), .0015, .001, steel, parent)


driver_cap(yaw_body, 'Z')
driver_cap(tilt_body, 'X')
empty('anchor_pan_uart', yaw_body, (0, -.025, .012))
empty('anchor_pan_power', yaw_body, (.008, -.025, .012))
empty('anchor_tilt_uart', tilt_body, (.096, 0, .147))
empty('anchor_tilt_power', tilt_body, (.096, -.006, .140))
empty('anchor_camera_csi', camera, (0, .024, -.0175))
empty('anchor_camera_optical', camera, (0, -.0278, 0))
gimbal['source_cad_parts'] = len(data['parts'])
gimbal['driver_geometry'] = 'Illustrative control cap; SKU and physical fit unverified'
export(gimbal, 'gimbal.glb')

nano = empty('NanoBoard')
nano['lessonPart'] = 'nano'
nano['reference_envelope'] = '100x80 mm carrier; connector layout and heatsink illustrative'
cube('Nano_carrier_PCB', (0, 0, .003), (.100, .080, .0016), pcb, nano, .0007)
for x in [-.044, .044]:
    for y in [-.034, .034]:
        cylinder(f'Nano_mount_{x}_{y}', (x, y, .001), .0026, .002, steel, nano)
        cylinder(f'Nano_hole_ring_{x}_{y}', (x, y, .004), .0024, .0003, gold, nano)
cube('Nano_compute_module', (-.012, .002, .007), (.067, .046, .003), pcb, nano, .0007)
cube('Nano_heatsink_base', (-.014, .003, .011), (.043, .043, .005), black, nano, .0008)
for i in range(13):
    cube(f'Nano_heatsink_fin_{i:02}', (-.0335 + i * .00325, .003, .022), (.0013, .041, .018), black, nano, .00025)
for x in [-.033, .005]:
    for y in [-.016, .022]:
        cylinder(f'Nano_heatsink_screw_{x}_{y}', (x, y, .033), .0017, .001, steel, nano)
for j, y in enumerate([-.021, .006]):
    cube(f'Nano_USB_stack_{j}', (.039, y, .013), (.017, .016, .018), metal, nano, .0007)
    for z in [.009, .017]:
        cube(f'Nano_USB_insert_{j}_{z}', (.048, y, z), (.0008, .012, .005), black, nano, .0002)
        cube(f'Nano_USB_tongue_{j}_{z}', (.0486, y, z), (.0002, .010, .0018), driver_pcb, nano)
cube('Nano_Ethernet', (.036, .029, .012), (.022, .016, .017), metal, nano, .0007)
cube('Nano_Ethernet_socket', (.0475, .029, .012), (.001, .012, .010), black, nano, .0004)
cube('Nano_HDMI_shell', (.005, -.034, .007), (.016, .012, .007), metal, nano, .0007)
cube('Nano_HDMI_insert', (.005, -.0405, .007), (.012, .0008, .004), black, nano, .0003)
cube('Nano_CSI_socket', (-.022, -.033, .0055), (.024, .005, .003), paper, nano, .0003)
cube('Nano_CSI_latch', (-.022, -.036, .0065), (.024, .0015, .002), black, nano, .0002)
cube('Nano_GPIO_header', (-.014, .033, .0065), (.051, .006, .0045), black, nano, .0004)
for i in range(20):
    for row in [-1, 1]:
        cube(f'Nano_GPIO_pin_{i:02}_{row}', (-.038 + i * .00254, .033 + row * .00127, .010), (.00065, .00065, .003), gold, nano)
for i in range(9):
    cube(f'Nano_component_{i}', (-.043 + (i % 3) * .009, -.025 + (i // 3) * .005, .0045), (.004, .0023, .0012), ceramic, nano, .00015)
cylinder('Nano_barrel_power', (-.042, .024, .008), .0038, .013, plastic, nano, 'Y')
empty('anchor_nano_uart', nano, (-.014, .035, .010))
empty('anchor_nano_uart_tilt', nano, (-.006, .035, .010))
empty('anchor_nano_csi', nano, (-.022, -.036, .006))
export(nano, 'nano.glb')

supply = empty('MotorSupply')
supply['lessonPart'] = 'power'
cube('Supply_body', (0, 0, .009), (.039, .031, .018), plastic, supply, .002)
cube('Supply_label', (0, 0, .0182), (.026, .020, .0003), paper, supply, .0007)
for i in range(4):
    cube(f'Supply_label_line_{i}', (0, -.005 + i * .0032, .0185), (.018 - i * .002, .0007, .0002), black, supply)
cylinder('Supply_output', (.021, 0, .008), .0028, .008, plastic, supply, 'X')
empty('anchor_supply', supply, (.025, 0, .008))
empty('anchor_supply_tilt', supply, (.025, .006, .008))
export(supply, 'supply.glb')

catalog = {
    'units': 'metres', 'cad_part_count': len(data['parts']),
    'cad_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'facing': 'Blender -Y, browser +Z', 'tilt_height': .126,
    'gimbal_groups': ['Base', 'YawMotor', 'YawRotor', 'UpperStructure', 'TiltMotor', 'PanPivot', 'TiltPivot', 'TiltRotor', 'CameraAssembly'],
    'anchors_browser_local': {
        'yaw.uart': [0, .012, .025], 'tilt.uart': [.096, .147, 0],
        'camera.csi': [0, .1085, -.024], 'camera.optical': [0, .126, .0278],
        'nano.uart': [-.014, .010, -.035], 'nano.csi': [-.022, .006, .036],
        'power.output': [.025, .008, 0]
    },
    'assumptions': ['Exact integrated motor SKU unknown', 'Nano carrier revision and connector coordinates illustrative',
                    'Driver caps and cable routing are not fit-validated', 'Lens envelope reused; FOV is a teaching parameter'],
    'assets': {}
}
for root, file in [(gimbal, 'gimbal.glb'), (nano, 'nano.glb'), (supply, 'supply.glb')]:
    catalog['assets'][file] = {'bytes': (OUT / file).stat().st_size,
                             'nodes': [root.name] + [o.name for o in root.children_recursive]}
(OUT / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')

# Save the editable asset pack before adding preview-only stage objects.
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / 'assets.blend'))
nano.location = (-.15, .005, 0)
supply.location = (-.145, .105, 0)
cube('Preview_floor', (0, 0, -.004), (.70, .60, .006), paper, bevel=.002)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 12
scene.cycles.use_denoising = True
scene.render.resolution_x = 1100
scene.render.resolution_y = 780
scene.render.resolution_percentage = 100
scene.world = bpy.data.worlds.new('Studio_world')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.65, .65, .65, 1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .35
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'Medium High Contrast'
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
for name, pos, energy, size in [('Key', (-.3, -.4, .5), 4, .4), ('Fill', (.35, .1, .35), 2, .3)]:
    ld = bpy.data.lights.new(name, 'AREA')
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = pos
    lo.rotation_euler = (Vector((0, 0, .05)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    ld.energy, ld.size = energy, size
camera_data = bpy.data.cameras.new('Preview_camera')
camera_obj = bpy.data.objects.new('Preview_camera', camera_data)
bpy.context.collection.objects.link(camera_obj)
scene.camera = camera_obj
camera_data.type = 'ORTHO'
for name, pos, target, scale in [
    ('assembly-three-quarter', (.31, -.43, .30), (-.045, 0, .07), .36),
    ('assembly-front', (0, -.55, .09), (-.04, 0, .08), .33),
    ('nano-detail', (-.03, -.18, .20), (-.15, .005, .016), .14)
]:
    if name == 'nano-detail':
        for root in [gimbal, supply]:
            for obj in root.children_recursive:
                obj.hide_render = True
    camera_obj.location = pos
    camera_obj.rotation_euler = (Vector(target) - camera_obj.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.ortho_scale = scale
    scene.render.filepath = str(PREVIEWS / (name + '.png'))
    bpy.ops.render.render(write_still=True)
print('ASSETS_READY ' + json.dumps({k: v['bytes'] for k, v in catalog['assets'].items()}))
