# =============================
#  Document2Markdown 流程总览
#  (knowlion/doc_parsing_markdown.py)
# =============================

## ☆ 顶层流程
1) 初始化与配置
   - 设定 `DOCLING_ARTIFACTS_PATH=/thutmose/app/abution/model`
   - `get_document_converter()` 创建 Docling 转换器：
     - `do_ocr=True`（EasyOCR 路径=model_path）
     - `do_formula_enrichment=False`
     - `do_code_enrichment=True`
     - `do_table_structure=True`
     - 生成页面/图片快照
   - `set_device_mode(device_gpu=False)` 强制 CPU，隐藏 CUDA，并关闭 pin_memory

2) 输入归一化 (`doc_to_pdf`)
   - 支持 `pdf/doc/docx/pptx/xlsx/txt/png/jpg/jpeg/md`
   - `doc` → LibreOffice 转 `docx`; `docx` → pandoc 转 PDF（weasyprint+SimHei）
   - 其他格式直接读二进制；记录 `original_filename` 供输出命名

3) PDF→Markdown (`pdf_to_markdown`)
   - 记录时间与内存（psutil）
   - 按字节流或路径喂入 Docling 转换
   - 遍历 Docling items（Text/Table/Picture/Code）：
     - Text：普通文本；公式包裹 `Formulas::...::Formulas`；标题转 `#`；代码包裹 `Code::...::Code`
     - Table：`export_to_dataframe()` → `to_markdown()` → `Table::...::Table`
     - Picture：过滤边缘 Logo（上下<80pt，左右<90pt）与面积<1000的小图；其余挂占位符 `IMAGE_PLACEHOLDER_n` 排队处理
   - 输出统计：文本/标题/表格/图片/代码/公式数量、过滤图片数、耗时、内存

4) 图片描述（可选）
   - 若开启 `enable_image_caption` 且存在图片任务：
     - 抽取前后各最多5段文本（各200字符）作为上下文
     - `_process_images_parallel` 用线程池并发、带重试
     - 调用 `vl_model.call_image_model`，占位符替换为 `Image::...::Image`
   - 若关闭图片解释，占位符改为 `[图片]`

5) 输出与保存
   - 拼接为 Markdown 字符串
   - 记录总耗时、长度、内存增量
   - `__main__` 中写入 `../markdowns/{original_filename}.md`，打印前 500 字符预览

## ☆ 关键默认值
- OCR：开启（EasyOCR）
- 公式增强：关闭；代码增强/表格结构：开启
- 图片过滤：四边 Logo / 面积<1000 直接丢弃
- 并发：图片描述用线程池，类默认 10 线程；示例中设 5 线程，重试 1 次
- 设备：CPU-only，`CUDA_VISIBLE_DEVICES=''`

## ☆ 已知提示
- Docling 警告：`TableItem.export_to_dataframe()` 未传 `doc` 参数已弃用
- 若 PDF 使用自定义 CMap/字体且无 ToUnicode，开启 OCR 仍可能出乱码；可切换关闭/启用 OCR 以对比效果
