import bpy
from ..properties import NAMING_FORMATS   # ← 改为相对导入（最可靠）

class TOMMY_OT_NamingQuery(bpy.types.Operator):
    """查询产品命名格式"""
    bl_idname = "tommy.naming_query"
    bl_label = "查询"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        p_type = context.scene.tommy_naming_product_type
        example = NAMING_FORMATS.get(p_type, "未定义的命名格式")

        self.report({'INFO'}, f"产品类型: {p_type}   {example}")
        return {'FINISHED'}