from abc import ABC, abstractmethod

class IExportStrategy(ABC):
    """Interface for all export strategies."""

    @abstractmethod
    def send(self, tenant_id: str, form_data: dict) -> dict:
        """Perform the export action (e.g., send email, WhatsApp msg, etc.)."""
        pass
