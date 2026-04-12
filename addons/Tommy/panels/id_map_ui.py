import bpy
from ....common.types.framework import reg_order


@reg_order(50)
class VIEW3D_PT_IDMapTools(bpy.types.Panel):
    """ID Map 综合工具面板"""
    bl_label = "ID Map"
    bl_idname = "VIEW3D_PT_id_map_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MDB'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- 快速操作 ---
        col = layout.column(align=True)
        col.label(text="快速操作", icon='MODIFIER')

        has_hidden_renderable = any(
            obj.hide_get() and not obj.hide_render
            for obj in context.view_layer.objects
        )

        row = col.row(align=True)
        split = row.split(factor=0.7, align=True)
        split.operator("object.clear_visible_materials", text="清除可见材质", icon='TRASH')
        split.operator("object.show_hidden_renderable", text="", icon='GHOST_ENABLED', depress=has_hidden_renderable)

        col.operator("object.create_id_material", text="应用随机 ID 材质 (B&W)", icon='NODE_SEL')

        layout.separator()

        # --- 手动 ID 控制（自动加载版）---
        col = layout.column(align=True)
        col.label(text="指定颜色", icon='COLOR')

        # 自动加载提示
        # col.label(text="提示：选中带 ID_Color_xx 材质的物体时自动加载", icon='INFO')

        col.separator(factor=1.0)

        # 大色轮 + 色块
        col.template_color_picker(scene, "tommy_id_color", value_slider=True)
        col.separator(factor=1.0)

        col = layout.column(align=True)
        col.prop(scene, "tommy_id_color", text="")

        # ====================== 紧凑三栏UI（按钮 + ID名称输入栏） ======================

        row = col.row(align=True)
        split = row.split(factor=0.15, align=True)  # ← 精确控制比例
        split.operator("wm.call_menu", text="", icon='MATERIAL').name = "OBJECT_MT_id_color_menu"
        split.prop(scene, "tommy_id_name", text="")

        row = col.row(align=True)
        row.operator("object.create_new_id_material", text="新建", icon='ADD')
        row.operator("object.link_active_id_material", text="链接", icon='LINKED')
        row.operator("object.select_linked_material_custom", text="选择相连", icon='LINKED')
        # # 错误提示
        # allowed_types = {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}
        # if context.active_object and context.active_object.type not in allowed_types:
        #     layout.label(text="请选中支持材质的几何体", icon='ERROR')