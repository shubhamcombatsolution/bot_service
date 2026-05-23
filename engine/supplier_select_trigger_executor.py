# # engine/supplier_select_trigger_executor.py

# import json
# import logging
# from app.models.workflow_trigger import WorkflowTrigger
# from app.models.bot_diagram import BotDiagram
# from app.database.DatabaseOperationPostgreSQL import db_session
# from engine.workflow_executor import WorkflowExecutor

# logger = logging.getLogger(__name__)


# def run_supplier_selection(bot_id, tenant_id, selected_supplier):
#     """
#     Execute workflow when admin selects a supplier.

#     selected_supplier = {
#         "rfq_id": 55,
#         "supplier_id": 2001,
#         "supplier_name": "ABC Pvt Ltd",
#         "selected_by": "Admin"
#     }
#     """

#     session = next(db_session())
#     try:
#         # ---------------------------------------------------------
#         # 1. Fetch active SupplierSelect trigger
#         # ---------------------------------------------------------
#         trigger = (
#             session.query(WorkflowTrigger)
#             .filter_by(
#                 bot_id=bot_id,
#                 tenant_id=tenant_id,
#                 trigger_type="supplier_select",
#                 status="active"     # IMPORTANT
#             )
#             .first()
#         )

#         if not trigger:
#             return {
#                 "status": "error",
#                 "message": "No active SupplierSelect trigger configured"
#             }

#         start_node_id = trigger.trigger_node_id
#         diagram_id = trigger.flow_id

#         logger.info(f"[SUPPLIER_TRIGGER] Using start node: {start_node_id} | flow_id={diagram_id}")

#         # ---------------------------------------------------------
#         # 2. Load workflow diagram version
#         # ---------------------------------------------------------
#         diagram = (
#             session.query(BotDiagram)
#             .filter_by(bot_id=bot_id, diagram_id=diagram_id)
#             .first()
#         )

#         if not diagram:
#             return {"status": "error", "message": "Workflow diagram not found"}

#         workflow_json = json.loads(diagram.diagram_json)

#         # MUST attach metadata
#         workflow_json["bot_id"] = bot_id
#         workflow_json["tenant_id"] = tenant_id
#         workflow_json["diagram_id"] = diagram_id

#         # ---------------------------------------------------------
#         # 3. Prepare trigger injection (VERY IMPORTANT)
#         # ---------------------------------------------------------
#         trigger_data = {
#             start_node_id: selected_supplier
#         }

#         # ---------------------------------------------------------
#         # 4. Execute workflow
#         # ---------------------------------------------------------
#         executor = WorkflowExecutor(
#             workflow_json=workflow_json,
#             enable_parallel=True,
#             enable_checkpointing=False
#         )

#         result = executor.execute(
#             trigger_data=trigger_data,
#             return_context=True
#         )

#         # Save run result to DB
#         executor.finalize_execution_record(result)
#         executor.shutdown()

#         return {
#             "status": "success",
#             "message": "Supplier workflow executed successfully",
#             "run_id": executor.execution_db_id,
#             "result": result.to_dict()
#         }

#     except Exception as e:
#         logger.exception("Error executing supplier select workflow")
#         return {"status": "error", "message": str(e)}
