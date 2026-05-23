# ===== FILE: nodes/text_splitter_node.py =====
import os
import re
import logging
from typing import Dict, Any, List
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.logging_config import setup_logging

logger = setup_logging(__name__, level=logging.DEBUG)
BASE_DIR = "/home/ubuntu/mcp_bot_builder"  # prepend to relative paths if needed


@register_node("TextSplitterNode")
class TextSplitterNode(BaseNode):
    """
    Splits long text into smaller chunks with overlap.
    Supports sentence-aware splitting for cleaner context.
    Matches @mcp.tool("Text.splitter") behavior.
    """

    def __init__(self, node_id, data):
        self.node_id = node_id
        self.data = data

    def execute(self, context) -> Dict[str, Any]:
        form_data = self.data.get("formData", {})
        text_field = form_data.get("text_field")  # e.g., "pdf_extractor.extracted_text"
        max_chunk_size = int(form_data.get("max_chunk_size", 2000))
        overlap = int(form_data.get("overlap", 100))
        split_by_sentence = form_data.get("split_by_sentence", True) in (True, "true", "True")

        # Resolve input text
        text = self._resolve_field(context, text_field)
        if not text or not isinstance(text, str):
            logger.error(f"[TextSplitterNode] Invalid or missing text at field: {text_field}")
            return {"success": False, "error": "No valid text provided."}

        logger.info(f"[TextSplitterNode] Splitting text of {len(text)} chars "
                    f"(max_chunk_size={max_chunk_size}, overlap={overlap}, sentence_split={split_by_sentence})")

        try:
            result = self._split_text(
                text=text,
                max_chunk_size=max_chunk_size,
                overlap=overlap,
                split_by_sentence=split_by_sentence
            )
            logger.info(f"[TextSplitterNode] Created {result['total_chunks']} chunks")
            return result

        except Exception as e:
            logger.exception(f"[TextSplitterNode] Failed to split text: {e}")
            return {"success": False, "error": str(e)}

    def _split_text(
        self,
        text: str,
        max_chunk_size: int,
        overlap: int,
        split_by_sentence: bool
    ) -> Dict[str, Any]:
        """
        Core splitting logic — identical to @mcp.tool("Text.splitter")
        """
        # --- Step 1: Normalize ---
        text = text.strip().replace("\r\n", "\n").replace("\r", "\n")

        # --- Step 2: Split into sentences (if enabled) ---
        if split_by_sentence:
            # Split on sentence boundaries: . ! ? followed by whitespace
            sentences = re.split(r'(?<=[.!?])\s+', text)
            if not sentences:
                sentences = [text]
        else:
            sentences = [text]

        # --- Step 3: Build chunks with size & overlap ---
        chunks = []
        current_chunk = ""
        char_start = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if adding sentence exceeds limit
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += (" " + sentence) if current_chunk else sentence
            else:
                # Save current chunk
                if current_chunk.strip():
                    chunks.append({
                        "content": current_chunk.strip(),
                        "start_char": char_start,
                        "end_char": char_start + len(current_chunk),
                        "chunk_id": len(chunks)
                    })
                    char_start += len(current_chunk) - overlap  # move start forward, keep overlap

                # Start new chunk with overlap
                if overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-overlap:].strip()
                    current_chunk = overlap_text + " " + sentence
                else:
                    current_chunk = sentence

        # Add final chunk
        if current_chunk.strip():
            chunks.append({
                "content": current_chunk.strip(),
                "start_char": char_start,
                "end_char": char_start + len(current_chunk),
                "chunk_id": len(chunks)
            })

        return {
            "success": True,
            "chunks": chunks,
            "total_chunks": len(chunks),
            "config": {
                "max_chunk_size": max_chunk_size,
                "overlap": overlap,
                "split_by_sentence": split_by_sentence
            }
        }

    def _resolve_field(self, context, path: str):
        """Same as in PDFExtractorNode — reuse logic"""
        if not path:
            logger.warning("[TextSplitterNode] No path provided to resolve")
            return None
        try:
            parts = path.split(".")
            value = context
            for p in parts:
                if isinstance(value, dict):
                    value = value.get(p)
                elif isinstance(value, list) and p.isdigit():
                    value = value[int(p)]
                else:
                    logger.debug(f"[TextSplitterNode] Path '{path}' not found at '{p}'")
                    return None
            return value
        except Exception as e:
            logger.warning(f"[TextSplitterNode] Failed to resolve field '{path}': {e}")
            return None