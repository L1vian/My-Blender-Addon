from .addons.Tommy import register as addon_register, unregister as addon_unregister

bl_info = {
    "name": "Tommy's Blender Tools_2.0.2 Beta",
    "author": 'Tommy',
    "version": (2, 0, 2),
    "blender": (4, 1, 0),
    "description": 'This is a Blender Add-on developed by Tommy for the Render Team to streamline the workflow.',
    "category": 'render'
}

def register():
    addon_register()

def unregister():
    addon_unregister()

    