import bpy
from ....common.types.framework import reg_order  # 装饰器，用于设定不同的类的先后注册顺序
from bpy.app.handlers import persistent


@persistent
def sync_ui_list_handler(scene, depsgraph=None):
    if bpy.app.is_job_running('RENDER'):
        return

     # 【修复】使用 get 安全读取字典属性
    if scene.get("tommy_is_syncing", False):
        return

    current_frame = scene.frame_current
    target_index = -1

    for i, marker in enumerate(scene.timeline_markers):
        if marker.frame == current_frame and marker.camera:
            target_index = i
            break

    if scene.tommy_active_marker_index != target_index:
        # 【修复】使用字典语法动态赋值，无需注册！
        scene["tommy_is_syncing"] = True
        scene.tommy_active_marker_index = target_index
        scene["tommy_is_syncing"] = False

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'VIEW_3D', 'PROPERTIES'}:
                    area.tag_redraw()


def check_markers_order(scene):
    """辅助函数：检查当前时间轴标记是否处于乱序状态"""
    if not scene.timeline_markers:
        return False
    frames = [m.frame for m in scene.timeline_markers]
    # 如果当前帧序列与排序后的序列不一致，说明乱序了
    return frames != sorted(frames)


def trigger_sort_safely():
    scene = bpy.context.scene

    # 【修复】字典语法赋值
    scene["tommy_is_sorting_markers"] = True

    try:
        bpy.ops.tommy.sort_timeline_markers()
    except Exception as e:
        print(f"Tommy 自动排序标记失败: {e}")

    # 【修复】字典语法赋值
    scene["tommy_is_sorting_markers"] = False
    return None

@persistent
def auto_sort_markers_handler(scene, depsgraph):
    """
    监听依赖图更新。当我们在时间轴上增/删/改标记时，会触发此函数
    """
    if bpy.app.is_job_running('RENDER'):
        return

    # 如果此时正在执行 UI 列表的双向同步，或者正在执行排序，则直接放行，避免死循环
    if scene.get("tommy_is_syncing", False) or scene.get("tommy_is_sorting_markers", False):
        return

    # 检查是否真的发生了乱序
    if check_markers_order(scene):
        # 发现乱序！我们不直接调用 ops，而是注册一个 0.1 秒后执行的计时器
        # 这样可以巧妙地跳出 Handler 的严格上下文限制
        if not bpy.app.timers.is_registered(trigger_sort_safely):
            bpy.app.timers.register(trigger_sort_safely, first_interval=0.1)



class RENDER_UL_bound_cameras(bpy.types.UIList):
    """自定义摄像机绑定列表 UI"""
    bl_idname = "RENDER_UL_bound_cameras"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # 这里的 item 对应的是 context.scene.timeline_markers 中的标记对象
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # 使用 split 让排版像表格一样整齐
            split = row.split(factor=0.35)
            split.label(text=f"帧 {item.frame}")

            if item.camera:
                split.label(text=item.camera.name)
            else:
                split.label(text="未绑定", icon='ERROR')

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CAMERA_DATA')

    def filter_items(self, context, data, propname):
        """核心逻辑：筛选和排序数据源，只显示绑定了摄像机且在范围内的标记"""
        markers = getattr(data, propname)
        flt_flags = []
        scene = context.scene

        # 1. 过滤：保留有摄像机的标记，且在设定的渲染帧范围内
        for marker in markers:
            if marker.camera and scene.frame_start <= marker.frame <= scene.frame_end:
                flt_flags.append(self.bitflag_filter_item)
            else:
                flt_flags.append(0)  # 0代表隐藏该项

        # 2. 排序映射修复：构建正确的索引字典
        indexed_markers = list(enumerate(markers))
        # 先按照帧号从小到大排序
        sorted_markers = sorted(indexed_markers, key=lambda x: x[1].frame)

        # 核心修复：Blender 要求 flt_neworder[原始索引] = 新的视觉排序位置
        flt_neworder = [0] * len(markers)
        for new_visual_index, (original_index, marker) in enumerate(sorted_markers):
            flt_neworder[original_index] = new_visual_index

        return flt_flags, flt_neworder


@reg_order(10)  # 父面板必须先注册
class RENDER_PT_NamedHelper(bpy.types.Panel):
    bl_label = "Tommy's Render Tools"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_order = 100

    def draw_render_button(self, layout, context, task_id, operator_id, default_text, icon, active_camera=True):
        """
        统一渲染按钮生成器，处理：蓝显、置灰、文字切换及F12判断。
        task_id: 'SINGLE', 'SEQUENCE', 'CUSTOM'
        """
        scene = context.scene
        active_task = scene.tommy_active_render_task

        # 1. 判定外部 F12 渲染：如果 Blender 正在渲染，但不是我们的任务，则视为外部渲染
        is_blender_rendering = bpy.app.is_job_running('RENDER')
        is_external_render = is_blender_rendering and active_task == "NONE"

        # 2. 状态判定
        is_this_active = (active_task == task_id)
        is_other_active = (active_task != "NONE" and active_task != task_id)

        row = layout.row(align=True)
        row.scale_y = 1.5

        # 3. 核心逻辑分支
        if is_this_active:
            # 当前按钮正在运行：显示“按ESC中断”，高亮蓝色 (depress=True)
            row.operator(operator_id, text="按 ESC 中断渲染", icon='PAUSE', depress=True)
        elif is_other_active or is_external_render or not active_camera:
            # 其他渲染正在运行，或者系统正在 F12，或者没绑定相机：置灰
            row.enabled = False
            row.operator(operator_id, text=default_text, icon=icon)
        else:
            # 闲置状态：正常显示
            row.operator(operator_id, text=default_text, icon=icon)

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 模式切换
        mode_split = layout.split(factor=0.5, align=True)
        left = mode_split.column(align=True)
        left.scale_y = 1.1
        left.operator("tommy.switch_render_mode", text="当前帧",
                      depress=(scene.tommy_render_mode == 'CURRENT_FRAME')).mode = 'CURRENT_FRAME'

        right = mode_split.column(align=True)
        right.scale_y = 1.1
        right.operator("tommy.switch_render_mode", text="序列",
                       depress=(scene.tommy_render_mode == 'SEQUENCE')).mode = 'SEQUENCE'

        content = layout.box()
        if scene.tommy_render_mode == 'CURRENT_FRAME':
            self.draw_current_frame_mode(content, context)
        else:
            self.draw_sequence_mode(content, context)

        layout.separator()
        layout.prop(scene, 'tommy_pack_external', text="自动打包资源")

        layout.separator()
        notes = layout.column(align=True)
        notes.scale_y = 0.9
        notes.label(text="渲染前请检查:")
        notes.label(text="• 输出路径是否正确")
        notes.label(text="• 渲染数量是否正确")
        notes.label(text="• 文件格式是否正确")
        notes.label(text="• 需要为每帧在时间线中绑定摄像机")
        notes.label(text="• 渲染进行中只能按 ESC 键中断当前帧")

    def draw_current_frame_mode(self, layout, context):
        scene = context.scene
        current_camera = self.get_current_frame_camera(scene)

        # --- 设置区块 ---
        col = layout.column(align=True)
        col.label(text="设置")

        # 1. 渲染引擎
        split = col.split(factor=0.5)
        split.label(text="渲染引擎：")
        split.label(text=scene.render.engine)

        # 2. 渲染采样
        split = col.split(factor=0.5)
        split.label(text="渲染采样：")
        engine = scene.render.engine
        if engine == 'CYCLES':
            split.prop(scene.cycles, "samples", text="")
        elif engine in {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
            # 兼容不同版本的 Eevee 采样属性名
            if hasattr(scene.eevee, "render_samples"):
                split.prop(scene.eevee, "render_samples", text="")
            elif hasattr(scene.eevee, "taa_render_samples"):
                split.prop(scene.eevee, "taa_render_samples", text="")
            else:
                split.label(text="N/A")
        else:
            split.label(text="N/A")

        # 3. 图像分辨率
        split = col.split(factor=0.5)
        split.label(text="图像分辨率：")
        split.label(text=f"{scene.render.resolution_x} × {scene.render.resolution_y}")

        # 4. 图像格式
        split = col.split(factor=0.5)
        split.label(text="图像格式：")
        split.prop(scene.render.image_settings, "file_format", text="")

        col.separator()

        # 5. 当前帧号
        split = col.split(factor=0.5)
        split.label(text="当前帧号：")
        split.label(text=str(scene.frame_current))

        # 6. 摄像机状态
        split = col.split(factor=0.5)
        split.label(text="摄像机绑定：")
        if current_camera:
            split.label(text=current_camera.name)
        else:
            split.alert = True
            split.label(text="无绑定摄像机", icon='ERROR')

        col.separator()

        # 使用统一渲染按钮系统
        self.draw_render_button(
            col, context,
            task_id="SINGLE",
            operator_id="tommy.render_current_frames",
            default_text="渲染当前帧" if current_camera else "无绑定摄像机，无法渲染",
            icon='PLAY',
            active_camera=bool(current_camera)
        )

    def draw_sequence_mode(self, layout, context):
        scene = context.scene
        frames_info, missing_frames = self.collect_frames_info(scene)

        # --- 顶部设置区块 ---
        col = layout.column(align=True)
        col.label(text="设置")

        # 1. 渲染引擎 (只读显示)
        split = col.split(factor=0.5)
        split.alignment='CENTER'
        split.label(text="渲染引擎：")
        split.label(text=scene.render.engine)

        # 2. 渲染采样 (智能适配引擎并允许修改)
        split = col.split(factor=0.5)
        split.label(text="渲染采样：")
        engine = scene.render.engine
        if engine == 'CYCLES':
            split.prop(scene.cycles, "samples", text="")
        elif engine in {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
            # 适配 Blender 4.2+ 的 Eevee Next 和旧版 Eevee
            if hasattr(scene.eevee, "render_samples"):
                split.prop(scene.eevee, "render_samples", text="")
            elif hasattr(scene.eevee, "taa_render_samples"):
                split.prop(scene.eevee, "taa_render_samples", text="")
            else:
                split.label(text="N/A")
        else:
            split.label(text="N/A")

        # 3. 图像分辨率 (只读显示)
        split = col.split(factor=0.5)
        split.label(text="图像分辨率：")
        split.label(text=f"{scene.render.resolution_x} × {scene.render.resolution_y}")

        # 4. 图像格式 (允许修改)
        split = col.split(factor=0.5)
        split.label(text="图像格式：")
        split.prop(scene.render.image_settings, "file_format", text="")

        # 5. 总帧数 (只读显示)
        total_frames = scene.frame_end - scene.frame_start + 1
        split = col.split(factor=0.5)
        split.label(text="总帧数：")
        split.label(text=str(total_frames))

        # 6. 渲染范围 (允许修改，左右并排)
        split = col.split(factor=0.5)
        split.label(text="渲染范围：")
        range_row = split.row(align=True)
        range_row.prop(scene, "frame_start", text="")
        range_row.prop(scene, "frame_end", text="")

        col.separator()

        # --- 摄像机绑定状态区块 ---
        col.label(text="摄像机绑定状态：")

        # 1. 已绑定帧数 (对齐中线)
        split = col.split(factor=0.5)
        split.label(text="已绑定:", icon='CHECKMARK')
        split.label(text=f"{len(frames_info)} 帧")

        # 2. 缺失帧处理
        has_missing = len(missing_frames) > 0
        if has_missing:
            # 缺失数量统计 (对齐中线)
            split = col.split(factor=0.5)
            split.alert = True
            split.label(text="缺失：", icon='ERROR')
            split.label(text=f"{len(missing_frames)} 帧")

            row_detail = col.split(factor=0.5, align=True)

            # 处理详情文字内容
            if len(missing_frames) <= 5:
                missing_text = ", ".join(map(str, missing_frames))
            else:
                missing_text = ", ".join(map(str, missing_frames[:5])) + "..."

            # 左侧显示详情内容
            row_detail.label(text=f"详情: {missing_text}", icon='INFO')

            # 右侧放置跳转按钮 (文字缩短为“跳转首帧”以适配空间)
            row_detail.operator("tommy.preview_missing_frames",
                                text="跳转首帧",).frame = missing_frames[0]

        col.separator()

        # --- 修改部分：预览输出文件名 和 检查同名标记 同行显示，高度 1.5 ---
        preview_row = col.row(align=True)
        preview_row.scale_y = 1.5
        # 只要系统在渲染，这些按钮也应该置灰
        # preview_row.enabled = not bpy.app.is_job_running('RENDER')
        preview_row.operator("tommy.preview_output_names",
                             icon='VIEWZOOM',
                             text="预览输出文件名")
        preview_row.operator("tommy.check_duplicate_markers",
                             icon='HELP',
                             text="检查同名标记")
        # ---------------------------------------------------------

        col.separator()

        # 使用统一渲染按钮系统处理“渲染当前序列”
        button_text = f"渲染当前序列 ({len(missing_frames)} 帧缺失)" if has_missing else "渲染当前序列"
        self.draw_render_button(
            col, context,
            task_id="SEQUENCE",
            operator_id="tommy.render_all_frames",
            default_text=button_text,
            icon='PLAY',
            active_camera=not has_missing
        )

        # --- 间隔渲染 UI ---
        col.separator()

        # 使用 split 布局，左侧输入框占 70%，右侧按钮占 30%
        custom_row = col.split(factor=0.7, align=True)

        # 1. 输入框 (使用 placeholder 提示格式)
        input_row = custom_row.row()
        input_row.scale_y = 1.5
        input_row.enabled = not bpy.app.is_job_running('RENDER')
        input_row.prop(scene, "tommy_custom_render_frames", text="", placeholder="帧号用逗号分隔: 2,5,13")

        # 2. 渲染按钮，使用统一渲染按钮系统
        self.draw_render_button(
            custom_row, context,
            task_id="CUSTOM",
            operator_id="render.render_custom_sequence",
            default_text="间隔渲染",
            icon='PLAY',
            active_camera=True
        )

        # 已绑定摄像机列表
        if frames_info:
            col.separator()

            # 使用 split 分隔行，factor 控制左侧标签占用的比例
            # factor=0.7 表示标签占 70%，按钮占 30%，从而实现按钮长度缩短
            split = col.split(factor=0.7, align=True)

            # 左侧：显示标签
            split.label(text="已绑定摄像机列表:", icon='OUTLINER_OB_CAMERA')

            # 右侧：放置排序按钮，设置 scale_y 调整高度
            row_btn = split.row(align=True)
            row_btn.scale_y = 1.5
            row_btn.operator("tommy.sort_timeline_markers", text="排序", icon='SORT_ASC')

            # 下方显示列表
            col.template_list(
                "RENDER_UL_bound_cameras",
                "",
                scene,
                "timeline_markers",
                scene,
                "tommy_active_marker_index",
                rows=5
            )

    def get_current_frame_camera(self, scene):
        current_frame = scene.frame_current
        for marker in scene.timeline_markers:
            if marker.frame == current_frame and marker.camera:
                return marker.camera
        return None

    def collect_frames_info(self, scene):
        frames_info = []
        missing_frames = []
        start_frame = scene.frame_start
        end_frame = scene.frame_end
        marker_frames = {}
        for marker in scene.timeline_markers:
            if marker.camera:
                marker_frames[marker.frame] = marker.camera
        for frame in range(start_frame, end_frame + 1):
            if frame in marker_frames:
                frames_info.append({
                    'frame': frame,
                    'camera': marker_frames[frame].name
                })
            else:
                missing_frames.append(frame)
        return frames_info, missing_frames


# ====================== 子面板：命名格式查询 ======================
@reg_order(11)  # 子面板必须在父面板之后注册
class RENDER_PT_NamingQuery(bpy.types.Panel):
    bl_label = "命名格式查询"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_parent_id = "RENDER_PT_NamedHelper"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        row.label(text="产品类型:")
        row.prop(scene, "tommy_naming_product_type", text="")
        row.separator(factor=2.0)

        # 查询按钮
        row.operator("tommy.naming_query", text="查询", icon='VIEWZOOM')



