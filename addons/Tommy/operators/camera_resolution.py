# ====================== addons/Tommy/operators/camera_resolution.py （完整代码） ======================
import bpy
from bpy.props import StringProperty, IntVectorProperty, BoolProperty
from ..properties import sync_marker_list_to_frame


# ====================== 原始分辨率即时更新回调 ======================
def update_original_resolution(self, context):
    """用户在面板修改原始分辨率时，立即同步到渲染设置（仅当前帧无绑定摄像机时生效）"""
    scene = context.scene

    # 如果当前帧已经绑定了摄像机且使用了自定义分辨率，就不覆盖（保持自定义优先）
    if get_camera_at_frame(scene, scene.frame_current):
        return

    # 立即同步到 Render Settings（和官方属性面板体验完全一致）
    scene.render.resolution_x = scene.tommy_original_resolution[0]
    scene.render.resolution_y = scene.tommy_original_resolution[1]


# ====================== 工具函数 ======================
def get_camera_at_frame(scene, frame):
    for marker in scene.timeline_markers:
        if marker.frame == frame and marker.camera:
            return marker.camera
    return None

def get_camera_data_name(camera_obj):
    return camera_obj.data.name if camera_obj and camera_obj.data else None

def get_camera_setting(scene, camera_data_name):
    if not hasattr(scene, 'tommy_camera_resolution_settings'):
        return None
    for s in scene.tommy_camera_resolution_settings:
        if s.camera_data_name == camera_data_name:
            return s
    return None

def get_camera_first_frame(scene, camera_data_name):
    first = float('inf')
    for m in scene.timeline_markers:
        if m.camera and get_camera_data_name(m.camera) == camera_data_name:
            first = min(first, m.frame)
    return first if first != float('inf') else float('inf')

def get_sorted_camera_settings(scene):
    if not hasattr(scene, 'tommy_camera_resolution_settings'):
        return []
    items = [(s, get_camera_first_frame(scene, s.camera_data_name)) for s in scene.tommy_camera_resolution_settings]
    items.sort(key=lambda x: x[1])
    return [x[0] for x in items]

def get_camera_object_by_data_name(camera_data_name):
    for obj in bpy.data.objects:
        if obj.type == 'CAMERA' and obj.data and obj.data.name == camera_data_name:
            return obj
    return None

def update_resolution_for_frame(scene, frame):
    cam_obj = get_camera_at_frame(scene, frame)
    if cam_obj:
        data_name = get_camera_data_name(cam_obj)
        setting = get_camera_setting(scene, data_name) if data_name else None
        if setting and setting.is_applied:
            scene.render.resolution_x = setting.applied_resolution[0]
            scene.render.resolution_y = setting.applied_resolution[1]
            return
    # 恢复原始分辨率
    scene.render.resolution_x = scene.tommy_original_resolution[0]
    scene.render.resolution_y = scene.tommy_original_resolution[1]

def update_camera_temp_resolution_on_frame_change(scene, frame):
    cam_obj = get_camera_at_frame(scene, frame)
    if cam_obj:
        data_name = get_camera_data_name(cam_obj)
        setting = get_camera_setting(scene, data_name) if data_name else None
        if setting:
            setting.temp_resolution = setting.applied_resolution[:] if setting.is_applied else scene.tommy_original_resolution[:]


# ====================== Operators ======================
class CAMRES_OT_add_camera_setting(bpy.types.Operator):
    bl_idname = "tommy.camres_add_camera_setting"
    bl_label = "添加自定义分辨率"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_camera_at_frame(context.scene, context.scene.frame_current)

    def execute(self, context):
        scene = context.scene
        camera_obj = get_camera_at_frame(scene, scene.frame_current)
        if not camera_obj:
            return {'CANCELLED'}
        camera_data_name = get_camera_data_name(camera_obj)
        if not camera_data_name:
            self.report({'ERROR'}, "无法获取摄像机数据块")
            return {'CANCELLED'}

        setting = get_camera_setting(scene, camera_data_name)
        if not setting:
            if not hasattr(scene, 'tommy_camera_resolution_settings'):
                self.report({'ERROR'}, "分辨率设置属性未初始化")
                return {'CANCELLED'}
            setting = scene.tommy_camera_resolution_settings.add()
            setting.camera_data_name = camera_data_name
            setting.temp_resolution = scene.tommy_original_resolution[:]
            setting.applied_resolution = scene.tommy_original_resolution[:]
            setting.is_applied = True

        if setting.is_applied:
            scene.render.resolution_x = setting.applied_resolution[0]
            scene.render.resolution_y = setting.applied_resolution[1]

        self.report({'INFO'}, f"已为摄像机 '{camera_obj.name}' 添加分辨率设置")
        return {'FINISHED'}

# 其他 operator 保持不变（添加 hasattr 检查到每个 execute 中类似以上）
class CAMRES_OT_remove_camera_setting(bpy.types.Operator):
    bl_idname = "tommy.camres_remove_camera_setting"
    bl_label = "移除摄像机设置"
    bl_options = {'REGISTER', 'UNDO'}

    camera_data_name: StringProperty(default="")

    def execute(self, context):
        scene = context.scene
        if not hasattr(scene, 'tommy_camera_resolution_settings'):
            self.report({'ERROR'}, "分辨率设置属性未初始化")
            return {'CANCELLED'}
        for i, s in enumerate(scene.tommy_camera_resolution_settings):
            if s.camera_data_name == self.camera_data_name:
                if get_camera_data_name(get_camera_at_frame(scene, scene.frame_current)) == self.camera_data_name:
                    scene.render.resolution_x = scene.tommy_original_resolution[0]
                    scene.render.resolution_y = scene.tommy_original_resolution[1]
                scene.tommy_camera_resolution_settings.remove(i)
                self.report({'INFO'}, f"已移除摄像机设置")
                break
        return {'FINISHED'}


class CAMRES_OT_apply_camera_resolution(bpy.types.Operator):
    bl_idname = "tommy.camres_apply_camera_resolution"
    bl_label = "应用分辨率"
    bl_options = {'REGISTER', 'UNDO'}

    camera_data_name: StringProperty(default="")

    def execute(self, context):
        scene = context.scene
        setting = get_camera_setting(scene, self.camera_data_name)
        if setting:
            setting.applied_resolution = setting.temp_resolution[:]
            setting.is_applied = True
            if get_camera_data_name(get_camera_at_frame(scene, scene.frame_current)) == self.camera_data_name:
                scene.render.resolution_x = setting.applied_resolution[0]
                scene.render.resolution_y = setting.applied_resolution[1]
            self.report({'INFO'}, f"已应用 {setting.applied_resolution[0]}×{setting.applied_resolution[1]}")
        return {'FINISHED'}

class CAMRES_OT_apply_to_selected(bpy.types.Operator):
    bl_idname = "tommy.camres_apply_to_selected"
    bl_label = "应用到所选摄像机"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len([o for o in context.selected_objects if o.type == 'CAMERA']) > 0

    def execute(self, context):
        scene = context.scene
        current_res = get_camera_at_frame(scene, scene.frame_current)
        res = (scene.render.resolution_x, scene.render.resolution_y) if current_res else scene.tommy_original_resolution[:]

        count = 0
        if not hasattr(scene, 'tommy_camera_resolution_settings'):
            self.report({'ERROR'}, "分辨率设置属性未初始化")
            return {'CANCELLED'}
        for obj in [o for o in context.selected_objects if o.type == 'CAMERA']:
            data_name = get_camera_data_name(obj)
            setting = get_camera_setting(scene, data_name)
            if not setting:
                setting = scene.tommy_camera_resolution_settings.add()
                setting.camera_data_name = data_name
            setting.temp_resolution = res
            setting.applied_resolution = res
            setting.is_applied = True
            count += 1

        self.report({'INFO'}, f"已应用到 {count} 个选中的摄像机")
        return {'FINISHED'}


# ====================== 帧变化处理器 ======================
@bpy.app.handlers.persistent
def sync_marker_list_to_frame(scene):
    current_frame = scene.frame_current
    found = False
    for i, marker in enumerate(scene.timeline_markers):
        if marker.frame == current_frame and marker.camera:
            if scene.tommy_active_marker_index != i:
                scene.tommy_active_marker_index = i
            found = True
            break

    # 如果當前幀沒有有效的標記，可以考慮將索引設為 -1 (取消高亮)
    if not found:
        scene.tommy_active_marker_index = -1

@bpy.app.handlers.persistent
def frame_change_handler(scene):
    # 這裡確保 update_resolution_for_frame 邏輯正常
    from .camera_resolution import update_resolution_for_frame
    update_resolution_for_frame(scene, scene.frame_current)

    # --- 關鍵：取消下面的註釋 ---
    from ..properties import sync_marker_list_to_frame
    sync_marker_list_to_frame(scene)