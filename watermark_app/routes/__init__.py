from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from watermark_app.routes.collage import collage
from watermark_app.routes.single import single
from watermark_app.routes.social import social


def register_routes(app: Flask) -> None:
    app.register_blueprint(single)
    app.register_blueprint(collage)
    app.register_blueprint(social)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify(error="Upload exceeds the 64 MB request limit."), 413
