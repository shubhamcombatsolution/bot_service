import abc

class BaseNode(abc.ABC):
    def __init__(self, node_id, node_data):
        """
        Initialize base node.
        
        Args:
            node_id: Unique identifier for this node instance
            node_data: Dictionary containing node configuration
        """
        self.node_id = node_id
        self.node_data = node_data if node_data else {}
        
        # Support both formData structure and direct data
        self.form_data = self.node_data.get("formData", {})
        self.node_type = self.node_data.get("type")
        
    @abc.abstractmethod
    def execute(self, inputs):
        """
        Executes the node logic.
        Must return a dict or JSON-compatible object.
        """
        pass