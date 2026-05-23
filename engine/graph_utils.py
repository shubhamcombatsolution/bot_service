# ===== FILE: engine/graph_utils.py =====
"""Graph utilities for workflow execution"""

from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def build_graph(nodes, edges):
    """Build adjacency lists from nodes and edges - preserving full edge objects"""
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
   
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
       
        # Store the FULL edge object (critical!)
        edge_obj = {
            "source": source,
            "target": target,
            "sourceHandle": edge.get("sourceHandle"),
            "targetHandle": edge.get("targetHandle"),
            "id": edge.get("id"),
            # add any other fields you use in UI
        }
       
        outgoing[source].append(edge_obj)   # ← now list of dicts
        incoming[target].append(edge_obj)   # ← now list of dicts
   
    return {
        "outgoing": dict(outgoing),
        "incoming": dict(incoming)
    }


def compute_dependencies(graph):
    """
    Compute dependency count (in-degree) for each node.
    Returns:
        dependencies: dict[node_id -> count]
        ready_nodes: list[node_id with 0 dependencies]
    """
    incoming = graph["incoming"]
    outgoing = graph["outgoing"]
    all_nodes = set(incoming.keys()) | set(outgoing.keys())
   
    # Count incoming edges (each edge object = 1 dependency)
    dependencies = {}
    for node in all_nodes:
        edges = incoming.get(node, [])
        dependencies[node] = len(edges)  # ← count edge objects, not source strings
   
    ready_nodes = [node for node, count in dependencies.items() if count == 0]
    return dependencies, ready_nodes


def topological_sort(graph):
    incoming = graph["incoming"]
    outgoing = graph["outgoing"]
    all_nodes = set(incoming.keys()) | set(outgoing.keys())
   
    indegree = {node: len(incoming.get(node, [])) for node in all_nodes}
    queue = deque([n for n, d in indegree.items() if d == 0])
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
       
        for edge in outgoing.get(node, []):
            neighbor = edge["target"] if isinstance(edge, dict) else edge
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
   
    if len(order) != len(all_nodes):
        raise Exception("Workflow contains cycles - cannot execute")
   
    logger.info(f"Execution order: {order}")
    return order
# def build_graph(nodes, edges):
#     """Build adjacency lists from nodes and edges"""
#     outgoing = defaultdict(list)
#     incoming = defaultdict(list)
    
#     for edge in edges:
#         s = edge["source"]
#         t = edge["target"]
#         outgoing[s].append(t)
#         incoming[t].append(s)
    
#     return {"outgoing": outgoing, "incoming": incoming}

# def compute_dependencies(graph):
#     """
#     Compute dependency count (in-degree) for each node.
#     Returns:
#         dependencies: dict[node_id -> count]
#         ready_nodes: list[node_id with 0 dependencies]
#     """
#     all_nodes = set(graph["incoming"]) | set(graph["outgoing"])
#     dependencies = {n: len(graph["incoming"].get(n, [])) for n in all_nodes}
#     ready_nodes = [n for n, d in dependencies.items() if d == 0]
#     return dependencies, ready_nodes


# def topological_sort(graph):
#     """
#     Perform topological sort to get execution order.
#     Returns list of node IDs in execution order.
#     """
#     # Calculate in-degree for all nodes
#     all_nodes = set(graph["incoming"]) | set(graph["outgoing"])
#     indegree = {n: len(graph["incoming"].get(n, [])) for n in all_nodes}
    
#     # Start with nodes that have no incoming edges (trigger nodes)
#     queue = deque([n for n, d in indegree.items() if d == 0])
#     order = []
    
#     while queue:
#         node = queue.popleft()
#         order.append(node)
        
#         # Reduce in-degree for neighbors
#         for neighbor in graph["outgoing"].get(node, []):
#             indegree[neighbor] -= 1
#             if indegree[neighbor] == 0:
#                 queue.append(neighbor)
    
#     # Check for cycles
#     if len(order) != len(all_nodes):
#         raise Exception("Workflow contains cycles - cannot execute")
    
#     logger.info(f"Execution order: {order}")
#     return order

import jwt

def decode_token(token, secret=None, algorithms=["HS256"]):
    """
    Decode JWT token and return the payload as a dict.
    If secret is None, assumes token is unsigned or uses public key verification.
    """
    try:
        return jwt.decode(token, secret, algorithms=algorithms, options={"verify_signature": False})
    except Exception as e:
        raise ValueError(f"Failed to decode JWT: {e}")

