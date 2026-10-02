import bpy, glob
s = bpy.context.scene
s.render.engine = 'CYCLES'; s.cycles.samples = 4; s.cycles.use_denoising = False
s.render.resolution_x, s.render.resolution_y = 384, 256
w = s.world or bpy.data.worlds.new('w'); s.world = w; w.use_nodes = True
env = w.node_tree.nodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(sorted(glob.glob('/usr/share/blender/datafiles/studiolights/world/*.exr'))[0])
w.node_tree.links.new(env.outputs['Color'], w.node_tree.nodes['Background'].inputs['Color'])
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); s.collection.objects.link(cam); s.camera = cam
cam.rotation_euler = (1.5, 0, 0)
s.render.filepath = '/workspace/out/final.png'
bpy.ops.render.render(write_still=True)
