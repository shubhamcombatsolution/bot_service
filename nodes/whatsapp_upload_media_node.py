from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.whatsapp_strategy import WhatsAppExportStrategy
from nodes.whatsapp_node_helpers import get_tenant_id, resolve_form_data


@register_node("whatsappUploadMediaNode")
class WhatsappUploadMediaNode(BaseNode):
    """Upload media to WhatsApp Cloud API and return media_id."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("whatsappUploadMediaNode: Missing tenant_id")

        strategy = WhatsAppExportStrategy()
        result = strategy.upload_media(str(tenant_id), form_data)

        return {
            "status": "success",
            "node": "whatsappUploadMediaNode",
            "result": result,
            "media_id": result.get("media_id"),
        }


