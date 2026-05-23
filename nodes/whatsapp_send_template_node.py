from engine.base_node import BaseNode
from engine.registry import register_node
from engine.export_strategies.whatsapp_strategy import WhatsAppExportStrategy
from nodes.whatsapp_node_helpers import (
    get_tenant_id,
    infer_whatsapp_recipient,
    resolve_form_data,
)


@register_node("whatsappSendTemplateNode")
class WhatsappSendTemplateNode(BaseNode):
    """Send a WhatsApp template message."""

    def execute(self, inputs):
        form_data = resolve_form_data(self.form_data or {}, inputs)
        tenant_id = get_tenant_id(inputs, form_data)
        if not tenant_id:
            raise ValueError("whatsappSendTemplateNode: Missing tenant_id")

        recipient = form_data.get("to") or form_data.get("send_to") or infer_whatsapp_recipient(inputs)
        template_name = form_data.get("template_name")

        if not recipient:
            raise ValueError("whatsappSendTemplateNode: Missing recipient phone number")
        if not template_name:
            raise ValueError("whatsappSendTemplateNode: 'template_name' is required")

        strategy = WhatsAppExportStrategy()
        payload = {
            **form_data,
            "type": "whatsapp",
            "export_mode": "whatsapp",
            "to": recipient,
            "template_name": template_name,
            "template_language": form_data.get("template_language") or "en_US",
            "wait_for_reply": False,
        }

        result = strategy.send(str(tenant_id), payload)
        return {
            "status": "success",
            "node": "whatsappSendTemplateNode",
            "recipient": str(recipient),
            "template_name": str(template_name),
            "result": result,
        }
