from flask import Flask

from watermark_app.config import MAX_REQUEST_BYTES


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

    from watermark_app.routes import register_routes

    register_routes(app)
    return app
