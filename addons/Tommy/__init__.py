import bpy
from bpy.app.handlers import persistent

bl_info = {
    "name": "Tommy's Blender Tools_2.0.2 Beta",
    "author": "Tommy",
    "version": (2, 0, 2),
    "blender": (4, 1, 0),
    "description": "This is a Blender Add-on developed by Tommy for the Render Team to streamline the workflow.",
    "category": "render",
}

from .config import __addon_name__
from .i18n.dictionary import dictionary
from ...common.class_loader import auto_load
from ...common.class_loader.auto_load import add_properties, remove_properties
from ...common.i18n.dictionary import common_dictionary
from ...common.i18n.i18n import load_dictionary

from .panels.locate_in_properties_panels import sync_ui_list_handler
from .panels.locate_in_properties_panels import auto_sort_markers_handler

from .properties import CameraResolutionSetting
from .operators.camera_resolution import (
    frame_change_handler,
    update_original_resolution
)
from .operators.id_map import auto_load_id_from_active


# --- 1. 初始化逻辑 ---
@persistent
def ensure_addon_state_on_load(scene=None):
    try:
        if not bpy.data.use_autopack:
            bpy.data.use_autopack = True

        current_scene = bpy.context.scene
        if hasattr(current_scene, "tommy_original_resolution"):
            res = current_scene.tommy_original_resolution
            current_scene.render.resolution_x = res[0]
            current_scene.render.resolution_y = res[1]

    except Exception as e:
        print(f"Tommy Tools Init Error: {e}")


def run_init_timer():
    ensure_addon_state_on_load()
    return None


# --- 2. 场景属性 ---
# ▼ 新增：DPI 属性的 update 回调（用于驱动实时换算显示）
def _update_dpi_calc(self, context):
    """属性变化时触发重绘，使物理尺寸实时刷新"""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PROPERTIES':
                area.tag_redraw()


_addon_properties = {
    bpy.types.Scene: {
        # 保持原有属性不变
        "tommy_camera_resolution_settings": bpy.props.CollectionProperty(type=CameraResolutionSetting),
        "tommy_original_resolution": bpy.props.IntVectorProperty(
            name="原始分辨率",
            size=2,
            default=(5000, 3750),
            update=update_original_resolution,
        ),
    },
}


# ▼ 新增：插件偏好设置（AddonPreferences），用于 Pillow 安装管理
class TommyAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __addon_name__

    def draw(self, context):
        layout = self.layout

        # 检测 Pillow 状态
        try:
            from PIL import Image
            pillow_installed = True
            import PIL
            pillow_version = PIL.__version__
        except ImportError:
            pillow_installed = False
            pillow_version = ""

        box = layout.box()
        row = box.row()
        row.label(text="依赖库状态", icon='PREFERENCES')

        row = box.row()
        if pillow_installed:
            row.label(text=f"✅  Pillow {pillow_version}  已安装", icon='CHECKMARK')
            row.operator("tommy.uninstall_pillow", text="卸载 Pillow", icon='TRASH')
        else:
            row.label(text="⚠️  Pillow 未安装（DPI 元数据写入功能不可用）", icon='ERROR')
            row.operator("tommy.install_pillow", text="安装 Pillow", icon='IMPORT')


def register():
    # A. 注册 AddonPreferences（需要在 auto_load 之前手动注册）
    bpy.utils.register_class(TommyAddonPreferences)

    # B. 运行框架自动加载
    auto_load.init()
    auto_load.register()

    # C. 注册附加属性
    add_properties(_addon_properties)

    # D. 国际化翻译
    load_dictionary(dictionary)
    try:
        bpy.app.translations.register(__addon_name__, common_dictionary)
    except Exception:
        try:
            bpy.app.translations.unregister(__addon_name__)
            bpy.app.translations.register(__addon_name__, common_dictionary)
        except:
            pass

    # E. 注册处理器
    handlers = bpy.app.handlers.frame_change_post
    if frame_change_handler not in handlers:
        handlers.append(frame_change_handler)
    if sync_ui_list_handler not in handlers:
        handlers.append(sync_ui_list_handler)
    if ensure_addon_state_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(ensure_addon_state_on_load)

        # 注册依赖图处理器
    handlers = bpy.app.handlers.depsgraph_update_post
    if auto_sort_markers_handler not in handlers:
        handlers.append(auto_sort_markers_handler)

    # F. 计时器
    bpy.app.timers.register(run_init_timer, first_interval=0.1)

    if auto_load_id_from_active not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(auto_load_id_from_active)

    print("{} addon is installed.".format(__addon_name__))


def unregister():
    # 移除处理器
    if ensure_addon_state_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(ensure_addon_state_on_load)
    if frame_change_handler in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(frame_change_handler)
    if sync_ui_list_handler in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(sync_ui_list_handler)

    if auto_load_id_from_active in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(auto_load_id_from_active)

        # 卸载依赖图处理器
    if auto_sort_markers_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(auto_sort_markers_handler)

    # 注销翻译
    try:
        bpy.app.translations.unregister(__addon_name__)
    except:
        pass

    # 注销属性与类
    remove_properties(_addon_properties)
    auto_load.unregister()

    # ▼ 新增：手动注销 AddonPreferences
    bpy.utils.unregister_class(TommyAddonPreferences)

    print("{} addon is uninstalled.".format(__addon_name__))
