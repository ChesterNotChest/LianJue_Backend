#!/usr/bin/python3
# pip install python-docx
# sudo apt-get install unoconv
# sudo ln -s /usr/lib/libreoffice/program/pyuno.so /usr/lib/
# ln -s /home/raini/.cache/modelscope/hub/models/cubeai/blip-image-captioning-base /media/raini/414bbabe-867c-4aae-b65f-f3a024550774/model/docling-models/cubeai--blip-image-captioning-base
import base64
import json
import random
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from typing import Dict, Any, List, Tuple, Optional
import os
import logging
import time
import pandoc
from docling_core.types.io import DocumentStream
import concurrent.futures

from openpyxl.drawing.image import PILImage

from knowlion.multi_model_litellm import LitellmMultiModel

# 强制重新配置日志
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# easyocr_model_path = dify_config.DOCUMENT_MODEL_PATH+"/easyocr"
# doc_to_md_model_path = dify_config.DOCUMENT_MODEL_PATH+"/doc2md"

def get_document_converter(easyocr_model_path, pdf_artifacts_path):
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import PdfFormatOption, DocumentConverter, ImageFormatOption, \
        PowerpointFormatOption, WordFormatOption, ExcelFormatOption, HTMLFormatOption

    # 配置 OCR 模型路径
    # easyocr_model_storage_directory = json_input["easyocrModelPath"]
    easyocr_options = EasyOcrOptions()
    easyocr_options.model_storage_directory = easyocr_model_path
    # # 配置 公式图片识别 模型路径
    # smolvlm_picture_description = PictureDescriptionVlmOptions(repo_id="cubeai/blip-image-captioning-base",prompt="解释图片内容") # ds4sd/SmolDocling-256M-preview "Salesforce/blip-image-captioning-base" cubeai/blip-image-captioning-base HuggingFaceTB/SmolVLM-256M-Instruct ibm-granite/granite-vision-3.1-2b-preview
    # 配置 Docling 模型路径
    # 公式图片识别：./model/docling-models/HuggingFaceTB--SmolVLM-256M-Instruct
    # pdf_artifacts_path = json_input["docToMdModelPath"]
    pdf_pipeline_options = PdfPipelineOptions(
        artifacts_path=pdf_artifacts_path)  # , generate_page_images=True, generate_picture_images=True
    pdf_pipeline_options.ocr_options = easyocr_options
    pdf_pipeline_options.do_ocr = True
    ## 识别公式内容（默认调用模型ds4sd--CodeFormula
    pdf_pipeline_options.do_formula_enrichment = True
    pdf_pipeline_options.do_code_enrichment = True
    pdf_pipeline_options.do_table_structure = True
    # 设置文档变为图片的保存选项
    pdf_pipeline_options.generate_page_images = True  # 获取表格图片，然后使用 TableItem.get_image 函数来实现
    pdf_pipeline_options.generate_picture_images = True
    IMAGE_RESOLUTION_SCALE = 5.0  # 图片分辨率缩放比例
    # 创建转换器实例
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.PPTX: PowerpointFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.DOCX: WordFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.XLSX: ExcelFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.HTML: HTMLFormatOption(pipeline_options=pdf_pipeline_options)
        }
    )
    return converter


def set_device_mode(device_gpu):
    if not device_gpu:
        import torch
        # DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        # torch.device('cpu')
        # 1. 禁用 CUDA 设备
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        # 2. 设置默认设备为 CPU（替代原 torch.set_default_tensor_type）
        torch.set_default_device('cpu')
        print(f"当前默认OCR模式: {torch.device('cpu')}")
        # 3. 设置默认数据类型（原 torch.FloatTensor 对应 torch.float32）
        torch.set_default_dtype(torch.float32)
        # print(f"当前默认数据类型: {torch.get_default_dtype()}")
        # 4. 禁用 DataLoader 的 pin_memory（防止 GPU 相关警告）
        #    - 直接修改 DataLoader 默认参数
        if hasattr(torch.utils.data.DataLoader, '__init__'):
            default_args = list(torch.utils.data.DataLoader.__init__.__defaults__)
            if len(default_args) >= 5:  # 检查是否包含 pin_memory 参数（位置索引 4）
                default_args[4] = False  # 将 pin_memory 默认值设为 False
                torch.utils.data.DataLoader.__init__.__defaults__ = tuple(default_args)
            # print("已禁用 DataLoader 的 pin_memory")


class Document2Markdown:
    def __init__(self, vl_model: LitellmMultiModel, model_path: str, device_gpu=False,
                 enable_image_caption=True, max_workers=10, max_retries=1):
        self.vl_model = vl_model
        self.model_path = model_path
        self.device_gpu = device_gpu
        self.original_filename = None

        # 新增控制参数
        self.enable_image_caption = enable_image_caption  # 是否启用图片解释功能
        self.max_workers = max_workers  # 最大并行数
        self.max_retries = max_retries  # 最大重试次数

    def doc_to_pdf(self, file_path: str) -> bytes:
        """将文档转换为PDF，中间过程使用临时目录，返回bytes类型文件"""
        self.original_filename = os.path.splitext(os.path.basename(file_path))[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            ext = file_path.lower().split('.')[-1]

            if ext in {'doc', 'docx'}:
                if ext == 'doc':
                    docx_path = os.path.join(temp_dir, f"temp.docx")
                    self._convert_doc_to_docx_libreoffice(file_path, docx_path)
                else:
                    docx_path = file_path

                pdf_path = os.path.join(temp_dir, f"temp.pdf")
                success = self._convert_docx_to_pdf_pandoc(docx_path, pdf_path)

                if not success:
                    logging.warning(f"DOCX转PDF失败，将使用原始文件: {file_path}")
                    with open(file_path, 'rb') as f:
                        return f.read()

                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                return pdf_bytes

            elif ext in {'pdf', 'xlsx', 'pptx', 'txt', 'png', 'jpg', 'jpeg', 'md'}:
                with open(file_path, 'rb') as f:
                    return f.read()
            else:
                raise ValueError(f"不支持的文件格式: {ext}")

    def save_pdf_file(self, pdf_bytes: bytes, save_dir: str):
        """保存PDF文件到指定目录"""
        if not self.original_filename:
            raise ValueError("未设置文件名，请先调用doc_to_pdf方法")

        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{self.original_filename}.pdf")

        with open(save_path, 'wb') as f:
            f.write(pdf_bytes)

        logging.info(f"PDF文件已保存到: {save_path}")

    def pdf_to_markdown(self, pdf_path_or_input: str | bytes) -> str:
        """将PDF转换为Markdown，支持图片上下文提取和并行处理"""
        set_device_mode(self.device_gpu)
        converter = get_document_converter(self.model_path + "/easyocr", self.model_path + "/doc2md")

        # 处理PDF输入
        if isinstance(pdf_path_or_input, bytes):
            doc_stream = DocumentStream(
                name=self.original_filename,
                stream=BytesIO(pdf_path_or_input)
            )
            result = converter.convert(doc_stream)
        else:
            result = converter.convert(pdf_path_or_input)

        # 第一阶段：收集所有文本和图片信息
        all_text_items = []
        image_tasks = []
        image_counter = 0

        # 遍历文档中的所有项目，收集文本和图片信息
        from docling_core.types.doc import TextItem, TableItem, PictureItem, CodeItem
        for item, level in result.document.iterate_items():
            if isinstance(item, TextItem):
                if "formula" in item.label:
                    text_content = f"Formulas::\n{item.text}\n::Formulas"
                elif "section_header" in item.label:
                    indent = "  " * (level - 1)
                    text_content = f"{indent}{'#' * level} {item.text}"
                elif "code" in item.label:
                    text_content = f"Code::\n{item.text}\n::Code"
                else:
                    text_content = item.text

                all_text_items.append(('text', text_content))

            elif isinstance(item, TableItem):
                table_df = item.export_to_dataframe()
                table_md = table_df.to_markdown()
                text_content = f"Table::\n{table_md}\n::Table"
                all_text_items.append(('text', text_content))

            elif isinstance(item, PictureItem):
                try:
                    # 获取图片元数据
                    prov = item.prov[0]  # 第一个来源信息
                    bbox = prov.bbox
                    page = prov.page_no
                    # 动态获取页面尺寸（基于实际图像数据）
                    page_obj = result.document.pages[page]
                    pil_image = page_obj.image.pil_image
                    page_width, page_height = pil_image.size
                    # 边界框坐标转换（假设坐标系原点在左下角）
                    t = bbox.t  # 顶部坐标
                    l = bbox.l  # 左侧坐标
                    r = bbox.r  # 右侧坐标
                    b = bbox.b  # 底部坐标
                    # 四向Logo过滤条件（单位：磅，根据实际文档调整阈值）
                    is_edge_logo = (
                        # 顶部Logo（距页面上边缘 < 120磅）
                            (t < 80) or
                            # 底部Logo（距页面下边缘 < 120磅）
                            ((page_height - b) < 80) or
                            # 左侧Logo（距左边缘 < 150磅）
                            (l < 90) or
                            # 右侧Logo（距右边缘 < 150磅）
                            ((page_width - r) < 90)
                    )
                    # 小尺寸图片过滤（面积 < 1000平方磅）
                    is_small = (r - l) * (t - b) < 1000
                    # 组合过滤条件
                    if is_edge_logo or is_small:
                        logging.info(f"过滤边缘Logo/小图标：页{page} | 坐标({l:.0f},{t:.0f})-{r:.0f},{b:.0f}")
                        continue

                    # 获取有效图片数据
                    image_data:Optional[PILImage.Image] = item.get_image(result.document)
                    if image_data:
                        image_counter += 1

                        # 创建图片任务
                        placeholder = f"IMAGE_PLACEHOLDER_{image_counter}"
                        image_task = {
                            'placeholder': placeholder,
                            'image_data': image_data,
                            'position': len(all_text_items),  # 记录图片在文本中的位置
                            'page': page,
                            'coordinates': (l, t, r, b)
                        }
                        image_tasks.append(image_task)

                        # 添加占位符到文本列表
                        all_text_items.append(('image', placeholder))
                        logging.info(f"添加图片占位符：{placeholder}，位置：{len(all_text_items) - 1}")

                except Exception as e:
                    logging.info(f"处理图片异常：{str(e)}")
                    continue

            elif isinstance(item, CodeItem):
                text_content = f"Code::\n{item.text}\n::Code"
                all_text_items.append(('text', text_content))

            else:
                logging.info(f"Unhandled item type: {type(item)} {item.text}")

        # 构建初始Markdown（包含占位符）
        initial_md_parts = []
        for item_type, content in all_text_items:
            initial_md_parts.append(content)
        initial_md = "\n\n".join(initial_md_parts)

        # 第二阶段：如果有图片且启用了图片解释功能，则并行处理图片
        if self.enable_image_caption and image_tasks:
            logging.info(f"开始并行处理 {len(image_tasks)} 张图片，最大并行数：{self.max_workers}")

            # 为每个图片任务添加上下文信息
            image_tasks_with_context = self._add_image_context(image_tasks, all_text_items)

            # 并行处理图片
            processed_images = self._process_images_parallel(image_tasks_with_context)

            # 替换占位符
            final_md = initial_md
            for placeholder, description in processed_images.items():
                final_md = final_md.replace(placeholder, f"Image::\n{description}\n::Image")

            return final_md
        else:
            # 如果不启用图片解释，移除所有图片占位符
            if not self.enable_image_caption:
                for task in image_tasks:
                    initial_md = initial_md.replace(task['placeholder'], "[图片]")
            return initial_md

    def _add_image_context(self, image_tasks: List[Dict], all_text_items: List[Tuple]) -> List[Dict]:
        """为图片添加上下文信息"""
        context_size = 200  # 前后各200个字符

        for task in image_tasks:
            position = task['position']

            # 获取前文（图片位置之前的内容）
            pre_context = ""
            pre_start = max(0, position - 5)  # 最多向前看5个元素
            for i in range(pre_start, position):
                if all_text_items[i][0] == 'text':
                    pre_context += all_text_items[i][1] + "\n\n"

            # 获取后文（图片位置之后的内容）
            post_context = ""
            post_end = min(len(all_text_items), position + 6)  # 最多向后看5个元素
            for i in range(position + 1, post_end):
                if all_text_items[i][0] == 'text':
                    post_context += all_text_items[i][1] + "\n\n"

            # 截取固定大小的上下文
            pre_context = pre_context[-context_size:] if len(pre_context) > context_size else pre_context
            post_context = post_context[:context_size] if len(post_context) > context_size else post_context

            task['context'] = f"前文：{pre_context}\n\n后文：{post_context}"
            task['page_info'] = f"文档第{task['page']}页"

        return image_tasks

    def _process_images_parallel(self, image_tasks: List[Dict]) -> Dict[str, str]:
        """并行处理图片"""
        processed_results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_placeholder = {
                executor.submit(self._process_single_image, task): task['placeholder']
                for task in image_tasks
            }

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_placeholder):
                placeholder = future_to_placeholder[future]
                try:
                    description = future.result()
                    processed_results[placeholder] = description
                    logging.info(f"成功处理图片：{placeholder}")
                except Exception as e:
                    logging.error(f"处理图片 {placeholder} 失败: {e}")
                    processed_results[placeholder] = "图片内容处理失败"

        return processed_results

    def _process_single_image(self, image_task: Dict) -> str:
        """处理单张图片，包含重试机制"""
        # placeholder = image_task['placeholder']
        image_data = image_task['image_data']
        context = image_task['context']
        page_info = image_task['page_info']

        full_context = f"{page_info}\n{context}"

        for attempt in range(self.max_retries + 1):
            try:
                # 将PIL Image转换为bytes格式
                buffered = BytesIO()
                image_data.save(buffered, format="PNG")
                image_bytes = buffered.getvalue()

                system_prompt = """请详细描述图片内容，识别其中的关键信息，并生成适合知识图谱构建的结构化信息。"""
                user_prompt = f"""
                    图片上下文：{full_context}
                    请生成包含以下内容的JSON格式结果：
                    - 图片的详细描述
                    - 识别出的关键实体和关系
                """

                result = self.vl_model.call_image_model(system_prompt + user_prompt, image_bytes)
                return result

            except Exception as e:
                logging.warning(f"图片处理尝试 {attempt + 1} 失败: {e}")
                if attempt < self.max_retries:
                    time.sleep(1)  # 重试前等待1秒
                else:
                    raise Exception(f"图片处理失败，已重试{self.max_retries}次")

    def _convert_doc_to_docx_libreoffice(self, input_path: str, output_docx: str):
        """使用LibreOffice将DOC转换为DOCX"""
        cmd = [
            'libreoffice',
            '--headless',
            '--convert-to',
            'docx',
            '--outdir',
            os.path.dirname(output_docx),
            input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"DOC转DOCX失败: {result.stderr}")

        expected_output = os.path.join(
            os.path.dirname(output_docx),
            os.path.splitext(os.path.basename(input_path))[0] + '.docx'
        )

        if os.path.exists(expected_output):
            shutil.move(expected_output, output_docx)
        else:
            raise RuntimeError(f"转换输出文件不存在: {expected_output}")

        logging.info(f"文件已转换为docx: {output_docx}")

    def _convert_docx_to_pdf_pandoc(self, input_path: str, output_pdf: str) -> bool:
        """使用纯Python的pandoc库实现DOCX转PDF"""
        try:
            with open(input_path, 'rb') as f:
                docx_bytes = f.read()

            doc = pandoc.read(source=docx_bytes, format='docx')

            options = [
                '--pdf-engine=weasyprint',
                '-V', 'CJKmainfont=SimHei',
                '--extract-media=/tmp/pandoc'
            ]

            pdf_bytes = pandoc.write(
                doc,
                format='pdf',
                options=options
            )

            with open(output_pdf, 'wb') as f:
                f.write(pdf_bytes)

            return True

        except Exception as e:
            logging.error(f"转换失败: {input_path} to pdf {str(e)}")
            return False



def convert_to_pdf(input_path):
    """
    先将DOC转换为DOCX, 再使用pandoc将DOCX文档转换为PDF - 在同级目录输出.pdf文件
    :param input_path: 输入文件路径
    :param output_dir: 输出目录，默认为输入文件所在目录
    :return: 转换后的PDF文件路径
    """

    pdf_file_path = input_path

    if input_path.lower().endswith('.doc'):
        # 根据文件扩展名构建输出文件路径
        output_docx = convert_doc_to_docx_libreoffice(input_path)
    else:
        output_docx = input_path

    if output_docx.lower().endswith('.docx'):
        # 根据文件扩展名构建输出文件路径
        output_pdf = output_docx.replace('.docx', '.pdf')
        result = convert_docx_to_pdf_pandoc(output_docx, output_pdf)
        # 验证输出文件是否存在
        if not result:
            logging.info(f"转换失败: 将使用DOCX文件作为识别文件！")
            pdf_file_path = output_docx
        else:
            pdf_file_path = output_pdf

    return pdf_file_path


def convert_docx_to_pdf_pandoc(input_path: str, output_pdf: str) -> bool:
    """
    使用纯Python的pandoc库实现DOCX转PDF
    :param input_path: 输入DOCX文件路径
    :param output_pdf: 输出PDF路径
    :return: 是否转换成功
    """
    try:
        # 1. 读取DOCX文件
        with open(input_path, 'rb') as f:
            docx_bytes = f.read()

        # 2. 转换为Pandoc内部表示
        doc = pandoc.read(source=docx_bytes, format='docx')

        # 3. 配置PDF选项（模拟命令行参数）
        options = [
            '--pdf-engine=weasyprint',
            '-V', 'CJKmainfont=SimHei',
            '--extract-media=/tmp/pandoc'
        ]

        # 4. 写入PDF
        pdf_bytes = pandoc.write(
            doc,
            format='pdf',
            options=options
        )

        # 5. 保存PDF文件
        with open(output_pdf, 'wb') as f:
            f.write(pdf_bytes)

        return True

    except Exception as e:
        logging.error(f"转换失败: {input_path} to pdf {str(e)}")
        return False


def convert_doc_to_docx_libreoffice(input_path):
    """
    使用LibreOffice将文档转换为PDF
    :param input_path: 输入文件路径
    :param output_dir: 输出目录，默认为输入文件所在目录
    :return: 转换后的PDF文件路径
    """
    output_docx = input_path.lower().replace('.doc', '.docx')
    # 执行LibreOffice转换命令
    cmd = [
        'libreoffice',
        '--headless',
        '--convert-to',
        'docx',
        '--outdir',
        str(output_docx),
        str(input_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"DOC转DOCX失败: {result.stderr}")
    logging.info("文件已转换为docx：" + str(output_docx))

    return output_docx


def convert_docx_to_pdf_libreoffice(input_path, output_dir=None):
    """
    使用LibreOffice将文档转换为PDF
    :param input_path: 输入文件路径
    :param output_dir: 输出目录，默认为输入文件所在目录
    :return: 转换后的PDF文件路径
    """
    if output_dir is None:
        output_dir = input_path.parent

    # 构建输出文件路径
    output_pdf = output_dir / f"{input_path.stem}.pdf"

    # 执行LibreOffice转换命令
    cmd = [
        'libreoffice',
        '--headless',
        '--convert-to',
        'pdf',
        '--outdir',
        str(output_dir),
        str(input_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"转换失败: {result.stderr}")

    return output_pdf


if __name__ == "__main__":
    file_path = "/home/raini/Downloads/pdfs/pdf/基于液态天然气冷能利用的液...空气储能系统优化与性能评估_李俊先.pdf"
    file_path = "/home/raini/Downloads/pdfs/test1.pdf"
    model_path = "/thutmose/app/abution/model"

    MODEL_CONFIGS = {
        # 文本模型（仅处理文字对话）
        "text": {
            "model_name": "openai/qwen-max",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        },
        # 多模态模型（处理文本+图片）
        "image": {
            "model_name": "openai/qwen-vl-plus",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        },
        # 向量模型（生成文本嵌入向量）
        "embed": {
            "model_name": "openai/text-embedding-v4",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-09a9980300ad40e0978eefe0f3bbb4f2"
        }
    }

    model_instance = LitellmMultiModel(MODEL_CONFIGS)

    # 创建实例，启用图片解释，设置最大并行数为5，最大重试次数为1
    parser = Document2Markdown(
        vl_model=model_instance,
        model_path=model_path,
        device_gpu=False,
        enable_image_caption=True,
        max_workers=5,
        max_retries=1
    )

    # 1. 将文档转换为PDF bytes
    pdf_bytes = parser.doc_to_pdf(file_path)
    print(f"转换后的PDF大小: {len(pdf_bytes)} bytes")

    # # 2. 保存PDF文件（可选）
    # save_dir = "./test"
    # parser.save_pdf_file(pdf_bytes, save_dir)

    # 3. 将PDF转换为Markdown
    md_content = parser.pdf_to_markdown(pdf_bytes)
    print(md_content)