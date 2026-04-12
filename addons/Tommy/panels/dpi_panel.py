import bpy


class TOMMY_PT_dpi_tool(bpy.types.Panel):
    """DPI 工具：嵌套在属性面板 → 输出 → 格式 下"""
    bl_label = "DPI 工具"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_parent_id = "RENDER_PT_format"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── Pillow 检测 ──────────────────────────────────────────
        try:
            from PIL import Image
            pillow_ok = True
        except ImportError:
            pillow_ok = False

        if not pillow_ok:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Pillow 未安装，DPI 元数据写入不可用", icon='ERROR')
            col.label(text="前往  编辑 > 偏好设置 > 插件 > Tommy  完成安装")
            return

        layout.use_property_split = False

        # ── 实时换算物理尺寸 ─────────────────────────────────────
        dpi = max(scene.tommy_dpi, 1.0)
        px_x = scene.tommy_original_resolution[0]
        px_y = scene.tommy_original_resolution[1]
        width_mm  = (px_x / dpi) * 25.4
        height_mm = (px_y / dpi) * 25.4

        # ── 表头 ─────────────────────────────────────────────────
        split_header = layout.split(factor=0.55)
        split_header.label(text="像素尺寸")
        split_header.label(text="物理尺寸")

        # ── 宽度行 ───────────────────────────────────────────────
        split_w = layout.split(factor=0.55)
        split_w.prop(scene, "tommy_original_resolution", index=0, text="W")
        col_mm_w = split_w.column()
        col_mm_w.enabled = False
        col_mm_w.label(text=f"{width_mm:.1f} mm")

        # ── 高度行 ───────────────────────────────────────────────
        split_h = layout.split(factor=0.55)
        split_h.prop(scene, "tommy_original_resolution", index=1, text="H")
        col_mm_h = split_h.column()
        col_mm_h.enabled = False
        col_mm_h.label(text=f"{height_mm:.1f} mm")

        layout.separator(factor=0.8)

        # ── DPI 输入（居中）──────────────────────────────────────
        row_dpi = layout.row()
        row_dpi.alignment = 'CENTER'
        row_dpi.label(text="DPI")
        row_dpi.prop(scene, "tommy_dpi", text="")

        layout.separator(factor=0.5)

        # ── 确认写入按钮（蓝色常量，紧跟 DPI 下方）─────────────
        row_btn = layout.row()
        row_btn.scale_y = 1.3
        row_btn.operator(
            "tommy.apply_dpi_settings",
            text="确认写入渲染设置 + DPI 元数据",
            icon='CHECKMARK',
            depress=scene.tommy_dpi_confirmed,
            # depress=True,          # ← 蓝色常量激活状态
        )
