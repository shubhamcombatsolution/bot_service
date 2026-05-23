from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.whatsapp_strategy import WhatsAppExportStrategy
from nodes.whatsapp_node_helpers import (
    get_tenant_id,
    infer_media_id,
    resolve_form_data,
)


@register_node("whatsappDeleteMediaNode")
class WhatsappDeleteMediaNode(BaseNode):
    """Delete WhatsApp media by media_id."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("whatsappDeleteMediaNode: Missing tenant_id")

        media_id = form_data.get("media_id") or infer_media_id(inputs)
        if not media_id:
            raise ValueError("whatsappDeleteMediaNode: Missing media_id")

        strategy = WhatsAppExportStrategy()
        result = strategy.delete_media(
            str(tenant_id),
            {
                **form_data,
                "media_id": str(media_id),
            },
        )

        return {
            "status": "success",
            "node": "whatsappDeleteMediaNode",
            "result": result,
            "media_id": str(media_id),
        }
