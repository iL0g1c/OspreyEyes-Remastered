"""Flask application that renders a force-directed graph of shared callsigns."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from .graph_processing import GraphProcessingService

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = None
app.config["UPLOAD_FOLDER"] = Path(tempfile.gettempdir()) / "callsign_graph_uploads"
app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

processor = GraphProcessingService()


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/upload")
def upload() -> tuple:
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    filename = secure_filename(file.filename or "export.json")
    tmp_path = app.config["UPLOAD_FOLDER"] / f"{filename}.{os.getpid()}.{os.urandom(4).hex()}"
    with tmp_path.open("wb") as handle:
        shutil.copyfileobj(file.stream, handle)
    job_id = processor.start_job(tmp_path)
    return jsonify({"jobId": job_id})


@app.get("/api/job/<job_id>")
def job_status(job_id: str):
    job = processor.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


@app.delete("/api/job/<job_id>")
def drop_job(job_id: str):
    processor.drop_job(job_id)
    return ("", 204)


@app.get("/api/job/<job_id>/component/<component_id>")
def component(job_id: str, component_id: str):
    limit_param = request.args.get("limit")
    limit: Optional[int] = None
    if limit_param:
        try:
            limit = max(0, int(limit_param))
        except ValueError:
            return jsonify({"error": "limit must be numeric"}), 400
    payload = processor.get_component(job_id, component_id, limit if limit else None)
    if not payload:
        return jsonify({"error": "Component not found"}), 404
    return jsonify(payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
