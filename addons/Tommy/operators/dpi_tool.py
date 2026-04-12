import bpy
import os
from bpy.app.handlers import persistent


# ── 属性变化回调（原来在 __init__.py 里，现在移到这里）────────────
def _update_dpi_calc(self, context):
    """DPI 或像素变化时触发重绘，并重置确认状态"""
    self.tommy_dpi_confirmed = False
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PROPERTIES':
                area.tag_redraw()


# ── Operator ─────────────────────────────────────────────────────
class TOMMY_OT_apply_dpi_settings(bpy.types.Operator):
    """切换 DPI 确认状态：激活时写入渲染设置，再次点击取消"""
    bl_idname = "tommy.apply_dpi_settings"
    bl_label = "确认写入渲染设置 + DPI 元数据"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.tommy_dpi_confirmed = not scene.tommy_dpi_confirmed

        if scene.tommy_dpi_confirmed:
            res = scene.tommy_original_resolution
            scene.render.resolution_x = res[0]
            scene.render.resolution_y = res[1]
            dpi = scene.tommy_dpi
            self.report(
                {'INFO'},
                f"✅ 已写入渲染设置：{res[0]}×{res[1]} px，"
                f"DPI={dpi:.0f}。渲染完成后将自动写入元数据。"
            )
        else:
            self.report({'INFO'}, "DPI 设置已取消确认。")

        return {'FINISHED'}


# ── 渲染完成 Handler（保持不变）─────────────────────────────────
@persistent
def dpi_render_complete_handler(scene):
    try:
        from PIL import Image
    except ImportError:
        print("Tommy DPI: Pillow 未安装，跳过 DPI 元数据写入。")
        return

    dpi_value = scene.tommy_dpi
    dpi_tuple = (int(dpi_value), int(dpi_value))
    output_path = bpy.path.abspath(scene.render.filepath)
    file_format = scene.render.image_settings.file_format
    ext_map = {'PNG': '.png', 'JPEG': '.jpg', 'TIFF': '.tif', 'BMP': '.bmp'}
    ext = ext_map.get(file_format)

    if ext is None:
        print(f"Tommy DPI: 不支持写入 DPI 的格式 {file_format}，已跳过。")
        return

    if not output_path.lower().endswith(ext):
        output_path += ext

    if not os.path.isfile(output_path):
        print(f"Tommy DPI: 输出文件不存在，已跳过：{output_path}")
        return

    try:
        img = Image.open(output_path)
        if file_format == 'PNG':
            img.save(output_path, dpi=dpi_tuple)
        elif file_format == 'JPEG':
            img.save(output_path, dpi=dpi_tuple, quality=95)
        elif file_format == 'TIFF':
            img.save(output_path, dpi=dpi_tuple)
        print(f"Tommy DPI: 已写入 DPI={dpi_value:.0f} → {output_path}")
    except Exception as e:
        print(f"Tommy DPI: 元数据写入失败：{e}")


# ── 模块自己的属性注册（auto_load 自动调用）──────────────────────
_dpi_props = {
    bpy.types.Scene: {
        "tommy_dpi": bpy.props.FloatProperty(
            name="DPI",
            default=300.0,
            min=1.0,
            soft_max=1200.0,
            update=_update_dpi_calc,
        ),
        "tommy_dpi_confirmed": bpy.props.BoolProperty(
            name="DPI 已确认",
            default=False,
        ),
    }
}


def register():
    # 注册 Operator 类（auto_load 已经处理，这里只处理属性）
    for owner_type, props in _dpi_props.items():
        for prop_name, prop_value in props.items():
            setattr(owner_type, prop_name, prop_value)

    # 注册渲染完成 Handler
    if dpi_render_complete_handler not in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.append(dpi_render_complete_handler)


def unregister():
    # 移除 Handler
    if dpi_render_complete_handler in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.remove(dpi_render_complete_handler)

    # 注销属性
    for owner_type, props in _dpi_props.items():
        for prop_name in props:
            if hasattr(owner_type, prop_name):
                delattr(owner_type, prop_name)
