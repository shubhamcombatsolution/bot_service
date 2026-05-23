"""
Knowledge Base Build Status Routes.
Provides async KB creation with background processing and status tracking.
"""

import os
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from qdrant_client import QdrantClient
from app.models.knowledge_base import KnowledgeBase
from app.database.DatabaseOperationPostgreSQL import db_session
from app.services.build_tasks_manager import get_build_tasks_manager, BuildStatus
from logging_config import setup_logging

logger = setup_logging("kb-build-routes", level="DEBUG")
LIST_FIELD_MAX_LEN = 255
MAX_UPLOAD_FILES = 6

# Initialize Qdrant client
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
qdrant = QdrantClient(url=QDRANT_URL, timeout=120)

kb_build_blueprint = Blueprint("kb_build", __name__)


@kb_build_blueprint.route("/builds", methods=["GET"])
@kb_build_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_builds():
    """
    Get all KB build tasks + enrich with KB details
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found"}), 401

        session = next(db_session())

        try:
            # 🔹 1. Get all KBs
            knowledge_bases = session.query(KnowledgeBase).filter_by(
                tenant_id=tenant_id,
                del_flg=False
            ).all()

            kb_map = {
                kb.knowledge_base_id: {
                    "knowledge_base_id": kb.knowledge_base_id,
                    "tenant_id": kb.tenant_id,
                    "knowledge_base_name": kb.knowledge_base_name,
                    "description": kb.description,
                    "knowledge_base_summary": kb.kb_summary,
                    "upload_pdf": kb.upload_pdf,
                    "scrap_url": kb.scrap_url,
                    "created_at": kb.created_at.isoformat() if kb.created_at else None,
                    "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
                }
                for kb in knowledge_bases
            }

            # 🔹 2. Get build tasks
            manager = get_build_tasks_manager()
            tasks = manager.get_all_tasks(tenant_id=tenant_id, limit=50)

            def enrich(task):
                kb_id = task.get("knowledge_base_id")
                kb_data = kb_map.get(kb_id, {})

                return {
                    **kb_data,   # ✅ full KB fields
                    **task       # ✅ task fields (status, logs, progress)
                }

            active = [enrich(t) for t in tasks.get("active", [])]
            completed = [enrich(t) for t in tasks.get("completed", [])]

            return jsonify({
                "status": "success",
                "data": {
                    "active": active,
                    "completed": completed
                }
            }), 200

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error fetching builds: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@kb_build_blueprint.route("/builds/<task_id>", methods=["GET"])
@kb_build_blueprint.route("/<task_id>", methods=["GET"])
@jwt_required()
def get_status(task_id: str):
    """
    Get status of a specific build task.
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401
        
        manager = get_build_tasks_manager()
        task = manager.get_task(task_id)
        
        if not task:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        # Verify tenant ownership
        if task.get("tenant_id") != tenant_id:
            return jsonify({"status": "error", "message": "Access denied"}), 403
        
        return jsonify({
            "status": "success",
            "data": task
        }), 200
    except Exception as e:
        logger.error(f"Error fetching build status: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@kb_build_blueprint.route("/builds/<task_id>/cancel", methods=["POST"])
@kb_build_blueprint.route("/<task_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_build(task_id: str):
    """
    Cancel a pending or in-progress build task.
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401
        
        manager = get_build_tasks_manager()
        task = manager.get_task(task_id)
        
        if not task:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        if task.get("tenant_id") != tenant_id:
            return jsonify({"status": "error", "message": "Access denied"}), 403
        
        success = manager.cancel_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "Build cancelled"}), 200
        else:
            return jsonify({"status": "error", "message": "Cannot cancel this build"}), 400
    except Exception as e:
        logger.error(f"Error cancelling build: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@kb_build_blueprint.route("/builds/<task_id>/retry", methods=["POST"])
@kb_build_blueprint.route("/<task_id>/retry", methods=["POST"])
@jwt_required()
def retry_build(task_id: str):
    """
    Retry a failed build task.
    Creates a new task with the same parameters.
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401
        
        manager = get_build_tasks_manager()
        old_task = manager.get_task(task_id)
        
        if not old_task:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        if old_task.get("tenant_id") != tenant_id:
            return jsonify({"status": "error", "message": "Access denied"}), 403
        
        if old_task.get("status") != BuildStatus.FAILED.value:
            return jsonify({"status": "error", "message": "Only failed builds can be retried"}), 400
        
        # Get the knowledge base to retry
        kb_id = old_task.get("knowledge_base_id")
        if not kb_id:
            return jsonify({"status": "error", "message": "No knowledge base associated with this task"}), 400
        
        session = next(db_session())
        try:
            kb = session.query(KnowledgeBase).filter_by(
                knowledge_base_id=kb_id,
                tenant_id=tenant_id
            ).first()
            
            if not kb:
                return jsonify({"status": "error", "message": "Knowledge base not found"}), 404
            
            # Create new task
            new_task_id = manager.create_task(
                tenant_id=tenant_id,
                knowledge_base_name=kb.knowledge_base_name,
                knowledge_base_id=kb_id,
                metadata=old_task.get("metadata", {})
            )
            
            # Update KB status
            kb.status = "pending"
            kb.build_task_id = new_task_id
            kb.error_message = None
            session.commit()
            
            # Trigger background rebuild
            from app.routes.knowledge_base_routes import rebuild_knowledge_base_async
            thread = threading.Thread(
                target=rebuild_knowledge_base_async,
                args=(current_app._get_current_object(), new_task_id, kb_id, tenant_id)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "status": "success",
                "message": "Rebuild started",
                "data": {"task_id": new_task_id}
            }), 202
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error retrying build: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@kb_build_blueprint.route("/register-async", methods=["POST"])
@jwt_required()
def create_knowledge_base_async():
    try:
        logger.info("=== ASYNC KNOWLEDGE BASE CREATION REQUEST ===")

        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found"}), 401

        if not request.content_type or 'multipart/form-data' not in request.content_type:
            return jsonify({"status": "error", "message": "Content-Type must be multipart/form-data"}), 400

        data = request.form

        # ✅ Required
        knowledge_base_name = data.get("knowledge_base_name", "").strip()
        if not knowledge_base_name:
            return jsonify({"status": "error", "message": "Missing knowledge_base_name"}), 400

        # ✅ OPTIONAL FIELDS (FIXED)
        description = data.get("description", "").strip()
        kb_summary = data.get("knowledge_base_summary", "").strip()

        # ✅ FILES
        files = (
            request.files.getlist("pdf_files")
            + request.files.getlist("excel_files")
            + request.files.getlist("docx_files")
            + request.files.getlist("txt_files")
        )
        if len([f for f in files if getattr(f, "filename", "")]) > MAX_UPLOAD_FILES:
            return jsonify({
                "status": "error",
                "message": f"Maximum {MAX_UPLOAD_FILES} files are allowed per request."
            }), 400

        upload_dir = os.path.join(
            "Uploads",
            f"async_{datetime.now().strftime('%Y%m%d%H%M%S')}_{tenant_id}"
        )
        os.makedirs(upload_dir, exist_ok=True)

        saved_files = []
        for file in files:
            if file.filename:
                file_path = os.path.join(upload_dir, file.filename)
                file.save(file_path)
                saved_files.append({"filename": file.filename, "path": file_path})

        # ✅ Prepare file + URL fields
        upload_pdf_names = [f["filename"] for f in saved_files]

        scrap_urls = request.form.getlist("scrap_urls")
        scrap_urls_alt = request.form.getlist("scrap_urls[]")
        if scrap_urls_alt:
            scrap_urls.extend(scrap_urls_alt)

        if not scrap_urls:
            scrap_urls = [
                data[key].strip()
                for key in data
                if key.startswith("scrap_urls") and data[key].strip()
            ]

        scrap_urls = [
            (url.strip() if url.startswith("http") else f"https://{url.strip()}")
            for url in scrap_urls
            if url.strip()
        ]
        scrap_urls = list(dict.fromkeys(scrap_urls))

        upload_pdf_str = ",".join(upload_pdf_names) if upload_pdf_names else None
        scrap_url_str = ",".join(scrap_urls) if scrap_urls else None

        if upload_pdf_str and len(upload_pdf_str) > LIST_FIELD_MAX_LEN:
            return jsonify({
                "status": "error",
                "message": f"Total uploaded file names are too long ({len(upload_pdf_str)} chars). Please reduce file count or shorten file names."
            }), 400
        if scrap_url_str and len(scrap_url_str) > LIST_FIELD_MAX_LEN:
            return jsonify({
                "status": "error",
                "message": f"Total URLs are too long ({len(scrap_url_str)} chars). Please reduce URL count or use shorter URLs."
            }), 400

        # ✅ METADATA (ONLY PROCESSING DATA)
        metadata = {
            "upload_dir": upload_dir,
            "files": saved_files,
            "scrap_urls": scrap_urls,
            "raw_text": data.get("raw_text", "").strip(),
            "provider": data.get("provider", "").strip(),
            "embedding_model": data.get("embeddingModel", "").strip(),
            "secret_key": data.get("secretKey", "").strip(),
            "chunk_size": int(data.get("chunk_size", 1024)),
            "chunk_overlap": int(data.get("chunk_overlap", 150)),
            "max_crawl_pages": data.get("max_crawl_pages", "25"),
            "max_crawl_depth": data.get("max_crawl_depth", "10"),
            "dynamic_wait": data.get("dynamic_wait", "2")
        }

        # ✅ CREATE TASK
        manager = get_build_tasks_manager()
        task_id = manager.create_task(
            tenant_id=tenant_id,
            knowledge_base_name=knowledge_base_name,
            metadata=metadata
        )

        # ✅ SAVE TO DB (FIXED)
        session = next(db_session())
        try:
            new_kb = KnowledgeBase(
                tenant_id=tenant_id,
                knowledge_base_name=knowledge_base_name,

                description=description,
                kb_summary=kb_summary,
                upload_pdf=upload_pdf_str,
                scrap_url=scrap_url_str,

                status="pending",
                build_task_id=task_id,
                total_chunks=0,
                processed_chunks=0,

                chunk_size=metadata["chunk_size"],
                chunk_overlap=metadata["chunk_overlap"],
                max_crawl_pages=metadata.get("max_crawl_pages"),
                max_crawl_depth=metadata.get("max_crawl_depth"),
                dynamic_wait=metadata.get("dynamic_wait"),
                raw_text=metadata.get("raw_text")
            )

            session.add(new_kb)
            session.commit()

            kb_id = new_kb.knowledge_base_id
            manager.set_knowledge_base_id(task_id, kb_id)

        except Exception as e:
            session.rollback()
            manager.fail_task(task_id, str(e))
            raise
        finally:
            session.close()

        # ✅ BACKGROUND THREAD
        from app.routes.knowledge_base_routes import process_knowledge_base_async

        thread = threading.Thread(
            target=process_knowledge_base_async,
            args=(current_app._get_current_object(), task_id, kb_id, tenant_id, metadata)
        )
        logger.info("[KB CREATE START]")
        logger.info(f"[ASYNC TASK CREATED] Task ID: {task_id} | KB ID: {kb_id}")
        logger.info(f"[KB CREATE] Tenant: {tenant_id}")
        logger.info(f"[KB CREATE] Name: {knowledge_base_name}")
        logger.info(f"[KB CREATE] Files: {[f['filename'] for f in saved_files]}")

        raw_text = metadata.get("raw_text") or ""
        logger.info(f"[KB CREATE] Raw Text Input Length: {len(raw_text)}")
        if not raw_text and saved_files:
            logger.info("[KB CREATE] Raw text not supplied in request; extracted file text will be logged during background processing.")

        logger.info(f"[KB CREATE] Scrap URLs Count: {len(scrap_urls)}")
        logger.info(f"[KB CREATE] Scrap URLs (sample): {scrap_urls[:5]}")

        logger.info(f"[KB CREATE] Chunk Size: {metadata['chunk_size']} | Overlap: {metadata['chunk_overlap']}")
        logger.info(f"[KB CREATE] Crawl Config → Pages: {metadata.get('max_crawl_pages')} | Depth: {metadata.get('max_crawl_depth')} | Wait: {metadata.get('dynamic_wait')}")
        logger.info("=" * 80)

        # ✅ THEN start thread
        thread.start()
        return jsonify({
            "status": "success",
            "data": {
                "task_id": task_id,
                "knowledge_base_id": kb_id
            }
        }), 202

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@kb_build_blueprint.route("/builds/<task_id>/chunks", methods=["GET"])
@kb_build_blueprint.route("/<task_id>/chunks", methods=["GET"])
@jwt_required()
def get_build_chunks(task_id: str):
    """



    
    Get the embedded chunks for a completed build.
    Supports pagination with offset and limit query parameters.
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found in token"}), 401
        
        # Get pagination parameters
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 20, type=int)
        limit = min(limit, 100)  # Cap at 100 per request
        
        # Get the task
        manager = get_build_tasks_manager()
        task = manager.get_task(task_id)
        
        if not task:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        if task.get("tenant_id") != tenant_id:
            return jsonify({"status": "error", "message": "Access denied"}), 403
        
        if task.get("status") != BuildStatus.COMPLETED.value:
            return jsonify({"status": "error", "message": "Chunks only available for completed builds"}), 400
        
        # Get collection name from build_summary
        build_summary = task.get("build_summary", {})
        collection_name = build_summary.get("collection_name")
        
        if not collection_name:
            # Try to get from KB record
            kb_id = task.get("knowledge_base_id")
            if kb_id:
                session = next(db_session())
                try:
                    kb = session.query(KnowledgeBase).filter_by(
                        knowledge_base_id=kb_id,
                        tenant_id=tenant_id
                    ).first()
                    if kb:
                        collection_name = kb.collection_name
                finally:
                    session.close()
        
        if not collection_name:
            return jsonify({"status": "error", "message": "Collection name not found"}), 404
        
        # Check if collection exists
        try:
            collection_info = qdrant.get_collection(collection_name)
            total_points = collection_info.points_count
        except Exception as e:
            logger.error(f"Collection not found: {collection_name}, error: {e}")
            return jsonify({"status": "error", "message": "Collection not found in Qdrant"}), 404
        
        # Fetch chunks using scroll
        try:
            results, next_offset = qdrant.scroll(
                collection_name=collection_name,
                offset=offset if offset > 0 else None,
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            chunks = []
            for point in results:
                payload = point.payload or {}
                chunks.append({
                    "id": str(point.id),
                    "text": payload.get("text", payload.get("content", "")),
                    "source_type": payload.get("source_type", "unknown"),
                    "metadata": {
                        k: v for k, v in payload.items() 
                        if k not in ["text", "content", "embedding"]
                    }
                })
            
            return jsonify({
                "status": "success",
                "data": {
                    "chunks": chunks,
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total_points,
                        "has_more": (offset + len(chunks)) < total_points,
                        "next_offset": offset + len(chunks) if (offset + len(chunks)) < total_points else None
                    }
                }
            }), 200
            
        except Exception as e:
            logger.error(f"Error fetching chunks: {str(e)}")
            return jsonify({"status": "error", "message": f"Error fetching chunks: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Error in get_build_chunks: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@kb_build_blueprint.route("/update-async/<int:kb_id>", methods=["POST"])
@jwt_required()
def update_knowledge_base_async(kb_id):
    try:
        logger.info("=== ASYNC KNOWLEDGE BASE UPDATE REQUEST ===")

        # ✅ AUTH
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"status": "error", "message": "Tenant ID not found"}), 401

        # ✅ CONTENT TYPE
        if not request.content_type or 'multipart/form-data' not in request.content_type:
            return jsonify({"status": "error", "message": "Content-Type must be multipart/form-data"}), 400

        data = request.form

        # ✅ FETCH KB
        session = next(db_session())
        kb = session.query(KnowledgeBase).filter_by(
            knowledge_base_id=kb_id,
            tenant_id=tenant_id
        ).first()

        if not kb:
            session.close()
            return jsonify({"status": "error", "message": "Knowledge base not found"}), 404

        # ✅ BASIC FIELDS
        knowledge_base_name = data.get("knowledge_base_name", kb.knowledge_base_name).strip()
        description = data.get("description", kb.description or "").strip()
        kb_summary = data.get("knowledge_base_summary", kb.kb_summary or "").strip()

        # ✅ FILES
        files = (
            request.files.getlist("pdf_files")
            + request.files.getlist("excel_files")
            + request.files.getlist("docx_files")
            + request.files.getlist("txt_files")
        )
        if len([f for f in files if getattr(f, "filename", "")]) > MAX_UPLOAD_FILES:
            session.close()
            return jsonify({
                "status": "error",
                "message": f"Maximum {MAX_UPLOAD_FILES} files are allowed per request."
            }), 400

        upload_dir = os.path.join(
            "Uploads",
            f"update_async_{datetime.now().strftime('%Y%m%d%H%M%S')}_{tenant_id}"
        )
        os.makedirs(upload_dir, exist_ok=True)

        saved_files = []
        for file in files:
            if file.filename:
                file_path = os.path.join(upload_dir, file.filename)
                file.save(file_path)
                saved_files.append({"filename": file.filename, "path": file_path})

        upload_pdf_names = [f["filename"] for f in saved_files]

        # ✅ SCRAP URLS (aligned with register-async behavior)
        # Accept both "scrap_urls" and "scrap_urls[]"
        scrap_urls = request.form.getlist("scrap_urls")
        scrap_urls_alt = request.form.getlist("scrap_urls[]")
        if scrap_urls_alt:
            scrap_urls.extend(scrap_urls_alt)

        # Backward compatibility: support indexed keys like scrap_urls0, scrap_urls_1
        if not scrap_urls:
            scrap_urls = [
                data[key].strip()
                for key in data
                if key.startswith("scrap_urls") and data[key].strip()
            ]

        scrap_urls = [
            (url.strip() if url.strip().startswith("http") else f"https://{url.strip()}")
            for url in scrap_urls
            if url and url.strip()
        ]
        scrap_urls = list(dict.fromkeys(scrap_urls))

        # If no URLs are sent in update request, keep existing DB value
        scrap_url_str = ",".join(scrap_urls) if scrap_urls else kb.scrap_url
        existing_files = [x.strip() for x in (kb.upload_pdf or "").split(",") if x.strip()]
        merged_files = list(dict.fromkeys(existing_files + upload_pdf_names))
        merged_upload_pdf_str = ",".join(merged_files) if merged_files else None

        if merged_upload_pdf_str and len(merged_upload_pdf_str) > LIST_FIELD_MAX_LEN:
            session.close()
            return jsonify({
                "status": "error",
                "message": f"Total uploaded file names are too long ({len(merged_upload_pdf_str)} chars). Please reduce file count or shorten file names."
            }), 400
        if scrap_url_str and len(scrap_url_str) > LIST_FIELD_MAX_LEN:
            session.close()
            return jsonify({
                "status": "error",
                "message": f"Total URLs are too long ({len(scrap_url_str)} chars). Please reduce URL count or use shorter URLs."
            }), 400

        # ✅ METADATA
        metadata = {
            "upload_dir": upload_dir,
            "files": saved_files,
            "scrap_urls": scrap_urls,
            "raw_text": data.get("raw_text", "").strip(),
            "provider": data.get("provider", "").strip(),
            "embedding_model": data.get("embeddingModel", "").strip(),
            "secret_key": data.get("secretKey", "").strip(),
            "chunk_size": int(data.get("chunk_size", kb.chunk_size or 512)),
            "chunk_overlap": int(data.get("chunk_overlap", kb.chunk_overlap or 100)),
            "max_crawl_pages": data.get("max_crawl_pages", str(kb.max_crawl_pages or 25)),
            "max_crawl_depth": data.get("max_crawl_depth", str(kb.max_crawl_depth or 10)),
            "dynamic_wait": data.get("dynamic_wait", str(kb.dynamic_wait or 2))
        }

        # ✅ CREATE TASK
        manager = get_build_tasks_manager()
        task_id = manager.create_task(
            tenant_id=tenant_id,
            knowledge_base_name=knowledge_base_name,
            knowledge_base_id=kb_id,
            metadata=metadata
        )

        # ✅ UPDATE DB (IMPORTANT)
        kb.knowledge_base_name = knowledge_base_name
        kb.description = description
        kb.kb_summary = kb_summary

        if merged_upload_pdf_str:
            kb.upload_pdf = merged_upload_pdf_str

        kb.scrap_url = scrap_url_str
        kb.status = "pending"
        kb.build_task_id = task_id
        kb.error_message = None
        kb.error_message = None
        kb.total_chunks = 0
        kb.processed_chunks = 0

        kb.chunk_size = metadata["chunk_size"]
        kb.chunk_overlap = metadata["chunk_overlap"]
        kb.max_crawl_pages = metadata.get("max_crawl_pages")
        kb.max_crawl_depth = metadata.get("max_crawl_depth")
        kb.dynamic_wait = metadata.get("dynamic_wait")
        kb.raw_text = metadata.get("raw_text")

        session.commit()
        session.close()

        # ✅ START BACKGROUND UPDATE
        from app.routes.knowledge_base_routes import rebuild_knowledge_base_async

        thread = threading.Thread(
            target=rebuild_knowledge_base_async,
            args=(current_app._get_current_object(), task_id, kb_id, tenant_id)
        )
        thread.daemon = True

        logger.info("\n" + "=" * 80)
        logger.info("[KB UPDATE START]")
        logger.info(f"[ASYNC UPDATE TASK] Task ID: {task_id} | KB ID: {kb_id}")
        logger.info(f"[KB UPDATE] Tenant: {tenant_id}")
        logger.info(f"[KB UPDATE] Name: {knowledge_base_name}")
        logger.info(f"[KB UPDATE] Files: {[f['filename'] for f in saved_files]}")
        logger.info(f"[KB UPDATE] URLs: {scrap_urls[:5]}")
        logger.info("=" * 80)

        thread.start()

        return jsonify({
            "status": "success",
            "message": "KB update started",
            "data": {
                "task_id": task_id,
                "knowledge_base_id": kb_id
            }
        }), 202

    except Exception as e:
        logger.error(f"Error in async update: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@kb_build_blueprint.route("/delete-async/<int:kb_id>", methods=["DELETE"])
@jwt_required()
def delete_knowledge_base(kb_id):
    """Delete a knowledge base by ID for the authenticated tenant."""
    session = None
    try:
        # ✅ AUTH
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        # ✅ DB SESSION
        session = next(db_session())

        # ✅ FETCH KB
        kb = session.query(KnowledgeBase).filter_by(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id
        ).first()

        if not kb:
            logger.warning(f"KB not found: ID={kb_id}, tenant={tenant_id}")
            return jsonify({
                "status": "error",
                "message": "Knowledge base not found"
            }), 404

        # ✅ DELETE QDRANT COLLECTION (IMPORTANT)
        if kb.collection_name:
            try:
                qdrant.delete_collection(kb.collection_name)
                logger.info(f"Deleted Qdrant collection: {kb.collection_name}")
            except Exception as e:
                logger.warning(f"Qdrant delete failed: {str(e)}")

        # ✅ DELETE DB RECORD
        session.delete(kb)
        session.commit()

        logger.info(f"KB deleted: ID={kb_id}, tenant={tenant_id}")

        return jsonify({
            "status": "success",
            "message": "Knowledge base deleted successfully"
        }), 200

    except Exception as e:
        if session:
            session.rollback()

        logger.error(f"Error deleting KB {kb_id}: {str(e)}")

        return jsonify({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

    finally:
        if session:
            session.close()
