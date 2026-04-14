import logging
import threading

try:
    from flask import Flask, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from .config import cfg


def build_flask_app(engine):
    """
    Build and return the Flask application.
    The engine object is captured by the route closures; no circular module
    imports are needed because state constants are accessed via the instance.

    Args:
        engine: WakeLLM instance
    """
    app = Flask(__name__)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    @app.route('/wake', methods=['POST'])
    def wake():
        state = engine.get_state()
        if state == engine.STATE_RUNNING:
            return jsonify({"status": "already_running", "pod_id": engine.pod_id}), 200
        if state == engine.STATE_STARTING:
            return jsonify({"status": "starting"}), 202
        if state == engine.STATE_STOPPING:
            return jsonify({
                "status": "stopping",
                "message": "Pod is currently shutting down, retry shortly.",
            }), 503

        # STATE_STOPPED — kick off lifecycle in a background thread
        t = threading.Thread(target=engine.start_lifecycle, daemon=True, name="lifecycle")
        t.start()
        return jsonify({"status": "starting"}), 202

    @app.route('/status', methods=['GET'])
    def status():
        return jsonify({"state": engine.get_state(), "pod_id": engine.pod_id}), 200

    return app


def start_api_server(engine, config):
    """
    Start the Flask API server in a daemon thread (if enabled in config).

    Args:
        engine: WakeLLM instance
        config: Full config dict
    """
    if not cfg(config, 'api', 'enabled', True):
        return
    if not FLASK_AVAILABLE:
        print("[WARN] API server is enabled in config but Flask is not installed. "
              "Run: pip install flask")
        return

    host = cfg(config, 'api', 'host', '127.0.0.1')
    port = cfg(config, 'api', 'port', 8765)
    app  = build_flask_app(engine)
    print(f"[INFO] API server listening on http://{host}:{port} (POST /wake, GET /status)")

    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, use_reloader=False),
        daemon=True,
        name="api-server",
    )
    t.start()
