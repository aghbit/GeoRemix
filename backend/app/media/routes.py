import os
from flask import Blueprint, current_app, send_from_directory
from flask_cors import cross_origin
from dotenv import load_dotenv

load_dotenv()

MEDIA_DIRECTORY = os.getenv("MEDIA_DIRECTORY", "images")
THUMBNAIL_DIRECTORY = os.getenv("THUMBNAIL_DIRECTORY", "thumbnails")
CLIENT_ORIGIN = os.getenv("CLIENT_ORIGIN", "http://localhost:5173")

media_bp = Blueprint("media", __name__)


def _resolve_directory(directory: str) -> str:
    if os.path.isabs(directory):
        return directory
    app_root = current_app.root_path
    project_root = os.path.abspath(os.path.join(app_root, os.pardir))
    return os.path.abspath(os.path.join(project_root, directory))


@media_bp.route("/images/<path:filename>")
@cross_origin(origins=CLIENT_ORIGIN, supports_credentials=True)
def get_image(filename):
    """Serve images from the images directory stored outside the package."""
    return send_from_directory(_resolve_directory(MEDIA_DIRECTORY), filename)


@media_bp.route("/thumbnails/<path:filename>")
def get_thumbnail(filename):
    """Serve thumbnail images from the thumbnails directory."""
    return send_from_directory(_resolve_directory(THUMBNAIL_DIRECTORY), filename)
