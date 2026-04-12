import bpy


# ====================== 更新函数 ======================
def update_camera_display_size(self, context):
    display_size = context.scene.camera_display_size
    for cam in [obj for obj in context.scene.objects if obj.type == 'CAMERA']:
        cam.data.display_size = display_size


def update_pack_external(self, context):
    if context.scene.tommy_pack_external:
        bpy.ops.file.autopack_toggle()
    else:
        bpy.ops.file.autopack_toggle()


def update_original_resolution(self, context):
    """原始分辨率变化时更新当前帧"""
    scene = context.scene
    from .operators.camera_resolution import update_resolution_for_frame
    update_resolution_for_frame(scene, scene.frame_current)

def update_render_ui(self, context):
    """当渲染状态改变时，强制刷新所有的属性面板，确保按钮文字瞬间切换"""
    for area in context.screen.areas:
        if area.type == 'PROPERTIES':
            area.tag_redraw()

# 嵌入RGB色轮，允许用户实时更新颜色
def update_id_color_sync(self, context):
    target_name = self.tommy_id_name
    mat = bpy.data.materials.get(target_name)
    if mat and mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == 'EMISSION':
                node.inputs['Color'].default_value = self.tommy_id_color
                break
# ====================== RGB 色轮相关属性注册 ======================
bpy.types.Scene.tommy_id_name = bpy.props.StringProperty(
    name="材质名称",
    default="0-ID_Color_01",
)

bpy.types.Scene.tommy_id_color = bpy.props.FloatVectorProperty(
    name="ID颜色",
    subtype='COLOR',
    default=(1.0, 1.0, 1.0, 1.0),
    size=4,
    min=0.0,   # 必须加上，解决滑杆卡死
    max=1.0,   # 必须加上，解决滑杆卡死
    update=update_id_color_sync
)

# ====================== 摄像机显示尺寸属性注册 ======================
bpy.types.Scene.camera_display_size = bpy.props.FloatProperty(
    name="Camera Display Size",
    default=1.0,
    min=0.01,
    update=update_camera_display_size
)

# ====================== 预览文件名：保存原始路径 ======================
bpy.types.Scene.tommy_original_filepath_backup = bpy.props.StringProperty(
    name="原始输出路径备份",
    description="用于在渲染时保存初始路径，防止预览名出现重复后缀",
    default=""
)

# ====================== 自动打包资源 ======================
def get_autopack(self):
    """读取 Blender 当前打包状态"""
    return getattr(bpy.data, 'use_autopack', False)

def set_autopack(self, value):
    """设置打包状态（同时同步菜单勾选）"""
    if bpy.data.use_autopack != value:
        bpy.data.use_autopack = value
        # 可选：强制刷新界面
        for area in bpy.context.screen.areas:
            if area.type == 'PROPERTIES':
                area.tag_redraw()

bpy.types.Scene.tommy_pack_external = bpy.props.BoolProperty(
    name="自动打包资源",
    description="自动将所有外部资源打包到 .blend 文件",
    default=True,
    get=get_autopack,
    set=set_autopack
)

# ====================== 摄像机分辨率管理器 - 数据结构 ======================
class CameraResolutionSetting(bpy.types.PropertyGroup):
    camera_data_name: bpy.props.StringProperty(default="")

    temp_resolution: bpy.props.IntVectorProperty(
        size=2, default=(1920, 1080), min=1, max=10000
    )
    applied_resolution: bpy.props.IntVectorProperty(
        size=2, default=(1920, 1080), min=1, max=10000
    )
    is_applied: bpy.props.BoolProperty(default=False)

bpy.types.Scene.tommy_render_mode = bpy.props.EnumProperty(
    name="Tommy Render Mode",
    items=[('CURRENT_FRAME', "Current Frame", ""), ('SEQUENCE', "Sequence", "")],
    default='CURRENT_FRAME'
)

# 核心渲染状态标志（绑定了 UI 刷新函数）
bpy.types.Scene.is_current_rendering = bpy.props.BoolProperty(
    default=False, update=update_render_ui
)
bpy.types.Scene.is_sequence_rendering = bpy.props.BoolProperty(
    default=False, update=update_render_ui
)
bpy.types.Scene.tommy_active_render_task = bpy.props.StringProperty(
    name="当前执行的渲染任务",
    default="NONE",
    update=update_render_ui
)

bpy.types.Scene.tommy_original_resolution = bpy.props.IntVectorProperty(
    name="原始分辨率",
    size=2,
    default=(5000, 3750),
    min=1,
    max=10000,
    update=update_original_resolution
)


# ====================== 摄像机列表 UIList 相关属性 ======================
# 1. 先定义更新函数
def update_active_marker_index(self, context):
    scene = self
    # 使用 getattr 安全获取，或者直接访问（因为已经注册）
    if scene.tommy_is_syncing:
        return

    # 获取当前选中的标记点
    idx = scene.tommy_active_marker_index
    if idx < 0 or idx >= len(scene.timeline_markers):
        return

    markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
    target_marker = markers[idx]

    try:
        scene.tommy_is_syncing = True # 上锁
        scene.frame_set(target_marker.frame) # 跳转时间轴
    finally:
        scene.tommy_is_syncing = False # 解锁

# 2. 注册属性
bpy.types.Scene.tommy_active_marker_index = bpy.props.IntProperty(
    name="活动标记索引",
    default=-1,
    update=update_active_marker_index  # 确保绑定了更新函数
    )

bpy.types.Scene.tommy_is_syncing = bpy.props.BoolProperty(
    name="内部同步锁",
    default=False
)


# 3. 同步函数（保持不变）
def sync_marker_list_to_frame(scene):
    current_frame = scene.frame_current
    for i, marker in enumerate(scene.timeline_markers):
        if marker.frame == current_frame and marker.camera:
            if scene.tommy_active_marker_index != i:
                scene.tommy_active_marker_index = i
            return


# ====================== 间隔渲染 相关属性 ======================
bpy.types.Scene.tommy_custom_render_frames = bpy.props.StringProperty(
    name="自定义帧",
    description="输入需要渲染帧号，用逗号分隔（如：2,5,13）",
    default=""
)


# ====================== 命名格式查询 - 产品类型与命名格式映射 ======================
# 以后新增产品，只需要在这里添加一行即可！

NAMING_FORMATS = {
    'crib':
        "\n M30880_crib-front",
    'crib-9in1':
        "\n M30880W_bassinet-front"
        "\n M30880W_midi-front , M30880W_midi-toddler-front , M30880W_midi-daybed-front"
        "\n M30880W_crib-front"
        "\n M30880W_crib-toddler-front , M30880W_junior-front , M30880W_crib-daybed-front"
        "\n  M30880W_fullsize-front",
    'twin/full bed':
        "\n M15996NL_full bed-front",
    'glider':
        "\n B17186YC_glider-angle , B17186YC_glider-half-reclined , B17186YC_glider-full-reclined \n",
    'glider light on':
        "\n B17183YC_glider-angle-light-lever 1 , B17183YC_glider-angle-light-lever 2 , B17183YC_glider-angle-light-lever 3",
    'ottoman':
        "\n M30985TTFTDF_ottoman-angle , M30985TTFTDF_ottoman-angle-lid open",
}
bpy.types.Scene.tommy_naming_product_type = bpy.props.EnumProperty(
    name="产品类型",
    items=[
        ('crib', "crib", ""),
        ('crib-9in1', "crib 9in1", ""),
        ('twin/full', "twin/full", ""),
        ('glider', "glider", ""),
        ('glider', "glider", ""),
        ('glider light on', "glider light on", ""),
        ('ottoman', "ottoman", ""),
        ('PRODUCT_E', "产品e", ""),

        # 在这里继续添加新产品类型...
    ],
    default='crib',
)


