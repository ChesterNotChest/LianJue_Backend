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
import gc
import psutil
import re
from typing import Union


try:
    from PIL import Image
except Exception:
    Image = None

from openpyxl.drawing.image import PILImage

from knowlion.multi_model_litellm import LitellmMultiModel
from config import get_config
try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    PdfReader = None
    PdfWriter = None

os.environ['DOCLING_ARTIFACTS_PATH'] = "/thutmose/app/abution/model"

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
    pdf_pipeline_options.do_ocr = True  # 启用 OCR
    ## 识别公式内容（默认调用模型ds4sd--CodeFormula
    pdf_pipeline_options.do_formula_enrichment = True
    pdf_pipeline_options.do_code_enrichment = True
    pdf_pipeline_options.do_table_structure = True
    # 设置文档变为图片的保存选项
    pdf_pipeline_options.generate_page_images = True  # 获取表格图片，然后使用 TableItem.get_image 函数来实现
    pdf_pipeline_options.generate_picture_images = True
    try:
        pdf_pipeline_options.batch_size = 2
    except Exception:
        pass
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
    import torch
    if device_gpu:
        try:
            if getattr(torch, 'cuda', None) is not None and torch.cuda.is_available():
                try:
                    torch.set_default_device('cuda')
                except Exception:
                    pass
                print(f"当前默认OCR模式: {torch.device('cuda')}")
            else:
                # GPU 不可用，回退到 CPU
                try:
                    torch.set_default_device('cpu')
                except Exception:
                    pass
                print("当前默认OCR模式: cpu（GPU 不可用）")
        except Exception:
            print("尝试启用 GPU 失败，使用 CPU")
            try:
                torch.set_default_device('cpu')
            except Exception:
                pass
    else:
        # 禁用 CUDA 设备并强制使用 CPU
        try:
            os.environ['CUDA_VISIBLE_DEVICES'] = ''
        except Exception:
            pass
        try:
            torch.set_default_device('cpu')
            print(f"当前默认OCR模式: {torch.device('cpu')}")
        except Exception:
            print("当前默认OCR模式: cpu")
        # 设置默认数据类型（原 torch.FloatTensor 对应 torch.float32）
        try:
            torch.set_default_dtype(torch.float32)
        except Exception:
            pass
        # 禁用 DataLoader 的 pin_memory（防止 GPU 相关警告）
        try:
            if hasattr(torch.utils.data.DataLoader, '__init__'):
                default_args = list(torch.utils.data.DataLoader.__init__.__defaults__)
                if len(default_args) >= 5:
                    default_args[4] = False
                    torch.utils.data.DataLoader.__init__.__defaults__ = tuple(default_args)
        except Exception:
            pass


class Document2Markdown:
    def __init__(self, vl_model: LitellmMultiModel, model_path: str, device_gpu=False,
                 enable_image_caption=True, max_workers=10, max_retries=3):
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

    def pdf_to_markdown(self, pdf_path_or_input: str | bytes, job_id: str = None, process_index: int = 0) -> tuple:
        """将PDF转换为Markdown，支持图片上下文提取和并行处理"""
        # 📊 记录开始时间和内存
        start_time = time.time()
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        logging.info(f"🚀 开始 PDF->Markdown 转换，初始内存: {start_memory:.2f} MB")
        
        set_device_mode(self.device_gpu)
        converter = get_document_converter(self.model_path, self.model_path)
        print(f"当前OCR模型路径: {self.model_path}")
        print(f"当前Doc2MD模型路径: {self.model_path}")

        # 处理PDF输入
        step_start = time.time()
        input_type = type(pdf_path_or_input).__name__

        # 支持按页拆分的批处理（可在 config.PROCESSING_CONFIG.pages_per_batch 中配置）
        proc_cfg = get_config().get("PROCESSING_CONFIG", {})
        pages_per_batch = int(proc_cfg.get("pages_per_batch", 0) or 0)
        overlap = int(proc_cfg.get("page_context_window", 1) or 1)

        # 如果启用了按页分批，我们要避免对整个文档进行一次性 heavy convert；
        # 后续会在分批循环中对每个批次单独调用 converter.convert()
        try:
            if pages_per_batch > 0:
                logging.info(f"🔎 输入类型: {input_type}，启用按页分批 (pages_per_batch={pages_per_batch})，跳过全文转换")
                result = None
            else:
                if isinstance(pdf_path_or_input, bytes):
                    logging.info(f"🔎 输入类型: {input_type} (bytes)，大小: {len(pdf_path_or_input)} bytes，名称: {self.original_filename}")
                    doc_stream = DocumentStream(
                        name=self.original_filename or "unnamed_input",
                        stream=BytesIO(pdf_path_or_input)
                    )
                    result = converter.convert(doc_stream)
                else:
                    exists = isinstance(pdf_path_or_input, str) and os.path.exists(pdf_path_or_input)
                    size_info = None
                    if exists:
                        try:
                            size_info = os.path.getsize(pdf_path_or_input)
                        except Exception:
                            size_info = None
                    logging.info(
                        f"🔎 输入类型: {input_type} (path)，存在: {exists}" +
                        (f", 大小: {size_info} bytes" if size_info is not None else "")
                    )
                    try:
                        result = converter.convert(pdf_path_or_input)
                    finally:
                        # converter may hold native/pdfium resources; prefer explicit cleanup if available
                        pass
        except Exception as e:
            logging.error(f"❌ Docling 转换阶段异常（输入类型: {input_type}）: {e}")
            raise
        
        convert_time = time.time() - step_start
        current_memory = process.memory_info().rss / 1024 / 1024
        logging.info(f"⏱️ Docling 转换耗时: {convert_time:.2f}s，当前内存: {current_memory:.2f} MB (+{current_memory - start_memory:.2f} MB)")
        try:
            page_count = len(result.document.pages)
            logging.info(f"📄 转换后文档页数: {page_count}")
        except Exception:
            logging.debug("📄 无法获取页数信息")

        # 支持按页拆分的批处理（可在 config.PROCESSING_CONFIG.pages_per_batch 中配置）
        proc_cfg = get_config().get("PROCESSING_CONFIG", {})
        pages_per_batch = int(proc_cfg.get("pages_per_batch", 0) or 0)
        overlap = int(proc_cfg.get("page_context_window", 1) or 1)

        # _render_result_to_markdown moved to instance method so it is available
        # to other helpers (e.g., poor-quality retry handler).

        # 如果启用了按页分批
        if pages_per_batch > 0:
            # 获取原始 bytes
            if isinstance(pdf_path_or_input, bytes):
                pdf_bytes = pdf_path_or_input
            else:
                try:
                    with open(pdf_path_or_input, 'rb') as f:
                        pdf_bytes = f.read()
                except Exception:
                    # 回退：使用已经转换的 result（单次处理）
                    final_md, _ = self._render_result_to_markdown(result, getattr(self, '_image_counter', 0))
                    return final_md, [], 1

            batches = self.split_pdf_batches(pdf_bytes, pages_per_batch, overlap=overlap)
            total_batches = len(batches)
            fragments = []
            image_counter_global = getattr(self, '_image_counter', 0)
            device_mode = str(proc_cfg.get('device_mode', 'cpu')).lower()
            # write partial markdown to disk after every batch
            partial_dir = None
            partial_file = None

            start_idx = int(process_index or 0)
            for bidx in range(start_idx, total_batches):
                batch_bytes = batches[bidx]
                logging.info(f"📦 处理批次 {bidx+1}/{len(batches)}，大小: {len(batch_bytes)} bytes")
                # 创建 per-batch converter（确保内部状态不会在多个批次间累积）
                try:
                    converter = get_document_converter(self.model_path, self.model_path)
                except Exception as e:
                    logging.error(f"初始化 converter 失败: {e}")
                    converter = None

                doc_stream = DocumentStream(name=self.original_filename or f"batch_{bidx}", stream=BytesIO(batch_bytes))
                try:
                    if converter is None:
                        raise RuntimeError("converter 未能初始化")
                    res = converter.convert(doc_stream)
                except Exception as e:
                    logging.error(f"批次转换失败: {e}")
                    # ensure converter/result cleanup if possible then continue
                    try:
                        if 'res' in locals():
                            try:
                                if hasattr(res, 'document') and hasattr(res.document, 'close'):
                                    res.document.close()
                            except Exception:
                                pass
                            try:
                                del res
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        if converter is not None and hasattr(converter, 'close'):
                            try:
                                converter.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        del converter
                    except Exception:
                        pass
                    gc.collect()
                    if device_mode in ("cuda", "gpu"):
                        try:
                            import torch
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                    continue

                # 评估文本质量（字符数、页数、CJK比例等），决定是否启用回退策略
                try:
                    stats = self._assess_result_text_quality(res)
                except Exception:
                    stats = { 'chars': 0, 'pages': 0, 'cjk_ratio': 0.0 }

                poor_quality = False
                chars = int(stats.get('chars', 0) or 0)
                pages = int(stats.get('pages', 0) or 0)
                cjk_ratio = float(stats.get('cjk_ratio', 0.0) or 0.0)

                # Very small amount of text -> poor
                if chars < 200:
                    poor_quality = True

                # If CJK ratio is very low on a multi-page doc, it may be an English PDF.
                # Before treating as poor, check whether the result contains substantial
                # English/Latin text; if so, do NOT mark as poor.
                if pages > 0 and cjk_ratio < 0.1:
                    try:
                        is_english = self._contains_english_text(res)
                    except Exception:
                        is_english = False
                    if not is_english:
                        poor_quality = True

                if poor_quality:
                    logging.warning(f"检测到低质量提取（chars={stats.get('chars')} cjk_ratio={stats.get('cjk_ratio')})，使用回退策略（full-page OCR）。")
                    try:
                        frag, image_counter_global = self._handle_poor_quality_batch(batch_bytes, bidx, image_counter_global, device_mode)
                    except Exception as e:
                        logging.debug(f"回退策略处理失败: {e}")
                        frag = ""
                else:
                    frag, image_counter_global = self._render_result_to_markdown(res, image_counter_global)
                # 片段去重/规范化：避免写入与上一个或已存在 partial 完全重复的片段
                def _normalize_fragment(s: str) -> str:
                    try:
                        s2 = re.sub(r"[\s\u00A0]+", " ", s or "").strip()
                        return s2
                    except Exception:
                        return (s or "").strip()

                write_fragment = True
                try:
                    norm_frag = _normalize_fragment(frag)
                    # 与前一片段比较
                    if fragments:
                        last_norm = _normalize_fragment(fragments[-1])
                        if last_norm and norm_frag and last_norm == norm_frag:
                            logging.warning("跳过写入：与上一个已缓存片段完全重复")
                            write_fragment = False
                    # 与已存在 partial 文件中比较（避免 resume 时重复）
                    if write_fragment and partial_file is not None and partial_file.exists():
                        try:
                            existing_text = partial_file.read_text(encoding='utf-8')
                            if norm_frag and re.search(re.escape(norm_frag), re.sub(r"[\s\u00A0]+", " ", existing_text)):
                                logging.warning("跳过写入：片段已存在于 partial 文件中（resume 重复）")
                                write_fragment = False
                        except Exception:
                            pass
                except Exception:
                    write_fragment = True

                if write_fragment:
                    fragments.append(frag)

                # write partial markdown to disk after each batch to ensure per-batch persistence
                batch_completed = False
                try:
                    from pathlib import Path

                    # 保存至项目的 markdowns 目录
                    if partial_dir is None:
                        partial_dir = Path("./markdowns")
                        partial_dir.mkdir(parents=True, exist_ok=True)
                        if job_id:
                            partial_file = partial_dir / f"{job_id}_partial.md"
                        else:
                            partial_file = partial_dir / f"{self.original_filename}_partial.md"

                    # If the partial file already exists (resuming), do NOT try to
                    # guess how many fragments were written; simply append to EOF.
                    try:
                        if partial_file.exists():
                            write_mode = 'a'
                            logger.info(f"恢复检测: 部分文件已存在，使用 append 模式追加到 EOF。")
                        else:
                            write_mode = 'w'
                    except Exception:
                        write_mode = 'w'

                    # sanitize fragment a little (remove embedded control chars, collapse many blank lines)
                    try:
                        frag = re.sub(r'[\x00-\x08\x0b-\x1f]', '', frag)
                        frag = re.sub(r'\n{3,}', '\n\n', frag)
                    except Exception:
                        pass

                    # Always append to EOF to avoid accidental overwrite by mismatched start_idx.
                    try:
                        if partial_file is not None:
                            write_mode = 'a'
                        else:
                            write_mode = 'w'
                    except Exception:
                        write_mode = 'a'

                    # Filter out tiny / noise fragments (e.g., isolated symbols or single words like 'user')
                    frag_preview = frag.strip()
                    is_cjk = bool(re.search(r'[\u4e00-\u9fff]', frag_preview))
                    has_long_word = bool(re.search(r'[A-Za-z0-9]{3,}', frag_preview))
                    if not frag_preview:
                        logger.debug("跳过写入：片段为空")
                        write_skipped = True
                    elif len(frag_preview) < 12 and not is_cjk and not has_long_word:
                        logger.warning(f"跳过写入疑似噪声片段: {repr(frag_preview)}")
                        write_skipped = True
                    else:
                        write_skipped = False

                    logger.info(f"💾 写出部分 Markdown 到: {partial_file} (mode={write_mode}, start_idx={start_idx}, skipped={write_skipped})")
                    if not write_skipped:
                        # log a short debug representation of the fragment
                        try:
                            logger.debug(f"片段预览: {repr(frag_preview[:200])}")
                        except Exception:
                            pass
                        # When appending, only write a separator if the file already contains data
                        need_sep = False
                        try:
                            if write_mode == 'a' and partial_file is not None and os.path.exists(str(partial_file)):
                                try:
                                    if os.path.getsize(str(partial_file)) > 0:
                                        need_sep = True
                                except Exception:
                                    need_sep = True
                        except Exception:
                            need_sep = False

                        with open(partial_file, write_mode, encoding='utf-8') as pf:
                            if need_sep:
                                pf.write("\n\n")
                            pf.write(frag)
                    else:
                        # still update DB partial path so resume logic remains consistent
                        logger.debug("已跳过写入噪声片段，但保留 partial 路径和进度")

                    # 如果提供了 job_id，则更新任务数据库中的 partial 路径
                    if job_id:
                        try:
                            from repositories.jobs_repo import update_partial_md_path
                            update_partial_md_path(job_id, str(partial_file))
                        except Exception:
                            logging.debug("无法更新 jobs_repo 中的 partial 路径或进度（非致命）")

                    # free memory: do not clear fragments here to keep cumulative context in partial
                    gc.collect()
                    # mark batch as successfully processed (fragment generated and partial handling attempted)
                    batch_completed = True

                    # 尝试清空 GPU 缓存（若处于 GPU 模式）
                    if device_mode in ("cuda", "gpu"):
                        try:
                            import torch
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                except Exception as e:
                    logging.warning(f"写出部分 Markdown 失败: {e}")

                # 仅当批次已完全处理（包括生成片段与尝试写入 partial）后才更新 progress_index
                if job_id and batch_completed:
                    try:
                        from repositories.jobs_repo import update_job_progress
                        update_job_progress(job_id, bidx + 1)
                    except Exception:
                        logging.debug("无法更新 jobs_repo 中的 progress_index（非致命）")

                # 确保释放 per-batch converter 及中间结果以释放内存
                try:
                    if 'res' in locals():
                        try:
                            if hasattr(res, 'document') and hasattr(res.document, 'close'):
                                res.document.close()
                        except Exception:
                            pass
                        try:
                            del res
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if converter is not None and hasattr(converter, 'close'):
                        try:
                            converter.close()
                        except Exception:
                            pass
                    try:
                        del converter
                    except Exception:
                        pass
                except Exception:
                    pass
                gc.collect()
                if device_mode in ("cuda", "gpu"):
                    try:
                        import torch
                        torch.cuda.empty_cache()
                    except Exception:
                        pass

            # 更新实例计数器
            self._image_counter = image_counter_global
            final = "\n\n".join(fragments)
            # partial_file 可能为 Path 对象或 None
            partial_files = [str(partial_file)] if partial_file is not None else []

            # 最终对齐进度到 total_batches，外层可直接用 progress_index >= total_batches 判断终止
            if job_id:
                try:
                    from repositories.jobs_repo import update_job_progress
                    update_job_progress(job_id, total_batches)
                except Exception:
                    logging.debug("无法在收尾阶段更新 progress_index（非致命）")

            return final, partial_files, total_batches

        # 否则按单次结果渲染（原有行为）
        final_md, _ = self._render_result_to_markdown(result, getattr(self, '_image_counter', 0))
        try:
            del converter, result
        except Exception:
            pass
        gc.collect()
        # 对于非分批模式，返回最终 Markdown 与空的 partial list 以保证调用方兼容，total_batches=1
        return final_md, [], 1

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

    def split_pdf_batches(self, pdf_bytes: bytes, pages_per_batch: int = None, overlap: int = 1) -> list:
        """
        原型：将 PDF bytes 拆分为按页范围的若干批次并返回每个批次的 bytes 列表。
        - 需要安装 `pypdf`（包名 `pypdf`）。
        - 若 pages_per_batch 为 0/None/>=页数，则直接返回原始bytes列表。
        - overlap 为跨批的上下文页数，默认 1。
        """
        if PdfReader is None or PdfWriter is None:
            raise RuntimeError("pypdf 未安装，无法进行 PDF 拆分，请安装 pypdf")

        reader = PdfReader(BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        if pages_per_batch is None or pages_per_batch <= 0 or pages_per_batch >= num_pages:
            return [pdf_bytes]

        batches = []
        start = 0
        while start < num_pages:
            end = min(start + pages_per_batch, num_pages)
            write_start = max(0, start - overlap)
            write_end = min(num_pages, end + overlap)

            writer = PdfWriter()
            for p in range(write_start, write_end):
                writer.add_page(reader.pages[p])

            out = BytesIO()
            writer.write(out)
            batches.append(out.getvalue())

            start = end

        return batches

    def _assess_result_text_quality(self, result) -> dict:
        """评估 docling result 的文本质量，返回统计信息。
        返回示例: { 'chars': int, 'pages': int, 'cjk_ratio': float }
        """
        total_chars = 0
        cjk_chars = 0
        pages = 0
        try:
            from docling_core.types.doc import TextItem
            pages = len(result.document.pages) if hasattr(result.document, 'pages') else 0
            for item, _ in result.document.iterate_items():
                try:
                    if hasattr(item, 'text') and isinstance(item.text, str):
                        s = item.text
                        total_chars += len(s)
                        cjk_chars += len(re.findall(r'[\u4e00-\u9fff]', s))
                except Exception:
                    continue
        except Exception:
            pass

        cjk_ratio = (cjk_chars / total_chars) if total_chars > 0 else 0.0
        return { 'chars': total_chars, 'pages': pages, 'cjk_ratio': cjk_ratio }

    def _contains_english_text(self, res, min_words: int = 50, min_ascii_ratio: float = 0.3) -> bool:
        """Rough heuristic: determine if `res` contains substantial English/Latin text.
        Returns True if there are at least `min_words` Latin words and ascii-letter ratio
        across text exceeds `min_ascii_ratio`.
        """
        try:
            total_chars = 0
            ascii_chars = 0
            word_count = 0
            for item, _ in getattr(res.document, 'iterate_items')():
                try:
                    text = getattr(item, 'text', None)
                    if not text or not isinstance(text, str):
                        continue
                    total_chars += len(text)
                    ascii_chars += len(re.findall(r'[A-Za-z]', text))
                    # count English-like words of length>=2
                    word_count += len(re.findall(r"[A-Za-z]{2,}", text))
                except Exception:
                    continue

            if total_chars <= 0:
                return False
            ascii_ratio = ascii_chars / total_chars
            return (word_count >= min_words) and (ascii_ratio >= min_ascii_ratio)
        except Exception:
            return False

    def result_contains_text(self, result) -> bool:
        """检查 Docling 转换结果中是否包含可用的文本项（TextItem）。
        返回 True 表示存在至少一个非空文本块。
        """
        try:
            from docling_core.types.doc import TextItem
            for item, _ in result.document.iterate_items():
                try:
                    if isinstance(item, TextItem) and getattr(item, 'text', None):
                        if isinstance(item.text, str) and item.text.strip():
                            return True
                except Exception:
                    continue
        except Exception:
            # 如果无法导入 TextItem 或 result 结构异常，则尝试宽松判断
            try:
                for item, _ in result.document.iterate_items():
                    if hasattr(item, 'text') and isinstance(item.text, str) and item.text.strip():
                        return True
            except Exception:
                return False
        return False

    def _render_result_to_markdown(self, res, image_counter_start=0):
        # 将单个 Docling result 转为 markdown（包含图片占位符替换）
        all_text_items = []
        image_tasks = []
        image_counter = image_counter_start

        stats = {
            'text': 0,
            'table': 0,
            'image': 0,
            'code': 0,
            'formula': 0,
            'section_header': 0,
            'filtered_images': 0,
            'filtered_edge_logo': 0,
            'filtered_small': 0
        }

        try:
            from docling_core.types.doc import TextItem, TableItem, PictureItem, CodeItem
        except Exception:
            TextItem = TableItem = PictureItem = CodeItem = object

        idx = 0
        for item, level in res.document.iterate_items():
            idx += 1
            try:
                logging.debug(f"🔄 处理元素[{idx}]: {type(item).__name__}")
            except Exception:
                pass

            if isinstance(item, TextItem):
                if getattr(item, 'label', '') and "formula" in item.label:
                    text_content = f"Formulas::\n{item.text}\n::Formulas"
                    stats['formula'] += 1
                elif getattr(item, 'label', '') and "section_header" in item.label:
                    indent = "  " * (level - 1)
                    text_content = f"{indent}{'#' * level} {item.text}"
                    stats['section_header'] += 1
                elif getattr(item, 'label', '') and "code" in item.label:
                    text_content = f"Code::\n{item.text}\n::Code"
                    stats['code'] += 1
                else:
                    text_content = item.text
                    stats['text'] += 1
                all_text_items.append(('text', text_content))
            elif isinstance(item, TableItem):
                try:
                    # Newer versions of docling TableItem.export_to_dataframe may
                    # require the parent document as first arg; prefer passing it
                    # to avoid deprecation/warning and ensure correct behavior.
                    try:
                        table_df = item.export_to_dataframe(res.document)
                    except TypeError:
                        table_df = item.export_to_dataframe()

                    if table_df is None:
                        logging.debug("TableItem.export_to_dataframe returned None, skipping table")
                        continue

                    # Convert to markdown; if DataFrame-like object doesn't support
                    # to_markdown, fall back to string conversion.
                    try:
                        table_md = table_df.to_markdown()
                    except Exception:
                        try:
                            import pandas as _pd  # noqa: F401
                            table_md = table_df.to_markdown()
                        except Exception:
                            table_md = str(table_df)

                    text_content = f"Table::\n{table_md}\n::Table"
                    all_text_items.append(('text', text_content))
                    stats['table'] += 1
                except Exception as e:
                    logging.debug(f"处理 TableItem 时出错，跳过表格: {e}")
                    continue
            elif isinstance(item, PictureItem):
                try:
                    prov = item.prov[0]
                    bbox = prov.bbox
                    page = prov.page_no
                    page_obj = res.document.pages[page]
                    pil_image = page_obj.image.pil_image
                    page_width, page_height = pil_image.size
                    t = bbox.t
                    l = bbox.l
                    r = bbox.r
                    b = bbox.b
                    is_edge_logo = ((t < 80) or ((page_height - b) < 80) or (l < 90) or ((page_width - r) < 90))
                    is_small = (r - l) * (t - b) < 1000
                    if is_edge_logo or is_small:
                        stats['filtered_images'] += 1
                        if is_edge_logo:
                            stats['filtered_edge_logo'] += 1
                        if is_small:
                            stats['filtered_small'] += 1
                        continue

                    image_data = item.get_image(res.document)
                    if image_data:
                        image_counter += 1
                        stats['image'] += 1
                        placeholder = f"IMAGE_PLACEHOLDER_{image_counter}"
                        image_task = {
                            'placeholder': placeholder,
                            'image_data': image_data,
                            'position': len(all_text_items),
                            'page': page,
                            'coordinates': (l, t, r, b)
                        }
                        image_tasks.append(image_task)
                        all_text_items.append(('image', placeholder))
                except Exception:
                    continue
            elif isinstance(item, CodeItem):
                text_content = f"Code::\n{item.text}\n::Code"
                all_text_items.append(('text', text_content))
            else:
                continue

        # 构建初始 Markdown
        initial_md_parts = [content for (_t, content) in all_text_items]
        initial_md = "\n\n".join(initial_md_parts)

        # 图片处理
        if self.enable_image_caption and image_tasks:
            image_tasks_with_context = self._add_image_context(image_tasks, all_text_items)
            processed_images = self._process_images_parallel(image_tasks_with_context)
            final_md = initial_md
            for placeholder, description in processed_images.items():
                final_md = final_md.replace(placeholder, f"Image::\n{description}\n::Image")
            return final_md, image_counter
        else:
            if not self.enable_image_caption:
                for task in image_tasks:
                    initial_md = initial_md.replace(task['placeholder'], "[图片]")
            return initial_md, image_counter

    def _handle_poor_quality_batch(self, batch_bytes: bytes, bidx: int, image_counter_global: int, device_mode: str) -> Tuple[str, int]:
        """处理低质量批次：强制 full-page OCR。"""


        # 尝试强制 full-page OCR
        try:
            print(f"批次 {bidx+1}: 尝试强制 full-page OCR...")
            gc.collect()
            if device_mode in ("cuda", "gpu"):
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

        frag = ""
        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption, DocumentConverter, ImageFormatOption, \
                PowerpointFormatOption, WordFormatOption, ExcelFormatOption, HTMLFormatOption

            easyocr_options = EasyOcrOptions()
            # model storage path - try multiple possible attribute names
            for _attr in ('model_storage_directory', 'model_storage_dir', 'model_storage_path'):
                try:
                    setattr(easyocr_options, _attr, self.model_path)
                    break
                except Exception:
                    pass

            # force full page OCR - multiple possible attribute names
            for _attr in ('force_full_page_ocr', 'force_fullpage', 'force_fullpage_ocr'):
                try:
                    setattr(easyocr_options, _attr, True)
                    break
                except Exception:
                    pass

            # set OCR languages: accept config or default; normalize common chinese codes
            try:
                langs_raw = get_config().get('OCR_LANGUAGES', None)
                if isinstance(langs_raw, str):
                    langs = [s.strip() for s in langs_raw.split(',') if s.strip()]
                else:
                    langs = list(langs_raw) if langs_raw else None

                if not langs:
                    langs = ['ch', 'en']

                mapped = []
                for l in langs:
                    if not isinstance(l, str):
                        continue
                    ll = l.lower()
                    if ll in ('ch', 'zh', 'zh-cn', 'zh_cn'):
                        mapped.append('ch_sim')
                    elif ll in ('zh-tw', 'zh_tw', 'cht'):
                        mapped.append('ch_tra')
                    else:
                        mapped.append(l)

                # try several field names that different versions may expect
                for _attr in ('lang', 'language', 'languages', 'langs'):
                    try:
                        setattr(easyocr_options, _attr, mapped)
                    except Exception:
                        pass
            except Exception:
                pass

            # GPU / use flag - try common attribute names
            for _attr in ('use_gpu', 'gpu', 'enable_gpu'):
                try:
                    setattr(easyocr_options, _attr, True if device_mode in ("cuda", "gpu") else False)
                    break
                except Exception:
                    pass

            pdf_pipeline_options = PdfPipelineOptions(artifacts_path=self.model_path)
            pdf_pipeline_options.ocr_options = easyocr_options
            pdf_pipeline_options.do_ocr = True
            pdf_pipeline_options.do_formula_enrichment = False
            pdf_pipeline_options.do_code_enrichment = True
            pdf_pipeline_options.do_table_structure = True
            pdf_pipeline_options.generate_page_images = True
            pdf_pipeline_options.generate_picture_images = True
            # For forced OCR retry we want a fresh run: disable pipeline caching
            try:
                pdf_pipeline_options.enable_caching = False
            except Exception:
                pass

            converter_ocr = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
                    InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_pipeline_options),
                    InputFormat.PPTX: PowerpointFormatOption(pipeline_options=pdf_pipeline_options),
                    InputFormat.DOCX: WordFormatOption(pipeline_options=pdf_pipeline_options),
                    InputFormat.XLSX: ExcelFormatOption(pipeline_options=pdf_pipeline_options),
                    InputFormat.HTML: HTMLFormatOption(pipeline_options=pdf_pipeline_options)
                }
            )

            doc_stream_ocr = DocumentStream(name=self.original_filename or f"batch_{bidx}_ocr", stream=BytesIO(batch_bytes))
            try:
                res_ocr = converter_ocr.convert(doc_stream_ocr)
            except Exception as e:
                logging.warning(f"强制 OCR 处理失败: {e}")
                res_ocr = None

            # Diagnostic: log few TextItem samples from res_ocr to help debug noise
            if res_ocr is not None:
                try:
                    sample_texts = []
                    from docling_core.types.doc import TextItem
                    for i, (item, _lv) in enumerate(res_ocr.document.iterate_items()):
                        if i >= 6:
                            break
                        try:
                            if isinstance(item, TextItem) and getattr(item, 'text', None):
                                sample_texts.append(item.text.strip())
                        except Exception:
                            continue
                    logging.info(f"强制 OCR 原始片段样例 (前6项): {sample_texts}")
                except Exception:
                    pass

            if res_ocr is not None and self.result_contains_text(res_ocr):
                try:
                    frag, image_counter_global = self._render_result_to_markdown(res_ocr, image_counter_global)
                except Exception:
                    frag = ""

        except Exception as e:
            logging.debug(f"尝试强制 OCR 时出错: {e}")
            frag = ""
        finally:
            try:
                if 'res_ocr' in locals():
                    try:
                        if hasattr(res_ocr, 'document') and hasattr(res_ocr.document, 'close'):
                            res_ocr.document.close()
                    except Exception:
                        pass
                    try:
                        del res_ocr
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if 'converter_ocr' in locals() and converter_ocr is not None and hasattr(converter_ocr, 'close'):
                    try:
                        converter_ocr.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                del converter_ocr
            except Exception:
                pass
            gc.collect()
            if device_mode in ("cuda", "gpu"):
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        return frag, image_counter_global



    def _process_images_parallel(self, image_tasks: List[Dict]) -> Dict[str, str]:
        """并行处理图片 - 使用多线程池同时调用视觉语言模型API"""
        processed_results = {}  # 存储所有图片的处理结果 {占位符: 描述文本}
        completed_count = 0
        total_count = len(image_tasks)

        # 创建线程池，最大并发数由 self.max_workers 控制（默认10）
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 【第1步】一次性提交所有图片处理任务到线程池
            # executor.submit() 立即返回 Future 对象，不会阻塞
            # 每个任务会在独立线程中调用 _process_single_image 方法（该方法内部会调用API）
            future_to_placeholder = {
                executor.submit(self._process_single_image, task): task['placeholder']
                for task in image_tasks
            }

            # 【第2步】收集已完成任务的结果
            # as_completed() 会按完成顺序（非提交顺序）逐个返回已完成的 Future
            for future in concurrent.futures.as_completed(future_to_placeholder):
                placeholder = future_to_placeholder[future]
                try:
                    # future.result() 获取线程执行结果（阻塞直到该任务完成）
                    # 这里拿到的是 VLM API 返回的图片描述文本
                    description = future.result()
                    processed_results[placeholder] = description
                    completed_count += 1
                    logging.info(f"✅ 图片处理进度: {completed_count}/{total_count} ({placeholder})")
                except Exception as e:
                    logging.error(f"❌ 处理图片 {placeholder} 失败: {e}")
                    processed_results[placeholder] = "图片内容处理失败"
                    completed_count += 1

        return processed_results

    def _process_single_image(self, image_task: Dict) -> str:
        """处理单张图片，包含重试机制
        
        工作流程：
        1. 提取图片数据和上下文
        2. 将PIL图片转为PNG字节流
        3. 构建prompt（系统提示词 + 上下文 + 用户要求）
        4. 🔥 调用视觉语言模型API（这是真正的网络请求）
        5. 返回API生成的图片描述文本
        """
        # 从任务字典中提取所需信息
        image_data = image_task['image_data']  # PIL.Image 对象
        context = image_task['context']  # 图片前后文本（前后各200字符）
        page_info = image_task['page_info']  # 图片所在页码

        full_context = f"{page_info}\n{context}"  # 组合完整上下文

        # 重试机制：允许失败后重试 max_retries 次（默认1次）
        for attempt in range(self.max_retries + 1):
            try:
                # 【步骤1】将PIL Image转换为PNG字节流（API要求的格式）
                buffered = BytesIO()
                image_data.save(buffered, format="PNG")
                image_bytes = buffered.getvalue()

                # 【步骤2】构建AI模型的输入prompt
                system_prompt = """请详细描述图片内容，识别其中的关键信息，并生成适合知识图谱构建的结构化信息。"""
                user_prompt = f"""
                    图片上下文：{full_context}
                    请生成包含以下内容的JSON格式结果：
                    - 图片的详细描述
                    - 识别出的关键实体和关系
                """

                # 🔥🔥🔥 【关键：这一行调用远程API】 🔥🔥🔥
                # 调用 LitellmMultiModel.call_image_model() 方法
                # 实际发送HTTP请求到 qwen-vl-plus API（通义千问视觉模型）
                # 参数1: 完整prompt（系统提示+用户需求）
                # 参数2: 图片字节数据
                # 返回值: API生成的图片描述文本（JSON格式）
                result = self.vl_model.call_image_model(system_prompt + user_prompt, image_bytes)
                return result  # 成功则返回结果并退出重试循环

            except Exception as e:
                # Detect non-retriable external service errors (e.g., account arrears)
                non_retriable = False
                try:
                    import litellm
                    if hasattr(litellm, 'BadRequestError') and isinstance(e, getattr(litellm, 'BadRequestError')):
                        non_retriable = True
                except Exception:
                    pass

                msg = str(e) or ''
                if 'Access denied' in msg or 'Arrearage' in msg or 'overdue' in msg.lower():
                    non_retriable = True

                # Log and immediate fallback for non-retriable errors
                if non_retriable:
                    import traceback
                    logging.error(
                        f"图片模型不可用（非重试错误），返回占位文本。异常类型: {type(e).__name__}，错误: {msg}\n完整堆栈:\n{traceback.format_exc()}"
                    )
                    return "图片处理失败（外部模型不可用）"

                # 增强错误日志：显示异常类型和详细堆栈（仅在首次失败时显示完整堆栈）
                if attempt == 0:
                    import traceback
                    logging.error(
                        f"图片处理首次尝试失败（将重试{self.max_retries}次）\n"
                        f"  异常类型: {type(e).__name__}\n"
                        f"  错误详情: {msg}\n"
                        f"  完整堆栈:\n{traceback.format_exc()}"
                    )
                else:
                    logging.warning(f"图片处理尝试 {attempt + 1}/{self.max_retries + 1} 失败: {type(e).__name__}: {e}")

                if attempt < self.max_retries:
                    time.sleep(1)  # 重试前等待1秒，避免API限流
                else:
                    raise Exception(f"图片处理失败，已重试{self.max_retries}次。最后错误: {type(e).__name__}: {e}") from e

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
    # file_path = "/root/knowlion/pdfs/不同刈割强度下稀土超富集植物芒萁的超补偿生长及净化稀土效应.pdf"
    # file_path = "/root/knowlion/pdfs/基于RAG的维修手册智能问答系统研究与应用_郭超_象征性编辑.pdf"
    file_path = "/root/knowlion/pdfs/第1章+绪论.pdf"
    model_path = "/thutmose/app/abution/model"

    from config import MODEL_CONFIGS

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
    
    # 4. 保存Markdown到文件
    markdowns_dir = os.path.join(os.path.dirname(__file__), '..', 'markdowns')
    os.makedirs(markdowns_dir, exist_ok=True)
    
    md_filename = f"{parser.original_filename}.md"
    md_filepath = os.path.join(markdowns_dir, md_filename)
    
    with open(md_filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"✅ Markdown已保存到: {md_filepath}")
    print(f"📝 文件大小: {len(md_content)} 字符")
    print(f"\n📄 Markdown 前500字符预览:")
    print("="*50)
    print(md_content[:500])
    print("="*50)