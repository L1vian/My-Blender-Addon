import bpy

from .... common.types.framework import reg_order
# ====================== 摄像机分辨率管理器所需工具函数 ======================
from ..operators.camera_resolution import (
    get_camera_at_frame,
    get_camera_data_name,
    get_camera_setting,
    get_sorted_camera_settings,
    get_camera_object_by_data_name
)

#reg_order()  装饰器，控制类的先后加载顺序，影响panel的默认排列顺序

@reg_order(0)
class VIEW3D_PT_MaterialTools(bpy.types.Panel):
    bl_label = "Tools bag"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "MDB"

    def draw(self, context):
        layout = self.layout

        # 材质管理
        layout.label(text="material manager：")
        row = layout.row()
        row.operator("material.copy_all_materials", icon='DUPLICATE')
        row.operator("material.clear_slots", icon='TRASH')

        layout.separator()

        # 对象管理
        layout.label(text="object manager：")
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.operator("object.set_origin_to_extreme", text="设置原点", icon='SNAP_VERTEX')
        grid.operator("object.pack_to_empty", icon='EMPTY_AXIS')
        grid.operator("object.go_to_floor", icon='SORT_DESC')

        layout.separator()

        # 资源清理
        layout.label(text="source manager：")
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.operator("object.clean_unused_materials", icon='MATERIAL_DATA')
        grid.operator("object.fix_missing_paths", text="修复丢失路径/打包报错", icon='FILE_REFRESH')

        layout.separator()

        # 摄像机工具（已删除“摄像机名称”功能）
        layout.label(text="摄像机工具：", icon='CAMERA_DATA')
        layout.operator("camera.set_active_camera", icon='RESTRICT_SELECT_OFF', text="选中摄像机")
        layout.prop(context.scene, "camera_display_size", text="显示尺寸")

@reg_order(1)
# ====================== 独立 Panel：摄像机分辨率管理器 ======================
class VIEW3D_PT_CameraResolution(bpy.types.Panel):
    bl_label = "摄像机分辨率管理器"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "MDB"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 原始分辨率
        box = layout.box()
        box.label(text="原始分辨率:", icon='RENDER_RESULT')
        row = box.row(align=True)
        row.prop(scene, "tommy_original_resolution", index=0, text="宽")
        row.prop(scene, "tommy_original_resolution", index=1, text="高")

        # 当前帧信息
        current_frame = scene.frame_current
        camera_obj = get_camera_at_frame(scene, current_frame)

        box = layout.box()
        box.label(text=f"当前帧: {current_frame}", icon='TIME')

        if camera_obj:
            data_name = get_camera_data_name(camera_obj)
            setting = get_camera_setting(scene, data_name) if data_name else None

            box.label(text=f"摄像机: {camera_obj.name}", icon='CAMERA_DATA')

            if setting:
                row = box.row(align=True)
                row.prop(setting, "temp_resolution", index=0, text="宽")
                row.prop(setting, "temp_resolution", index=1, text="高")

                row = box.row(align=True)
                op = row.operator("tommy.camres_apply_camera_resolution", text="应用", icon='CHECKMARK')
                op.camera_data_name = data_name
                op = row.operator("tommy.camres_remove_camera_setting", text="移除", icon='X')
                op.camera_data_name = data_name
            else:
                op = box.operator("tommy.camres_add_camera_setting", text="添加自定义分辨率", icon='ADD')
        else:
            box.label(text="未绑定摄像机，使用原始分辨率", icon='INFO')

        # 批量应用
        layout.operator("tommy.camres_apply_to_selected", text="应用到所选摄像机", icon='COPY_ID')

        # 已设置列表
        if hasattr(scene, "tommy_camera_resolution_settings") and len(scene.tommy_camera_resolution_settings) > 0:
            box = layout.box()
            box.label(text="已设置:", icon='BOOKMARKS')
            for setting in get_sorted_camera_settings(scene):
                cam_obj = get_camera_object_by_data_name(setting.camera_data_name)
                name = cam_obj.name if cam_obj else setting.camera_data_name
                if setting.is_applied:
                    box.label(text=f"{name}: {setting.applied_resolution[0]}×{setting.applied_resolution[1]}",
                              icon='CHECKMARK')
                else:
                    box.label(text=f"{name}: 未应用", icon='X')


class NODE_PT_MaterialTools(bpy.types.Panel):
    bl_label = "Tools bag"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "MDB"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ShaderNodeTree'

    def draw(self, context):
        layout = self.layout
        layout.separator()
        layout.label(text="资源清理：")
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.operator("object.clean_unused_materials", icon='MATERIAL_DATA')
        grid.operator("object.clean_unused_textures", icon='TEXTURE')
        layout.operator("material.set_non_color")