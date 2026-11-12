import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__)
allowed_origins = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
frontend_origin = os.environ.get("FRONTEND_ORIGIN")
if frontend_origin:
    allowed_origins.append(frontend_origin.rstrip("/"))

CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins=allowed_origins,
    max_http_buffer_size=8192,
)

DEMO_USERS = {"player1": "pass1", "player2": "pass2"}
MAX_MESSAGE_LENGTH = 1000


@app.post("/api/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="Expected a JSON object."), 400

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(status="error", message="Enter a username and password."), 400
    if DEMO_USERS.get(username) != password:
        return jsonify(status="error", message="Invalid demo credentials."), 401
    return jsonify(status="success", username=username)


@socketio.on("send_message")
def handle_message(data):
    if not isinstance(data, dict):
        return {"status": "error", "message": "Expected a message object."}

    user = data.get("user")
    text = data.get("text")
    if not isinstance(user, str) or user not in DEMO_USERS:
        return {"status": "error", "message": "Unknown demo user."}
    if not isinstance(text, str) or not text.strip():
        return {"status": "error", "message": "Message must not be empty."}
    text = text.strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        return {"status": "error", "message": "Message is too long."}

    emit("receive_message", {"user": user, "text": text}, broadcast=True)
    return {"status": "success"}


if __name__ == "__main__":
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
