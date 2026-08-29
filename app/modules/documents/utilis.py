import ulid

_monotonic_factory = ulid.monotonic

# Utility to create ULID
def generate_ulid() -> str:
    return str(_monotonic_factory.new())

# Utility to serialize a content block for API responses
def serialize_block(block) -> dict:
    return {
        "id": str(block.id),
        "type": block.block_type,
        "position": block.position,
        "data": block.data,
    }

# Utility to build a single node's response, optionally with pre-fetched children
def build_node_response(node, document, blocks, children=None) -> dict:
    return {
        "node_id": node.node_id,
        "document_id": str(document.id),
        "title": document.title,
        "description": document.description,
        "document_type": document.document_type,
        "parent_node_id": node.parent_node_id,
        "blocks": [serialize_block(block) for block in blocks],
        "children": children or []
    }

# Utility to build a tree response from a flat list of (node, document) rows
def build_tree_response(rows, blocks_map=None):
    if not rows:
        return None

    blocks_map = blocks_map or {}
    node_map = {}

    # Build dictionary
    for node, document in rows:
        node_map[node.node_id] = build_node_response(node, document, blocks_map.get(document.id, []))

    # The FIRST node in ordered rows is always the subtree root
    root_node_id = rows[0][0].node_id

    # Attach children
    for node, _ in rows:
        if node.parent_node_id and node.parent_node_id in node_map:
            node_map[node.parent_node_id]["children"].append(
                node_map[node.node_id]
            )

    return node_map[root_node_id]
