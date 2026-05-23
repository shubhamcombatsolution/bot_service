# engine/registry.py



NODE_REGISTRY = {
    
}

def register_node(node_type):
    """Decorator to register node classes"""
    def decorator(cls):
        NODE_REGISTRY[node_type] = cls
        return cls
    return decorator