import bpy
import os
import re
import time


# ====================== 增強型基類（文件驅動 + 看門狗版） ======================
class BaseRenderOperator:
    """
    所有渲染操作符的基类。
    采用「文件确认驱动」机制：只有检测到上一帧文件写入成功，才会推进进度。
    """
    _timer = None
    _current_frame = 0
    _frames_to_render = []
    _is_rendering = False
    _cancelled = False
    _stuck_count = 0  # 看门狗计数器
    _last_output_path = ""  # 用于校验文件是否存在

    _original_camera = None
    _original_filepath = ""  # 关键：保存原始输出路径，用于提取前缀

    def modal(self, context, event):
        if event.type == 'TIMER':
            # 1. 处理用户取消
            if self._cancelled:
                self.report({'WARNING'}, f"渲染被中断！已完成 {self._current_frame} 帧")
                self.finish_render(context)
                return {'CANCELLED'}

            # 2. 状态检查与看门狗 (Watchdog)
            if self._is_rendering:
                if not bpy.app.is_job_running('RENDER'):
                    self._stuck_count += 1
                    # 5秒看门狗 (计数到 10，因为 Timer 是 0.5s 一次)
                    if self._stuck_count >= 10:
                        self.report({'WARNING'}, "检测到渲染可能卡死，尝试重新发送指令...")
                        self._is_rendering = False
                        self._stuck_count = 0
                else:
                    self._stuck_count = 0
                return {'PASS_THROUGH'}

            # 3. 准备渲染下一帧
            if not self._is_rendering:
                if self._current_frame >= len(self._frames_to_render):
                    self.report({'INFO'}, f"序列渲染全部完成，共 {len(self._frames_to_render)} 帧")
                    self.finish_render(context)
                    return {'FINISHED'}

                frame_info = self._frames_to_render[self._current_frame]

                if bpy.app.is_job_running('RENDER'):
                    return {'PASS_THROUGH'}

                scene = context.scene
                scene.frame_set(frame_info['frame'])

                if self._original_camera is None:
                    self._original_camera = scene.camera
                scene.camera = frame_info['camera']

                # --- 调用统一的命名逻辑 ---
                self._last_output_path = self.set_output_path(scene, frame_info['frame'], frame_info['camera'])

                # msg = f"🚀 正在准备：第 {frame_info['frame']} 帧 (摄像机: {frame_info['camera'].name})"
                # print(msg)

                self.remove_handlers()
                bpy.app.handlers.render_complete.append(self.render_complete)
                bpy.app.handlers.render_cancel.append(self.render_cancel)

                res = bpy.ops.render.render('INVOKE_DEFAULT', write_still=True)

                if 'RUNNING_MODAL' in res:
                    self._is_rendering = True
                    self._stuck_count = 0
                else:
                    self.report({'WARNING'}, "渲染引擎拒绝请求，等待重试...")
                    self._is_rendering = False

        return {'PASS_THROUGH'}

    def set_output_path(self, scene, frame, camera):
        """
        增强版命名逻辑：解决目录不存在及路径拼接错误
        """
        # 1. 获取绝对路径并标准化（统一斜杠方向，去除末尾多余斜杠）
        raw_path = self._original_filepath if (hasattr(self, '_original_filepath') and self._original_filepath) else scene.render.filepath
        abs_base_path = os.path.normpath(bpy.path.abspath(raw_path))

        # 2. 智能判断：如果原始路径本身就是一个存在的目录，或者以斜杠结尾
        if os.path.isdir(abs_base_path) or raw_path.endswith(("\\", "/")):
            folder = abs_base_path
            prefix = ""
        else:
            # 否则，认为最后一部分是文件名前缀
            folder = os.path.dirname(abs_base_path)
            prefix = os.path.basename(abs_base_path)

        # 3. 彻底移除前缀名中的自动编号(####)和旧后缀
        prefix = re.sub(r'[#%]+(\d+d)?', '', prefix)
        if '.' in prefix:
            prefix = prefix.rsplit('.', 1)[0]

        # 4. 【核心修复】强制创建目录
        # 使用 normpath 确保路径格式正确后再创建
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
                print(f"已自动创建渲染目录: {folder}")
            except Exception as e:
                self.report({'ERROR'}, f"无法创建文件夹，请检查权限: {str(e)}")
                return None

        # 5. 清理摄像机名称
        safe_camera_name = re.sub(r'[\\/:*?"<>|]', '_', camera.name)

        # 6. 确定后缀名
        file_format = scene.render.image_settings.file_format
        ext_map = {
            'PNG': '.png', 'JPEG': '.jpg', 'TIFF': '.tif',
            'BMP': '.bmp', 'TARGA': '.tga', 'OPEN_EXR': '.exr',
            'OPEN_EXR_MULTILAYER': '.exr', 'HDR': '.hdr',
        }
        extension = ext_map.get(file_format, '.png')

        # 7. 拼接最终文件名（确保不产生双斜杠或丢失斜杠）
        if prefix and not prefix.isspace():
            final_filename = f"{prefix}_{safe_camera_name}{extension}"
        else:
            final_filename = f"{safe_camera_name}{extension}"

        # 8. 得到最终完整的文件绝对路径
        target_full_path = os.path.join(folder, final_filename)

        # 9. 写入 Blender 设置
        scene.render.filepath = target_full_path
        scene.render.use_file_extension = False # 禁用自动后缀，使用我们手动拼好的路径

        return target_full_path

    def render_complete(self, scene, depsgraph):
        """渲染结束回调：执行物理文件检查"""
        abs_path = bpy.path.abspath(self._last_output_path)
        time.sleep(0.1)  # 给文件系统微小缓冲

        if os.path.exists(abs_path):
            # print(f"✅ 文件确认存在：{os.path.basename(abs_path)}")
            self._current_frame += 1
            self._is_rendering = False
        else:
            print(f"❌ 文件未找到！将重新尝试渲染当前帧: {abs_path}")
            self._is_rendering = False

        self.remove_handlers()

    def render_cancel(self, scene, depsgraph):
        self._cancelled = True
        self._is_rendering = False
        self.remove_handlers()

    def remove_handlers(self):
        while self.render_complete in bpy.app.handlers.render_complete:
            bpy.app.handlers.render_complete.remove(self.render_complete)
        while self.render_cancel in bpy.app.handlers.render_cancel:
            bpy.app.handlers.render_cancel.remove(self.render_cancel)

    def finish_render(self, context):
        scene = context.scene
        # 核心：无论什么渲染，结束时都把所有标志位和任务 ID 设为默认状态
        scene.is_current_rendering = False
        scene.is_sequence_rendering = False
        scene.tommy_active_render_task = "NONE"

        # 1. 还原路径
        if hasattr(self, '_original_filepath') and self._original_filepath:
            context.scene.render.filepath = self._original_filepath

        # 移除计时器
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        # 恢复原始设置
        if self._original_camera:
            scene.camera = self._original_camera

        self._is_rendering = False

        # 强制界面刷新
        for screen in context.workspace.screens:
            for area in screen.areas:
                area.tag_redraw()


class RENDER_OT_name_by_camera(bpy.types.Operator, BaseRenderOperator):
    bl_idname = "render.name_by_camera"
    bl_label = "按摄像机名称进行渲染"
    bl_description = "根据时间轴上绑定的摄像机标记进行渲染并重命名文件"

    def execute(self, context):
        scene = context.scene

        # 1. 启动状态开关：这会让 UI 按钮立即变为“按 ESC 中断”
        scene.is_sequence_rendering = True
        scene.tommy_active_render_task = "SEQUENCE"
        # 2. 备份原始路径：这样渲染结束后，F12 看到的依然是用户原本设置的路径
        self._original_filepath = scene.render.filepath

        # --- 关键修复：补全初始化逻辑 ---
        self._frames_to_render = []
        self._current_frame = 0
        self._is_rendering = False
        self._cancelled = False
        self._stuck_count = 0
        self._original_camera = scene.camera  # 保存原始相机

        # 扫描时间轴上的标记点
        markers = sorted(scene.timeline_markers, key=lambda m: m.frame)

        for marker in markers:
            if marker.camera:
                self._frames_to_render.append({
                    'frame': marker.frame,
                    'camera': marker.camera
                })

        if not self._frames_to_render:
            self.report({'ERROR'}, "未发现绑定摄像机的标记点！")
            return {'CANCELLED'}

        # 启动定时器与模态循环
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)

        self.report({'INFO'}, f"开始序列渲染：共 {len(self._frames_to_render)} 个标记点")
        return {'RUNNING_MODAL'}


# ====================== 所有渲染 Operator ======================
class RENDER_OT_RenderAllFrames(bpy.types.Operator, BaseRenderOperator):
    """根据时间线标记中的摄像机，渲染整个序列的每一帧"""
    bl_idname = "tommy.render_all_frames"
    bl_label = "使用摄像机名称渲染序列"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """当有任一渲染任务在进行时，禁用所有渲染按钮"""
        return not (context.scene.get('is_sequence_rendering') or context.scene.get('is_current_rendering'))

    def execute(self, context):
        """执行操作：收集所有标记了摄像机的帧，启动模态渲染"""
        scene = context.scene
        # 再次检查并发状态（防止通过快捷键绕过 poll）
        if scene.get('is_sequence_rendering') or scene.get('is_current_rendering'):
            self.report({'ERROR'}, "已有渲染任务在进行中，请等待完成")
            return {'CANCELLED'}
        self._frames_to_render = self.collect_frames_and_cameras(scene)
        if not self._frames_to_render:
            self.report({'ERROR'}, "没有找到需要渲染的帧")
            return {'CANCELLED'}

        scene.is_sequence_rendering = True  # 自定义标记，用于UI状态显示
        scene.tommy_active_render_task = "SEQUENCE"

        self._current_frame = 0
        self._is_rendering = False
        self._cancelled = False
        self._original_camera = None
        self._original_filepath = scene.render.filepath
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.scene.frame_set(self._frames_to_render[0]['frame'])
        self.report({'INFO'}, f"开始渲染，共 {len(self._frames_to_render)} 帧")
        return {'RUNNING_MODAL'}

    def collect_frames_and_cameras(self, scene):
        """
        遍历时间线标记，收集每个绑定了摄像机的帧。
        返回列表，每个元素为 {'frame': 帧号, 'camera': 摄像机对象}
        """
        frames = []
        marker_frames = {m.frame: m.camera for m in scene.timeline_markers if m.camera}
        for f in range(scene.frame_start, scene.frame_end + 1):
            if f in marker_frames:
                cam = marker_frames[f]
                frames.append({'frame': f, 'camera': cam})
        return frames

    def finish_render(self, context):
        """重写父类方法，额外重置序列渲染标记"""
        super().finish_render(context)
        context.scene.is_sequence_rendering = False
        context.scene.tommy_active_render_task = "NONE"


class RENDER_OT_RenderCurrentFrame(bpy.types.Operator, BaseRenderOperator):
    """仅渲染当前帧（前提是当前帧绑定了摄像机）"""
    bl_idname = "tommy.render_current_frames"
    bl_label = "渲染当前帧"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """仅当当前帧存在绑定了摄像机的标记，且无其他渲染任务在进行时可用"""
        return (any(m.frame == context.scene.frame_current and m.camera for m in context.scene.timeline_markers) and
                not (context.scene.get('is_sequence_rendering') or context.scene.get('is_current_rendering')))

    def execute(self, context):
        scene = context.scene
        # 检查并发
        if scene.get('is_sequence_rendering') or scene.get('is_current_rendering'):
            self.report({'ERROR'}, "已有渲染任务在进行中，请等待完成")
            return {'CANCELLED'}
        camera = next((m.camera for m in scene.timeline_markers if m.frame == scene.frame_current), None)
        if not camera:
            self.report({'WARNING'}, "当前帧未绑定摄像机")
            return {'CANCELLED'}

        scene.is_current_rendering = True
        scene.tommy_active_render_task = "SINGLE"

        self._frames_to_render = [{'frame': scene.frame_current, 'camera': camera}]
        self._current_frame = 0
        self._is_rendering = False
        self._cancelled = False
        self._original_camera = None
        self._original_filepath = scene.render.filepath
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.scene.frame_set(scene.frame_current)
        self.report({'INFO'}, f"开始渲染帧 {scene.frame_current}")
        return {'RUNNING_MODAL'}

    def finish_render(self, context):
        """重写父类方法，额外重置当前帧渲染标记"""
        super().finish_render(context)
        context.scene.is_current_rendering = False
        context.scene.tommy_active_render_task = "NONE"


class RENDER_OT_RenderCustomSequence(bpy.types.Operator, BaseRenderOperator):
    """根据输入的自定义帧序列进行间隔渲染"""
    bl_idname = "render.render_custom_sequence"
    bl_label = "间隔渲染"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        raw_input = scene.tommy_custom_render_frames

        # 1. 基础输入校验
        if not raw_input.strip():
            self.report({'ERROR'}, "请输入帧号（例如：2, 5, 13）")
            return {'CANCELLED'}

        try:
            # 解析字符串，保持用户输入的原始顺序
            target_frames = []
            for f in raw_input.split(','):
                f_stripped = f.strip()
                if f_stripped.isdigit():
                    target_frames.append(int(f_stripped))
                elif f_stripped:
                    self.report({'ERROR'}, f"无效的帧号输入: {f_stripped}。请检查间隔符是否为英文逗号😵")
                    return {'CANCELLED'}

            if not target_frames:
                self.report({'ERROR'}, "未检测到有效的帧号")
                return {'CANCELLED'}

            # 2. 合法性检查：渲染范围与摄像机绑定
            start, end = scene.frame_start, scene.frame_end
            marker_map = {m.frame: m.camera for m in scene.timeline_markers if m.camera}

            valid_render_queue = []
            for f in target_frames:
                # 检查是否在场景帧范围内
                if f < start or f > end:
                    self.report({'ERROR'}, f"帧 {f} 超出渲染范围 ({start}-{end})，请调整范围或序列")
                    return {'CANCELLED'}

                # 检查该帧是否有绑定的摄像机
                if f not in marker_map:
                    self.report({'ERROR'}, f"第 {f} 帧未绑定摄像机标记，无法开始渲染")
                    return {'CANCELLED'}

                # 关键修复：构建基类需要的字典格式 {'frame': int, 'camera': Object}
                valid_render_queue.append({
                    'frame': f,
                    'camera': marker_map[f]
                })

            # 3. 初始化渲染引擎状态
            # 设置状态位以禁用 UI 按钮，防止重复触发
            scene.is_sequence_rendering = True
            scene.tommy_active_render_task = "CUSTOM"

            self._frames_to_render = valid_render_queue
            self._current_frame = 0
            self._is_rendering = False
            self._cancelled = False

            # 保存原始场景状态以便渲染后恢复
            self._original_camera = scene.camera
            self._original_filepath = scene.render.filepath

            # 4. 启动 Modal 循环与计时器
            context.window_manager.modal_handler_add(self)
            self._timer = context.window_manager.event_timer_add(0.5, window=context.window)

            self.report({'INFO'}, f"开始间隔渲染: 共 {len(valid_render_queue)} 帧")
            return {'RUNNING_MODAL'}

        except Exception as e:
            # 异常保护：如果启动逻辑出错，确保重置 UI 状态
            scene.is_sequence_rendering = False
            scene.tommy_active_render_task = "NONE"
            self.report({'ERROR'}, f"渲染启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class RENDER_OT_CancelRenderSequence(bpy.types.Operator):
    """取消正在进行的序列渲染"""
    bl_idname = "tommy.cancel_render_sequence"
    bl_label = "取消渲染序列"

    def execute(self, context):
        if bpy.app.is_job_running('RENDER'):
            bpy.ops.render.render('INVOKE_DEFAULT', write_still=False)  # 发送取消信号
        self.report({'INFO'}, "正在取消序列渲染...")
        return {'FINISHED'}


class RENDER_OT_CancelRenderCurrentFrame(bpy.types.Operator):
    """取消正在进行的当前帧渲染"""
    bl_idname = "tommy.cancel_render_current_frame"
    bl_label = "取消渲染当前帧"

    def execute(self, context):
        if bpy.app.is_job_running('RENDER'):
            bpy.ops.render.render('INVOKE_DEFAULT', write_still=False)
        context.scene.is_current_rendering = False
        context.scene.tommy_active_render_task = "NONE"
        self.report({'INFO'}, "已取消当前帧渲染")
        return {'FINISHED'}


class RENDER_OT_PreviewMissingFrames(bpy.types.Operator):
    """跳转到缺失摄像机的帧（用于预览）"""
    bl_idname = "tommy.preview_missing_frames"
    bl_label = "跳转到缺失帧"
    frame: bpy.props.IntProperty(default=0)  # 要跳转到的帧号

    def execute(self, context):
        context.scene.frame_set(self.frame)
        self.report({'INFO'}, f"已跳转到帧 {self.frame}")
        return {'FINISHED'}


class RENDER_OT_PreviewOutputNames(bpy.types.Operator):
    """预览将会生成的文件名列表（不实际渲染）"""
    bl_idname = "tommy.preview_output_names"
    bl_label = "预览输出文件名"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        # 始终允许在渲染期间执行
        return True

    def execute(self, context):
        scene = context.scene
        scene.tommy_original_filepath_backup = scene.render.filepath

        # 首先检查是否有未绑定摄像机的帧
        missing_frames = self.check_missing_cameras(scene)

        if missing_frames:
            # 构建缺失帧的提示信息（最多显示前10帧）
            if len(missing_frames) > 10:
                missing_frames_str = ", ".join(map(str, missing_frames[:10])) + f", ... 共 {len(missing_frames)} 帧"
            else:
                missing_frames_str = ", ".join(map(str, missing_frames))

            self.report({'WARNING'}, f"无法预览: 帧 {missing_frames_str} 未绑定摄像机")
            return {'CANCELLED'}

        original_path = scene.render.filepath

        # 分解原始输出路径
        if original_path:
            directory = os.path.dirname(original_path)
            base_name = os.path.basename(original_path)

            # 移除自动编号模式（如 ####）
            base_name = re.sub(r'[#%]+(\d+d)?', '', base_name)

            # 移除扩展名
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]
        else:
            directory = ""
            base_name = ""

        # 收集帧和摄像机信息
        frames_info = []
        start_frame = scene.frame_start
        end_frame = scene.frame_end

        # 建立帧号到摄像机的映射（只考虑有摄像机的标记）
        marker_frames = {}
        for marker in scene.timeline_markers:
            if marker.camera:
                marker_frames[marker.frame] = marker.camera

        for frame in range(start_frame, end_frame + 1):
            if frame in marker_frames:
                camera = marker_frames[frame]
                safe_camera_name = camera.name

                # 生成文件名
                if base_name:
                    filename = f"{base_name}_{safe_camera_name}"
                else:
                    filename = safe_camera_name

                # 根据文件格式添加扩展名
                file_format = scene.render.image_settings.file_format
                extension = {
                    'PNG': '.png',
                    'JPEG': '.jpg',
                    'TIFF': '.tif',
                    'OPEN_EXR': '.exr',
                    'OPEN_EXR_MULTILAYER': '.exr',
                    'BMP': '.bmp',
                    'TARGA': '.tga',
                    'TARGA_RAW': '.tga',
                }.get(file_format, '.png')

                filename += extension
                frames_info.append((frame, filename))

        # 显示结果（最多显示前30个，避免信息过长）
        if frames_info:
            message = "将生成以下文件:\n"
            for frame, filename in frames_info[:30]:
                message += f"帧 {frame}: {filename}\n"

            if len(frames_info) > 30:
                message += f"... 共 {len(frames_info)} 个文件"

            self.report({'INFO'}, message)
        else:
            self.report({'WARNING'}, "没有找到绑定的摄像机")

        return {'FINISHED'}

    def check_missing_cameras(self, scene):
        """
        检查在场景帧范围内，哪些帧没有绑定摄像机的标记。
        返回缺失帧号的列表。
        """
        missing_frames = []
        start_frame = scene.frame_start
        end_frame = scene.frame_end

        marker_frames = {marker.frame: marker.camera for marker in scene.timeline_markers if marker.camera}

        for frame in range(start_frame, end_frame + 1):
            if frame not in marker_frames:
                missing_frames.append(frame)

        return missing_frames


class RENDER_OT_CheckDuplicateMarkers(bpy.types.Operator):
    bl_idname = "tommy.check_duplicate_markers"
    bl_label = "检查同名标记"
    bl_description = "检查时间轴上是否有多个标记使用了同一个摄像机（包含渲染范围外）"

    @classmethod
    def poll(cls, context):
        # 始终允许在渲染期间执行
        return True

    def execute(self, context):
        scene = context.scene
        # 建立 摄像机名称 -> [帧号列表] 的映射
        cam_map = {}

        for marker in scene.timeline_markers:
            if marker.camera:
                cam_name = marker.camera.name
                if cam_name not in cam_map:
                    cam_map[cam_name] = []
                cam_map[cam_name].append(marker.frame)

        # 筛选出重复的摄像机
        duplicates = []
        for cam_name, frames in cam_map.items():
            if len(frames) > 1:
                # 排序帧号并格式化文本
                frames_text = "、".join([f"第{f}帧" for f in sorted(frames)])
                duplicates.append(f"{frames_text} 为同一摄像机 ({cam_name})")

        # 定义弹出框显示逻辑  悬浮框
        def draw_popup(self, context):
            layout = self.layout
            if duplicates:
                for line in duplicates:
                    layout.label(text=line, icon='INFO')
            else:
                layout.label(text="时间轴上没有同名标记", icon='CHECKMARK')

        # 同步打印到 info
        if duplicates:
            report_msg = "检查结果: \n" + "\n".join(duplicates)
            self.report({'WARNING'}, report_msg)
        else:
            self.report({'INFO'}, "时间轴上没有同名标记")

        # 弹出菜单保持不变（用于快速查看多行内容）
        def draw_popup(self, context):
            layout = self.layout
            if duplicates:
                for line in duplicates:
                    layout.label(text=line, icon='INFO')
            else:
                layout.label(text="时间轴上没有同名标记", icon='CHECKMARK')

        # 触发多行提示框
        title = "检查结果" if duplicates else "提示"
        context.window_manager.popup_menu(draw_popup, title=title, icon='QUESTION')

        return {'FINISHED'}


# ====================== 新增：标记点排序操作符 ======================
class RENDER_OT_SortTimelineMarkers(bpy.types.Operator):
    """将所有时间轴标记按帧号从小到大重新排序（物理排序）"""
    bl_idname = "tommy.sort_timeline_markers"
    bl_label = "排序标记点"
    bl_description = "按帧号对标记点进行重新排序，解决列表显示混乱的问题"
    bl_options = {'REGISTER', 'UNDO'}



    def execute(self, context):
        scene = context.scene
        # 记录现有的标记信息
        marker_data = []
        for m in scene.timeline_markers:
            marker_data.append({
                'name': m.name,
                'frame': m.frame,
                'camera': m.camera
            })

        scene = bpy.context.scene
        marker_states = {m.name: m.select for m in scene.timeline_markers}

        # 按帧号排序
        marker_data.sort(key=lambda x: x['frame'])

        # 清除并重建标记（Blender 的底层集合顺序通常由创建顺序决定）
        scene.timeline_markers.clear()
        for data in marker_data:
            m = scene.timeline_markers.new(data['name'], frame=data['frame'])
            m.camera = data['camera']
        # 清除选中状态
        for marker in scene.timeline_markers:
            marker.select = marker_states.get(marker.name, False)

        self.report({'INFO'}, f"已对 {len(marker_data)} 个标记点重新排序")
        return {'FINISHED'}