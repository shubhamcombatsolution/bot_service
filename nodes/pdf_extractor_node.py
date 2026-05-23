# ===== FILE: nodes/pdf_extractor_node.py =====
import os
import logging
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.logging_config import setup_logging
from PyPDF2 import PdfReader
from nodes.utils.resolver import resolve_field

logger = setup_logging(__name__, level=logging.DEBUG)

BASE_DIR = "/app" # prepend this to all relative paths


@register_node("PDFExtractorNode")
class PDFExtractorNode(BaseNode):
    """
    Node that extracts text from a PDF file given a file path.
    """

    def __init__(self, node_id, data):
        self.node_id = node_id
        self.data = data

    def execute(self, context):
        form_data = self.data.get("formData", {})
        pdf_source = form_data.get("pdf_source")

        pdf_path = resolve_field(context, pdf_source)

        # Fix: if the path is relative, prepend BASE_DIR
        if pdf_path and not pdf_path.startswith("/"):
            pdf_path = os.path.join(BASE_DIR, pdf_path)
            
        logger.info(f"[PDFExtractorNode] Final resolved path: {pdf_path}")
        logger.info(
            f"[PDFExtractorNode] File exists? {os.path.exists(pdf_path) if pdf_path else False}"
        )
        logger.info(f"[PDFExtractorNode] Extracting text from: {pdf_path}")

        if not pdf_path or not os.path.exists(pdf_path):
            return {
                "extracted_text": "",
                "skipped": True,
                "reason": "no_pdf_path"
            }

        try:
            text = self._extract_text_from_pdf(pdf_path)
            logger.info(f"[PDFExtractorNode] Successfully extracted text ({len(text)} chars)")
            return {"extracted_text": text}
        except Exception as e:
            logger.exception(f"[PDFExtractorNode] Failed to extract PDF text: {e}")
            return {"error": str(e)}

    def _extract_text_from_pdf(self, pdf_path):
        reader = PdfReader(pdf_path)
        text = ""
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            text += page_text + "\n"
            logger.debug(f"[PDFExtractorNode] Extracted page {page_num + 1}: {len(page_text)} chars")
        return text.strip()

    # def _resolve_field(self, context, path: str):
    #     if not path:
    #         logger.warning("[PDFExtractorNode] No path provided to resolve")
    #         return None

    #     try:
    #         parts = path.split(".")
    #         value = context

    #         for p in parts:
    #             if isinstance(value, dict):
    #                 value = value.get(p)
    #             elif isinstance(value, list) and p.isdigit():
    #                 value = value[int(p)]
    #             else:
    #                 logger.debug(f"[PDFExtractorNode] Path '{path}' not found at '{p}'")
    #                 return None

    #         return value

    #     except Exception as e:
    #         logger.warning(f"[PDFExtractorNode] Failed to resolve field '{path}': {e}")
    #         return None
