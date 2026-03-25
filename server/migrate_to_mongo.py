from __future__ import annotations

import json
import os
from pathlib import Path

from pymongo import MongoClient


DEFAULT_MONGO_URI = "mongodb://127.0.0.1:27017"
DEFAULT_DATABASE_NAME = "todo_app"
DEFAULT_COLLECTION_NAME = "tasks"
DEFAULT_JSON_PATH = Path(__file__).resolve().parent / "data" / "tasks.json"


def load_tasks(json_path: Path) -> list[dict]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload.get("tasks", [])


def main() -> None:
    json_path = Path(os.getenv("TASKS_JSON_PATH", str(DEFAULT_JSON_PATH)))
    mongo_uri = os.getenv("MONGODB_URI", DEFAULT_MONGO_URI)
    database_name = os.getenv("MONGODB_DB", DEFAULT_DATABASE_NAME)
    collection_name = os.getenv("MONGODB_COLLECTION", DEFAULT_COLLECTION_NAME)

    tasks = load_tasks(json_path)
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    collection = client[database_name][collection_name]

    # Mirror the app's storage format and keep task ids stable in Mongo.
    for task in tasks:
        document = dict(task)
        document["_id"] = task["id"]
        collection.replace_one({"_id": document["_id"]}, document, upsert=True)

    print(f"Migrated {len(tasks)} task(s) into {database_name}.{collection_name}.")


if __name__ == "__main__":
    main()
