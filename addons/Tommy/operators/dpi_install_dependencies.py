import bpy
import subprocess
import sys


class TOMMY_OT_install_pillow(bpy.types.Operator):
    """安装 Pillow 库（用于 DPI 元数据写入）"""
    bl_idname = "tommy.install_pillow"
    bl_label = "安装 Pillow"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        python_exe = sys.executable
        try:
            self.report({'INFO'}, "正在安装 Pillow，请稍候...")
            subprocess.run(
                [python_exe, "-m", "pip", "install", "pillow"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.report({'INFO'}, "✅ Pillow 安装成功！请重启 Blender 以激活。")
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"安装失败：{e.stderr}")
        return {'FINISHED'}


class TOMMY_OT_uninstall_pillow(bpy.types.Operator):
    """卸载 Pillow 库"""
    bl_idname = "tommy.uninstall_pillow"
    bl_label = "卸载 Pillow"
    bl_options = {'REGISTER', 'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        python_exe = sys.executable
        try:
            subprocess.run(
                [python_exe, "-m", "pip", "uninstall", "pillow", "-y"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.report({'INFO'}, "Pillow 已卸载。请重启 Blender 以完全生效。")
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"卸载失败：{e.stderr}")
        return {'FINISHED'}
