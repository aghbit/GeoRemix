from flask import Blueprint, jsonify, current_app
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

rounds_bp = Blueprint("rounds", __name__)

# Helper functions to load metadata, nodes, and links
def load_round_level_data(round_num, level_num, file_type):
    """Load data from specific round/level folder"""
    file_path = f"rounds/round_{round_num}/level_{level_num}/{file_type}.json"
    try:
        with open(file_path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def load_metadata(round_num, level_num):
    """Load metadata from specific round/level"""
    return load_round_level_data(round_num, level_num, "metadata")

def load_nodes(round_num, level_num):
    """Load nodes from specific round/level"""
    return load_round_level_data(round_num, level_num, "nodes")

def load_links(round_num, level_num):
    """Load links from specific round/level"""
    return load_round_level_data(round_num, level_num, "links")

def get_round_levels(round_num):
    """Get all level numbers for a specific round"""
    round_path = f"rounds/round_{round_num}"
    if not os.path.exists(round_path):
        return []

    levels = []
    for item in os.listdir(round_path):
        item_path = os.path.join(round_path, item)
        if os.path.isdir(item_path) and item.startswith("level_"):
            try:
                level_num = int(item.split("_")[1])
                levels.append(level_num)
            except (IndexError, ValueError):
                continue

    return sorted(levels)

# Endpoints to serve metadata and nodes for levels
@rounds_bp.route("/round<int:round_num>/metadata")
def get_round_metadata(round_num):
    """Get metadata for all levels in a specific round"""
    levels = get_round_levels(round_num)

    if not levels:
        return jsonify({"error": "Round not found or no levels available"}), 404

    all_metadata = []
    for level_num in levels:
        metadata = load_metadata(round_num, level_num)
        if metadata:
            all_metadata.append(metadata)

    return jsonify(all_metadata)

@rounds_bp.route("/round<int:round_num>/level<int:level_num>/metadata")
def get_level_metadata(round_num, level_num):
    """Get metadata for a specific round and level"""
    metadata = load_metadata(round_num, level_num)
    if metadata:
        return jsonify(metadata)
    return jsonify({"error": "Metadata not found"}), 404

@rounds_bp.route("/round<int:round_num>/level<int:level_num>/nodes/<node_id>")
def get_level_node(round_num, level_num, node_id):
    """Get a specific node for a round/level"""
    nodes = load_nodes(round_num, level_num)
    links_data = load_links(round_num, level_num)

    if not nodes or not links_data:
        return jsonify({"error": "Level data not found"}), 404

    node_data = next((node for node in nodes if str(node["id"]) == str(node_id)), None)
    if not node_data:
        return jsonify({"error": "Node not found"}), 404

    node_links = links_data.get(str(node_id), [])

    links = []
    for linked_node_id in node_links:
        linked_node = next(
            (node for node in nodes if str(node["id"]) == str(linked_node_id)), None
        )
        if linked_node:
            links.append(
                {
                    "nodeId": str(linked_node_id),
                    "gps": linked_node["gps"],
                }
            )

    # Access IMAGE_ENDPOINT from the app's config
    image_endpoint = current_app.config["IMAGE_ENDPOINT"]

    response_node = {
        "id": str(node_data["id"]),
        "panorama": image_endpoint + str(node_data["panorama"]),
        "links": links,
        "gps": node_data["gps"],
        "sphereCorrection": {"pan": str(node_data["sphereCorrection"]["pan"]) + "deg"},
    }

    return jsonify(response_node)

@rounds_bp.route("/round<int:round_num>/level<int:level_num>/nodes")
def get_level_nodes(round_num, level_num):
    """Get all nodes for a specific round/level"""
    nodes = load_nodes(round_num, level_num)
    links_data = load_links(round_num, level_num)

    if not nodes or not links_data:
        return jsonify({"error": "Level data not found"}), 404

    response_nodes = []
    for node_data in nodes:
        node_id = str(node_data["id"])

        node_links = links_data.get(node_id, [])

        links = []
        for linked_node_id in node_links:
            linked_node = next(
                (node for node in nodes if str(node["id"]) == str(linked_node_id)), None
            )
            if linked_node:
                links.append(
                    {
                        "nodeId": str(linked_node_id),
                        "gps": linked_node["gps"],
                    }
                )

        # Access IMAGE_ENDPOINT from the app's config
        image_endpoint = current_app.config["IMAGE_ENDPOINT"]

        response_node = {
            "id": node_id,
            "panorama": image_endpoint + str(node_data["panorama"]),
            "links": links,
            "gps": node_data["gps"],
            "panoData": {
                "poseHeading": (node_data["sphereCorrection"]["pan"]) / 180 * 3.14
            },
        }
        response_nodes.append(response_node)

    return jsonify(response_nodes)
