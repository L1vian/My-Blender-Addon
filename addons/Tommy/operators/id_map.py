import bpy
import os

# 清除视图可见物体的材质槽
class OBJECT_OT_ClearVisibleMaterials(bpy.types.Operator):
    """仅清除视图中可见物体的材质槽"""
    bl_idname = "object.clear_visible_materials"
    bl_label = "清除可见材质"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        # 核心逻辑：只过滤出在当前视图层未隐藏 (not hide_get) 的网格物体
        visible_meshes = [obj for obj in context.view_layer.objects
                          if obj.type == 'MESH' and not obj.hide_get()]

        for obj in visible_meshes:
            if obj.data and obj.data.materials:
                obj.data.materials.clear()
                count += 1

        self.report({'INFO'}, f"已清空 {count} 个可见物体的材质槽")
        return {'FINISHED'}

# 创建 ID_random B&W 材质并应用
class OBJECT_OT_CreateIDMaterial(bpy.types.Operator):
    """创建 ID_random B&W 材质并应用"""
    bl_idname = "object.create_id_material"
    bl_label = "生成随机 ID 材质"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat_name = "0-ID_Random_B&W"

        # 1. 获取或新建材质
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)

        # 优化1：在视图显示中打开背面剔除
        mat.use_backface_culling = True

        # 配置节点
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # 2. 创建节点并布局
        node_info = nodes.new(type='ShaderNodeObjectInfo')
        node_info.location = (-600, 0)

        node_ramp = nodes.new(type='ShaderNodeValToRGB')
        node_ramp.location = (-300, 0)

        node_emit = nodes.new(type='ShaderNodeEmission')
        node_emit.location = (0, 0)

        node_output = nodes.new(type='ShaderNodeOutputMaterial')
        node_output.location = (250, 0)

        # 3. 建立逻辑连接
        links.new(node_info.outputs['Random'], node_ramp.inputs['Fac'])
        links.new(node_ramp.outputs['Color'], node_emit.inputs['Color'])
        links.new(node_emit.outputs['Emission'], node_output.inputs['Surface'])

        # 4. 应用到选中物体
        selected_geos = [
            obj for obj in context.selected_objects
            if obj.type in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}
        ]

        for obj in selected_geos:
            # 检查物体是否有材质槽（有些特殊情况下 data 为空）
            if obj.data and hasattr(obj.data, "materials"):
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials.clear()
                    obj.data.materials.append(mat)
                    # obj.data.materials[0] = mat

        self.report({'INFO'}, f"材质 '{mat_name}' 已应用")
        return {'FINISHED'}

        #RGB色轮 输入框 按钮 的交互逻辑


# ====================== 新建 ID 材质（自动递增编号） ======================
class OBJECT_OT_CreateNewIDMaterial(bpy.types.Operator):
    """新建下一个 ID_Color_0X 材质并赋予活动物体"""
    bl_idname = "object.create_new_id_material"
    bl_label = "新建 ID 材质"
    bl_description = "自动创建下一个 0-ID_Color_0X 材质，使用当前面板颜色，并赋予活动物体"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return(
            context.active_object is not None
            and context.active_object.type in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}
            and context.active_object in context.selected_objects
        )


    def execute(self, context):
        scene = context.scene

        # 1. 自动计算下一个可用 ID 编号
        max_id = 0
        for mat in bpy.data.materials:
            if mat.name.startswith("0-ID_Color_"):
                try:
                    num_str = mat.name.split("_")[-1]
                    num = int(num_str)
                    if num > max_id:
                        max_id = num
                except ValueError:
                    continue
        next_id = max_id + 1
        mat_name = f"0-ID_Color_{next_id:02d}"   # 保持两位数格式：01、02、10...

        # 2. 创建新材质 + 节点设置（匹配 handler 查找的 Emission 节点）
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # 清空默认节点
        for node in list(nodes):
            nodes.remove(node)

        # 创建 Emission + Output
        emission = nodes.new(type='ShaderNodeEmission')
        emission.inputs['Color'].default_value = scene.tommy_id_color
        emission.location = (0, 0)

        output = nodes.new(type='ShaderNodeOutputMaterial')
        output.location = (300, 0)

        links.new(emission.outputs['Emission'], output.inputs['Surface'])

        # 3. 清空材质槽 并 赋予活动物体
        obj = context.active_object
        if obj.data.materials:
            obj.data.materials.clear()
            obj.data.materials.append(mat)
        else:
            obj.data.materials.append(mat)

        # 4. 更新面板名称（让 handler 保持一致）
        scene.tommy_id_name = mat_name

        self.report({'INFO'}, f"✅ 已创建并赋予 {mat_name}")
        return {'FINISHED'}


# ====================== 链接材质（清空选中槽 + 链接活动物体材质） ======================
class OBJECT_OT_LinkActiveIDMaterial(bpy.types.Operator):
    """将活动项的 ID 材质链接到所有选中的物体"""
    bl_idname = "object.link_active_id_material"
    bl_label = "链接材质"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # 1. 选中物体中属于支持材质的类型 且 数量 ≥ 2
        # 2. 活动物体必须在选中列表中
        allowed_types = {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}

        # 计算当前选中物体里有效的几何体数量
        valid_selected_count = sum(
            1 for obj in context.selected_objects
            if obj.type in allowed_types
        )

        return (
                valid_selected_count >= 2
                and context.active_object is not None
                and context.active_object in context.selected_objects
        )

    def execute(self, context):
        active_obj = context.active_object

        # 安全检查（双重保险）
        if not active_obj or not active_obj.data or not hasattr(active_obj.data, "materials") or not active_obj.data.materials:
            self.report({'WARNING'}, "活动项没有材质，无法链接")
            return {'CANCELLED'}

        active_mat = active_obj.data.materials[0]
        mat_name = active_mat.name

        count = 0
        # 先清空再追加（保证单槽 + 即时刷新）
        for obj in context.selected_objects:
            if obj.type not in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}:
                continue
            if obj.data and hasattr(obj.data, "materials"):
                obj.data.materials.clear()
                obj.data.materials.append(active_mat)
                count += 1

        self.report({'INFO'}, f"已将 {count} 个物体链接到 '{mat_name}' 材质")
        return {'FINISHED'}



# 选中所有与当前物体材质相同的物体
class OBJECT_OT_SelectLinkedMaterial(bpy.types.Operator):
    """选中所有与当前物体材质相同的物体"""
    bl_idname = "object.select_linked_material_custom"
    bl_label = "选择相连材质"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
                context.active_object is not None
                and context.active_object.type in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}
                and context.active_object in context.selected_objects

        )

    def execute(self, context):
        try:
            bpy.ops.object.select_linked(type='MATERIAL')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"执行失败: {str(e)}")
            return {'CANCELLED'}

# 显示并选中『视图隐藏但渲染启用』的物体
class OBJECT_OT_ShowHiddenRenderable(bpy.types.Operator):
    """显示所有『视图隐藏但渲染启用』的物体"""
    bl_idname = "object.show_hidden_renderable"
    bl_label = "查看隐藏物体"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. 取消当前所有选中状态
        bpy.ops.object.select_all(action='DESELECT')

        count = 0
        # 2. 查找幽灵物体
        for obj in context.view_layer.objects:
            if obj.hide_get() and not obj.hide_render:
                obj.hide_set(False)  # 取消隐藏
                obj.select_set(True)  # 选中
                count += 1

        if count > 0:
            # 自动将其中一个设为活跃物体，方便用户直接看到属性
            context.view_layer.objects.active = context.selected_objects[0]
            self.report({'INFO'}, f"已找回 {count} 个隐藏渲染物体")
        else:
            self.report({'INFO'}, "未发现隐藏的渲染物体")

        return {'FINISHED'}


# ====================== ID_Color 材质选择菜单（匹配参考图样式） ======================
class OBJECT_MT_IDColorMenu(bpy.types.Menu):
    """ 下拉菜单：列出所有 0-ID_Color_XX 材质 """
    bl_idname = "OBJECT_MT_id_color_menu"
    bl_label = "0-ID Color 材质列表"

    def draw(self, context):
        layout = self.layout
        # 收集所有 0-ID_Color_ 材质并排序
        mats = [mat for mat in bpy.data.materials if mat.name.startswith("0-ID_Color_")]
        mats.sort(key=lambda m: m.name)

        if not mats:
            layout.label(text="暂无 0-ID_Color_ 材质", icon='INFO')
            return

        for mat in mats:
            preview = mat.preview
            icon_value = preview.icon_id if preview is not None else 0

            op = layout.operator(
                "object.set_id_material_from_menu",
                text=mat.name,
                icon_value=icon_value
            )
            op.mat_name = mat.name


# ====================== 点击菜单项后执行加载 ======================
class OBJECT_OT_SetIDMaterialFromMenu(bpy.types.Operator):
    """从菜单选中 ID_Color 材质后加载到面板 + 赋予活动物体"""
    bl_idname = "object.set_id_material_from_menu"
    bl_label = "加载 ID 材质"
    bl_options = {'REGISTER', 'UNDO'}

    mat_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        mat = bpy.data.materials.get(self.mat_name)

        if not mat:
            self.report({'WARNING'}, f"材质 {self.mat_name} 不存在")
            return {'CANCELLED'}

        # 1. 更新面板
        scene.tommy_id_name = self.mat_name

        # 2. 加载 Emission 颜色
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'EMISSION' and 'Color' in node.inputs:
                    color_val = node.inputs['Color'].default_value[:]
                    if list(scene.tommy_id_color) != list(color_val):
                        scene.tommy_id_color = color_val
                    break

        # 3. 替换材质
        count = 0
        allowed_types = {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}

        for obj in context.selected_objects:
            if obj.type not in allowed_types:
                continue
            if obj.data and hasattr(obj.data, "materials"):
                obj.data.materials.clear()  # 清空所有槽
                obj.data.materials.append(mat)  # 链接新材质
                count += 1
        # 4. 加载材质预览小球
        if mat.preview is None or mat.preview.icon_id == 0:
            mat.preview_ensure()

        # 5. 同时告诉用户应用了多少个物体
        if count == 0:
            self.report({'WARNING'}, f"未找到可应用材质的物体")
        else:
            self.report({'INFO'}, f"✅ 已将 {self.mat_name} 应用到 {count} 个选中物体")


        return {'FINISHED'}




# ====================== 选中物体自动加载 ID ======================
from bpy.app.handlers import persistent

@persistent
def auto_load_id_from_active(depsgraph):
    """ 仅当面板当前名称 与 选中物体材质名称 不同时，才自动加载"""
    try:
        context = bpy.context
        obj = context.active_object
        if not obj:
            return

        # 1. 类型过滤
        if obj.type not in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'META', 'FONT'}:
            return

        # 2. 材质检查
        if not obj.data or not hasattr(obj.data, "materials") or len(obj.data.materials) == 0:
            return

        mat = obj.data.materials[0]
        if not mat or not mat.name.startswith("0-ID_Color_"):
            return

        if not mat.use_nodes:
            return

        scene = context.scene

        # ==================== 核心判断 ====================
        if scene.tommy_id_name == mat.name:
            return  # 名称一致 → 已经在编辑这个材质，不重复加载

        # 3. 执行加载
        scene.tommy_id_name = mat.name

        for node in mat.node_tree.nodes:
            if node.type == 'EMISSION' and node.inputs.get('Color'):
                current_color = node.inputs['Color'].default_value[:]
                if list(scene.tommy_id_color) != list(current_color):
                    scene.tommy_id_color = current_color
                break

    except Exception:
        pass  # handler 必须静默
