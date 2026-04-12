import bpy
import os
import bmesh
from mathutils import Vector
from bpy.props import EnumProperty

# ==================== 公共函数 & 更新函数 ====================
def get_material_textures(material):
    textures = set()
    if material.node_tree:
        for node in material.node_tree.nodes:
            if isinstance(node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and node.image:
                textures.add(node.image)
            elif isinstance(node, bpy.types.ShaderNodeGroup) and node.node_tree:
                for sub_node in node.node_tree.nodes:
                    if isinstance(sub_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and sub_node.image:
                        textures.add(sub_node.image)
    return textures

# ==================== 相机工具 ====================
class OBJECT_OT_SetCameraDisplaySize(bpy.types.Operator):
    bl_idname = "object.set_camera_display_size"
    bl_label = "Set Camera Display Size"
    bl_options = {'REGISTER', 'UNDO'}

    display_size: bpy.props.FloatProperty(name="Display Size", default=1.0, min=0.01)

    def execute(self, context):
        display_size = context.scene.camera_display_size
        for cam in [obj for obj in context.scene.objects if obj.type == 'CAMERA']:
            cam.data.display_size = display_size
        self.report({'INFO'}, f"已设置所有摄像机的显示尺寸为 {display_size}")
        return {'FINISHED'}

class CAMERA_OT_SetActiveCamera(bpy.types.Operator):
    bl_idname = "camera.set_active_camera"
    bl_label = "选中摄像机"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'CAMERA' for obj in context.scene.objects)

    def execute(self, context):
        cam = None
        if hasattr(context.space_data, 'camera') and context.space_data.camera:
            cam = context.space_data.camera
        if not cam:
            selected = [o for o in context.selected_objects if o.type == 'CAMERA']
            if selected: cam = selected[0]
        if not cam:
            all_cams = [o for o in context.scene.objects if o.type == 'CAMERA']
            if all_cams: cam = all_cams[0]
        if cam:
            context.view_layer.objects.active = cam
            bpy.ops.object.select_all(action='DESELECT')
            cam.select_set(True)
            self.report({'INFO'}, f"已选中摄像机: {cam.name}")
            return {'FINISHED'}
        self.report({'ERROR'}, "场景中没有摄像机")
        return {'CANCELLED'}

# ==================== 材质工具 ====================
class MATERIAL_OT_CopyAllMaterials(bpy.types.Operator):
    bl_idname = "material.copy_all_materials"
    bl_label = "复制所有材质"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        active = context.active_object
        if not active or active.type != 'MESH':
            self.report({'ERROR'}, "需要选择网格对象作为活动对象")
            return {'CANCELLED'}
        mats = [slot.material for slot in active.material_slots]
        if not mats:
            self.report({'ERROR'}, "活动对象没有材质")
            return {'CANCELLED'}
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH' and obj != active:
                obj.data.materials.clear()
                for m in mats:
                    obj.data.materials.append(m)
                count += 1
        self.report({'INFO'}, f"已复制材质到 {count} 个物体")
        return {'FINISHED'}

class MATERIAL_OT_ClearMaterialSlots(bpy.types.Operator):
    bl_idname = "material.clear_slots"
    bl_label = "清空材质槽"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                obj.data.materials.clear()
                count += 1
        self.report({'INFO'}, f"已清除 {count} 个物体的材质槽")
        return {'FINISHED'}

class MATERIAL_OT_SetNonColor(bpy.types.Operator):
    bl_idname = "material.set_non_color"
    bl_label = "Non-Color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for node in context.selected_nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                node.image.colorspace_settings.name = 'Non-Color'
                count += 1
        self.report({'INFO'}, f"已更新 {count} 个贴图设置")
        return {'FINISHED'}


##=========================分割线===============================
class OBJECT_OT_SetOriginToExtreme(bpy.types.Operator):
    """将选中物体的原点按变换坐标系移动（全局/局部）"""
    bl_idname = "object.set_origin_to_extreme"
    bl_label = "设置原点到边界"
    bl_options = {'REGISTER', 'UNDO'}

    # --- 算子属性（支持在左下角面板实时修改） ---
    axis: EnumProperty(
        name="轴向",
        items=[('X', "X 轴", ""), ('Y', "Y 轴", ""), ('Z', "Z 轴", "")],
        default='Z'
    )

    side: EnumProperty(
        name="位置",
        items=[('MIN', "最小值", ""), ('MAX', "最大值", "")],
        default='MIN'
    )

    orientation: EnumProperty(
        name="变换坐标系",
        items=[
            ('GLOBAL', "全局 (Global)", "基于世界坐标系计算"),
            ('LOCAL', "局部 (Local)", "基于物体自身坐标系计算"),
        ],
        default='LOCAL'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def invoke(self, context, event):
        """点击按钮时的初始触发：捕获当前环境状态"""
        # 自动获取当前的坐标系作为初始值
        current_orient = context.scene.transform_orientation_slots[0].type
        if current_orient in {'GLOBAL', 'LOCAL'}:
            self.orientation = current_orient
        else:
            self.orientation = 'LOCAL'  # 其他模式（如 Normal/Gimbal）默认转为 Local

        return self.execute(context)

    def execute(self, context):
        # 注意：这里需要先强制物体回到物体模式，因为我们将操作顶点数据
        if context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        # 1. 设置质心（此操作自带 UNDO 栈，会重置之前的移动）
        bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME', center='MEDIAN')

        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[self.axis]
        orient_type = self.orientation  # 使用属性而非环境参数

        for obj in selected_objects:
            # 2. 计算极值
            # 无论在什么模式下，我们直接从 obj.data.vertices 读取（这是最快的）
            if orient_type == 'GLOBAL':
                # 世界空间坐标 = matrix_world @ local_co
                extremes = [(obj.matrix_world @ v.co)[axis_idx] for v in obj.data.vertices]
            else:
                # 局部空间坐标
                extremes = [v.co[axis_idx] for v in obj.data.vertices]

            if not extremes: continue

            target_val = min(extremes) if self.side == 'MIN' else max(extremes)

            # 3. 计算偏移并应用
            mw = obj.matrix_world
            offset_world = Vector((0, 0, 0))
            offset_local = Vector((0, 0, 0))

            if orient_type == 'GLOBAL':
                current_origin_val = mw.translation[axis_idx]
                diff = target_val - current_origin_val
                offset_world[axis_idx] = diff
                offset_local = mw.inverted().to_3x3() @ offset_world
            else:
                diff = target_val  # Local 模式下原点是 0
                offset_local[axis_idx] = diff
                offset_world = mw.to_3x3() @ offset_local

            # 执行移动
            obj.matrix_world.translation += offset_world
            for v in obj.data.vertices:
                v.co -= offset_local

            obj.data.update()

        return {'FINISHED'}

    def draw(self, context):
        """定义左下角‘调整上一步操作’面板的 UI"""
        layout = self.layout
        col = layout.column(align=True)

        # 坐标系切换（这就是你想要的功能）
        col.prop(self, "orientation", expand=True)
        col.separator()

        # 轴向和位置
        row = col.row(align=True)
        row.prop(self, "axis", expand=True)

        col.separator()

        row = col.row(align=True)
        row.prop(self, "side", expand=True)

class OBJECT_OT_PackToEmpty(bpy.types.Operator):
    bl_idname = "object.pack_to_empty"
    bl_label = "pack2empty"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        valid_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT'}]
        if not valid_objs:
            self.report({'ERROR'}, "没有有效的物体")
            return {'CANCELLED'}
        all_global_verts = []
        matrix_list = [obj.matrix_world for obj in valid_objs]
        for obj, matrix in zip(valid_objs, matrix_list):
            if obj.type == 'MESH':
                all_global_verts.extend(matrix @ v.co for v in obj.data.vertices)
            elif obj.type in {'CURVE', 'SURFACE'}:
                for spline in obj.data.splines:
                    all_global_verts.extend(matrix @ p.co for p in spline.bezier_points)
                    all_global_verts.extend(matrix @ p.co for p in spline.points)
            elif obj.type == 'FONT':
                all_global_verts.extend(matrix @ Vector((v.x, v.y, 0)) for v in obj.data.vertices)
        if not all_global_verts:
            self.report({'ERROR'}, "没有顶点数据")
            return {'CANCELLED'}
        centroid = sum(all_global_verts, Vector()) / len(all_global_verts)
        min_z = min(v.z for v in all_global_verts) if all_global_verts else 0
        empty = bpy.data.objects.new("_con", None)
        context.collection.objects.link(empty)
        empty.location = centroid
        if all_global_verts:
            empty.location.z = min_z
        bpy.context.view_layer.objects.active = empty
        bpy.ops.object.mode_set(mode='OBJECT')
        for obj in valid_objs:
            obj.select_set(True)
        empty.select_set(True)
        context.view_layer.objects.active = empty
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
        bpy.ops.object.select_all(action='DESELECT')
        empty.select_set(True)
        context.view_layer.objects.active = empty
        self.report({'INFO'}, "PACK UP SUCCEEDED")
        return {'FINISHED'}

# 把物体垂直放置到Z轴为0的地方
class OBJECT_OT_GoToFloor(bpy.types.Operator):
    """ go2floor """
    bl_idname = "object.go_to_floor"
    bl_label = "go2floor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        processed_objects = 0
        for obj in context.selected_objects:
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'EMPTY'}:
                continue
            global_verts = []
            matrix = obj.matrix_world
            if obj.type == 'MESH':
                global_verts = [matrix @ v.co for v in obj.data.vertices]
            elif obj.type in {'CURVE', 'SURFACE'}:
                for spline in obj.data.splines:
                    global_verts.extend(matrix @ p.co for p in spline.bezier_points)
                    global_verts.extend(matrix @ p.co for p in spline.points)
            elif obj.type == 'FONT':
                global_verts = [matrix @ Vector((v.x, v.y, 0)) for v in obj.data.vertices]
            elif obj.type == 'EMPTY':
                world_location = obj.matrix_world.to_translation()
                obj.location.z -= world_location.z
                processed_objects += 1
                continue
            if not global_verts:
                continue
            min_z = min(v.z for v in global_verts)
            obj.location.z -= min_z
            processed_objects += 1
        self.report({'INFO'}, f"已处理 {processed_objects} 个物体")
        return {'FINISHED'}

# 清理未使用的材质
class CleanUnusedMaterialsOperator(bpy.types.Operator):
    """清理未使用的材质"""
    bl_idname = "object.clean_unused_materials"
    bl_label = "clear unused material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        material_texture_map = {}
        for mat in bpy.data.materials:
            if mat.users == 0 and not mat.use_fake_user:
                material_texture_map[mat] = get_material_textures(mat)
        removed_mats = 0
        for mat in list(bpy.data.materials):
            if mat in material_texture_map:
                bpy.data.materials.remove(mat)
                removed_mats += 1
        self.report({'INFO'}, f"已删除 {removed_mats} 材质")
        return {'FINISHED'}

# 移除所有找不到源文件的丢失路径
class OBJECT_OT_FixMissingPaths(bpy.types.Operator):
    """移除所有找不到源文件的丢失路径"""
    bl_idname = "object.fix_missing_paths"
    bl_label = "修复/清理丢失路径"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. 首先关闭自动打包，防止处理过程中持续报错
        if context.scene.tommy_pack_external:  # 假设你之前在 properties.py 注册过这个
            context.scene.tommy_pack_external = False

        missing_images = []
        # 2. 遍历所有图像数据块
        for img in bpy.data.images:
            if img.type == 'IMAGE' and img.source == 'FILE':
                # 检查绝对路径是否存在
                abs_path = bpy.path.abspath(img.filepath)
                if not os.path.exists(abs_path):
                    missing_images.append(img.name)
                    # 将丢失图片的路径设为空，并将其从内存中移除
                    img.user_clear()
                    bpy.data.images.remove(img)

        # 3. 同时也清理一下没有用户的材质或无用的节点（可选）
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        count = len(missing_images)
        if count > 0:
            self.report({'INFO'}, f"清理了 {count} 个无效的外部文件路径")
        else:
            self.report({'INFO'}, "未发现丢失的外部文件")

        return {'FINISHED'}

class CleanUnusedTexturesOperator(bpy.types.Operator):
    bl_idname = "object.clean_unused_textures"
    bl_label = "clear unused texture"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_count = 0
        for img in list(bpy.data.images):
            if img.users == 0 and not img.use_fake_user:
                bpy.data.images.remove(img)
                removed_count += 1
        self.report({'INFO'}, f"已移除 {removed_count} 个贴图")
        return {'FINISHED'}

# ==================== 渲染切换模式（仍属于公共） ====================
class RENDER_OT_SwitchRenderMode(bpy.types.Operator):
    bl_idname = "tommy.switch_render_mode"
    bl_label = "切换渲染模式"

    mode: bpy.props.StringProperty(default='CURRENT_FRAME')

    def execute(self, context):
        context.scene.tommy_render_mode = self.mode
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.tag_redraw()
        return {'FINISHED'}