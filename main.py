"""Companion AI CRUD server (FastAPI).

Run:  pip install fastapi uvicorn
      python main.py
Open: http://localhost:8000       (app)
      http://localhost:8000/docs  (API docs)
"""
import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
INDEX_FILE = BASE_DIR / "index.html"

app = FastAPI(title="Companion AI", description="CRUD API for AI companions")


# ---- Models ----
class CompanionIn(BaseModel):
    name: str = Field(..., max_length=60)
    avatar: str = Field("", max_length=8)
    role: str = Field("Friend", max_length=30)
    personality: str = Field("Friendly", max_length=30)
    description: str = Field("", max_length=1000)
    active: bool = True

    @field_validator("name")
    @classmethod
    def name_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class Companion(CompanionIn):
    id: str
    createdAt: int
    updatedAt: int


# ---- Storage (JSON file) ----
def load() -> list[dict]:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(items: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def find_index(items: list[dict], companion_id: str) -> int:
    for i, c in enumerate(items):
        if c["id"] == companion_id:
            return i
    raise HTTPException(status_code=404, detail="Companion not found")


# ---- Routes ----
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_FILE)


@app.get("/api/companions", response_model=list[Companion])
def list_companions():
    return load()


@app.get("/api/companions/{companion_id}", response_model=Companion)
def get_companion(companion_id: str):
    items = load()
    return items[find_index(items, companion_id)]


@app.post("/api/companions", response_model=Companion, status_code=201)
def create_companion(data: CompanionIn):
    items = load()
    ts = now_ms()
    item = {"id": str(uuid.uuid4()), **data.model_dump(), "createdAt": ts, "updatedAt": ts}
    items.append(item)
    save(items)
    return item


@app.put("/api/companions/{companion_id}", response_model=Companion)
def update_companion(companion_id: str, data: CompanionIn):
    items = load()
    i = find_index(items, companion_id)
    items[i] = {**items[i], **data.model_dump(), "updatedAt": now_ms()}
    save(items)
    return items[i]


@app.delete("/api/companions/{companion_id}", status_code=204)
def delete_companion(companion_id: str):
    items = load()
    items.pop(find_index(items, companion_id))
    save(items)
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
