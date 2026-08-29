import ulid

_monotonic_factory = ulid.monotonic

# Utility to create ULID
def generate_ulid() -> str:
    return str(_monotonic_factory.new())

# Utility to build a tree response
def build_tree_response(rows):
    if not rows:
        return None

    node_map = {}

    # Build dictionary
    for node, document in rows:
        node_map[node.node_id] = {
            "node_id": node.node_id,
            "title": document.title,
            "content": document.content,
            "parent_node_id": node.parent_node_id,
            "children": []
        }

    # The FIRST node in ordered rows is always the subtree root
    root_node_id = rows[0][0].node_id

    # Attach children
    for node, _ in rows:
        if node.parent_node_id and node.parent_node_id in node_map:
            node_map[node.parent_node_id]["children"].append(
                node_map[node.node_id]
            )

    return node_map[root_node_id]