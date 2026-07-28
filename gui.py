#!/usr/bin/env python3
"""Local web GUI for editing config.yaml — the marketplace-watcher shopping
list and per-item filters. Saving commits + pushes config.yaml to GitHub so
the next scheduled Actions run picks up the change.

Run: python3 gui.py   then open http://localhost:5000
"""
import subprocess
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from ruamel.yaml import YAML

app = Flask(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
REPO_DIR = Path(__file__).parent

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096  # avoid ruamel wrapping long lines mid-string

# Field definitions per category: (config_key, label, input_type)
# input_type: text | number | list | checkbox
CATEGORY_FIELDS = {
    "electronics": [
        ("keywords", "Search keywords (one per line)", "list"),
        ("require_all_words", "Must contain ALL of these words (one per line)", "list"),
        ("require_any_words", "Must contain AT LEAST ONE of these words (one per line)", "list"),
        ("exclude_keywords", "Exclude if title contains (one per line)", "list"),
        ("price_min", "Min price (EUR)", "number"),
        ("price_max", "Max price (EUR)", "number"),
    ],
    "watches": [
        ("keywords", "Brand keywords (one per line)", "list"),
        ("require_any_words", "Must contain AT LEAST ONE of these words (one per line)", "list"),
        ("detail_keywords", "Nice-to-have detail keywords (one per line)", "list"),
        ("exclude_keywords", "Exclude if title contains (one per line)", "list"),
        ("price_min", "Min price (EUR)", "number"),
        ("price_max", "Max price (EUR)", "number"),
    ],
    "cars": [
        ("make", "Make (e.g. bmw)", "text"),
        ("model", "Model (e.g. 330i)", "text"),
        ("body", "Body/chassis code (e.g. f30)", "text"),
        ("year_min", "Min year", "number"),
        ("year_max", "Max year", "number"),
        ("price_min", "Min price (EUR)", "number"),
        ("price_max", "Max price (EUR)", "number"),
        ("mileage_max_km", "Max mileage (km)", "number"),
        ("preferred_options", "Preferred options (one per line, for reference only)", "list"),
        ("exclude_keywords", "Exclude if title contains (one per line)", "list"),
    ],
}

ADAPTERS_BY_CATEGORY = {
    "electronics": ["vinted"],
    "watches": ["vinted"],
    "cars": ["autoscout24"],
}


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f)


def git_commit_and_push(message: str) -> tuple[bool, str]:
    try:
        subprocess.run(["git", "add", "config.yaml"], cwd=REPO_DIR, check=True, capture_output=True, text=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR)
        if diff.returncode == 0:
            return True, "No changes to commit."
        subprocess.run(["git", "commit", "-m", message], cwd=REPO_DIR, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], cwd=REPO_DIR, check=True, capture_output=True, text=True)
        return True, "Saved and pushed to GitHub."
    except subprocess.CalledProcessError as e:
        return False, f"Git error: {e.stderr or e.stdout}"


def list_to_text(values) -> str:
    return "\n".join(values) if values else ""


def text_to_list(text: str) -> list:
    return [line.strip() for line in text.splitlines() if line.strip()]


@app.route("/")
def index():
    config = load_config()
    return render_template(
        "index.html",
        items=config.get("items", []),
        settings=config.get("settings", {}),
    )


@app.route("/item/new", methods=["GET"])
@app.route("/item/<item_id>/edit", methods=["GET"])
def edit_item(item_id=None):
    config = load_config()
    item = None
    if item_id:
        item = next((i for i in config["items"] if i["id"] == item_id), None)
        if item is None:
            return "Item not found", 404
    category = request.args.get("category", item["category"] if item else "electronics")
    fields = CATEGORY_FIELDS.get(category, [])
    return render_template(
        "edit_item.html",
        item=item,
        category=category,
        fields=fields,
        all_categories=list(CATEGORY_FIELDS.keys()),
        list_to_text=list_to_text,
    )


@app.route("/item/save", methods=["POST"])
def save_item():
    config = load_config()
    form = request.form
    item_id = form.get("id", "").strip()
    category = form.get("category")
    is_new = form.get("is_new") == "1"
    original_id = form.get("original_id", "").strip()

    if not item_id:
        return "Item id is required", 400

    new_item = {
        "id": item_id,
        "label": form.get("label", item_id),
        "category": category,
        "adapters": ADAPTERS_BY_CATEGORY.get(category, []),
    }

    for key, _, input_type in CATEGORY_FIELDS.get(category, []):
        raw = form.get(key, "")
        if input_type == "list":
            new_item[key] = text_to_list(raw)
        elif input_type == "number":
            new_item[key] = int(raw) if raw.strip() else None
        else:
            new_item[key] = raw.strip()

    items = config.setdefault("items", [])
    if is_new:
        if any(i["id"] == item_id for i in items):
            return f"Item id '{item_id}' already exists", 400
        items.append(new_item)
    else:
        idx = next((n for n, i in enumerate(items) if i["id"] == original_id), None)
        if idx is None:
            return "Item to edit not found", 404
        items[idx] = new_item

    save_config(config)
    ok, msg = git_commit_and_push(f"Update shopping list item: {item_id}")
    return redirect(url_for("index", flash=msg, flash_ok=int(ok)))


@app.route("/item/<item_id>/delete", methods=["POST"])
def delete_item(item_id):
    config = load_config()
    items = config.get("items", [])
    config["items"] = [i for i in items if i["id"] != item_id]
    save_config(config)
    ok, msg = git_commit_and_push(f"Remove shopping list item: {item_id}")
    return redirect(url_for("index", flash=msg, flash_ok=int(ok)))


if __name__ == "__main__":
    app.run(debug=False, port=5000)
