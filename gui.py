#!/usr/bin/env python3
"""Local web GUI for editing config.yaml — the marketplace-watcher shopping
list and per-item filters. Saving commits + pushes config.yaml to GitHub so
the next scheduled Actions run picks up the change.

Run: python3 gui.py   then open http://localhost:5000
"""
import os
import subprocess
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for
from ruamel.yaml import YAML

app = Flask(__name__)
app.secret_key = os.urandom(24)  # local-only tool, session cookie just needs to survive the process
CONFIG_PATH = Path(__file__).parent / "config.yaml"
REPO_DIR = Path(__file__).parent

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096  # avoid ruamel wrapping long lines mid-string

# Field definitions per category: (config_key, label, input_type, help_text)
# input_type: text | number | list | checkbox
# help_text explains what the field actually does, shown under the input in the GUI.
GENERIC_FIELDS = [
    ("keywords", "Search keywords (one per line)", "list",
     "What gets typed into the site's search box. Each line is searched separately, "
     "results are combined. Keep these broad — narrow it down with the fields below "
     "instead, since the site's own search is fuzzy and won't exactly match what you type."),
    ("require_all_words", "Must contain ALL of these words (one per line)", "list",
     "A listing is only kept if its title contains every single word listed here. "
     "Use this to nail down an exact model/name made of several words, e.g. "
     "\"xbox\" + \"series\" + \"x\" so a listing needs all three, not just one."),
    ("require_any_words", "Must contain AT LEAST ONE of these words (one per line)", "list",
     "A listing is only kept if its title contains at least one of these words. "
     "Useful for confirming the listing is actually the right kind of thing, e.g. "
     "requiring \"montre\"/\"watch\"/\"orologio\" so a calculator with the same "
     "brand name doesn't slip through."),
    ("exclude_keywords", "Exclude if title contains (one per line)", "list",
     "Instant reject list. If a listing's title contains ANY of these words, it's "
     "thrown out no matter what else matches. Use this for accessories, wrong "
     "variants, games instead of consoles, scam red flags, etc."),
    ("price_min", "Min price (EUR)", "number",
     "Listings cheaper than this are ignored (useful for filtering out obvious "
     "scams or parts-only listings priced suspiciously low). Leave at 0 if you don't need a floor."),
    ("price_max", "Max price (EUR)", "number",
     "Your budget ceiling — listings above this price are ignored entirely."),
]

CATEGORY_FIELDS = {
    "electronics": GENERIC_FIELDS,
    "watches": [
        ("keywords", "Brand keywords (one per line)", "list",
         "Brand names to search for, e.g. \"seiko\", \"casio\". Each is searched separately."),
        ("require_any_words", "Must contain AT LEAST ONE of these words (one per line)", "list",
         "A listing is only kept if its title contains at least one of these — used here "
         "to confirm it's actually a watch (montre/watch/orologio/uhr/...), since brand "
         "names alone also match calculators, keyboards, cameras from the same manufacturer."),
        ("detail_keywords", "Nice-to-have detail keywords (one per line)", "list",
         "Words that make a listing more interesting if present (e.g. \"automatic\", "
         "\"day-date\") — currently informational only, doesn't filter anything out."),
        ("exclude_keywords", "Exclude if title contains (one per line)", "list",
         "Instant reject list — any of these words in the title and the listing is thrown "
         "out. Used to filter out calculators, digital watches, fakes, unrelated items."),
        ("price_min", "Min price (EUR)", "number", "Listings cheaper than this are ignored."),
        ("price_max", "Max price (EUR)", "number", "Your budget ceiling for this item."),
    ],
    "cars": [
        ("make", "Make (e.g. bmw)", "text", "The car manufacturer, lowercase, e.g. \"bmw\"."),
        ("model", "Model (e.g. 330i)", "text", "The specific model/trim, e.g. \"330i\"."),
        ("body", "Body/chassis code (e.g. f30)", "text",
         "The chassis/generation code, e.g. \"f30\" for 2012-2019 3 Series. Reference only "
         "right now — not yet used as an active filter by the search."),
        ("year_min", "Min year", "number", "Earliest first-registration year to accept."),
        ("year_max", "Max year", "number", "Latest first-registration year to accept."),
        ("price_min", "Min price (EUR)", "number", "Listings cheaper than this are ignored."),
        ("price_max", "Max price (EUR)", "number", "Your budget ceiling."),
        ("mileage_max_km", "Max mileage (km)", "number", "Listings above this mileage are ignored."),
        ("preferred_options", "Preferred options (one per line, for reference only)", "list",
         "Options you'd like to see (M Sport, xDrive, Head-Up Display, etc.) — informational "
         "only right now, doesn't filter anything out, just a reminder to yourself when reading alerts."),
        ("exclude_keywords", "Exclude if title contains (one per line)", "list",
         "Instant reject list — any of these words in the title/description and the "
         "listing is thrown out. Used for damage/salvage/parts-only red flags."),
    ],
}

DEFAULT_ADAPTERS_BY_CATEGORY = {
    "electronics": ["vinted"],
    "watches": ["vinted"],
    "cars": ["autoscout24"],
}

AVAILABLE_SITES = {
    "vinted": "Vinted (clothing, electronics, general second-hand)",
    "autoscout24": "AutoScout24 (cars)",
}


def get_custom_categories(config: dict) -> dict:
    """Custom categories live in config.yaml under settings.custom_categories:
    {name: {adapters: [...]}} — they use GENERIC_FIELDS for their form fields."""
    return config.get("settings", {}).get("custom_categories", {}) or {}


def all_category_names(config: dict) -> list:
    return list(CATEGORY_FIELDS.keys()) + list(get_custom_categories(config).keys())


def fields_for_category(category: str) -> list:
    return CATEGORY_FIELDS.get(category, GENERIC_FIELDS)


def adapters_for_category(config: dict, category: str) -> list:
    # Always return a fresh list, never the category's own list object — reusing
    # it directly would make ruamel.yaml emit a YAML anchor/alias between the
    # category definition and every item's `adapters` field, which is
    # confusing to hand-read and risks items appearing to share mutable state.
    if category in DEFAULT_ADAPTERS_BY_CATEGORY:
        return list(DEFAULT_ADAPTERS_BY_CATEGORY[category])
    custom = get_custom_categories(config)
    return list(custom.get(category, {}).get("adapters", []))


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f)


def _run(args):
    return subprocess.run(args, cwd=REPO_DIR, check=True, capture_output=True, text=True)


def git_commit_and_push(message: str) -> tuple[bool, str]:
    try:
        _run(["git", "add", "config.yaml"])
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR)
        if diff.returncode == 0:
            return True, "No changes to commit."
        _run(["git", "commit", "-m", message])

        # data/watcher.db is updated by scheduled GitHub Actions runs, which
        # can race with a save here — retry with a rebase if the push is
        # rejected for being behind, rather than failing the whole save.
        for attempt in range(3):
            try:
                _run(["git", "push"])
                return True, "Saved and pushed to GitHub."
            except subprocess.CalledProcessError as push_err:
                if attempt == 2:
                    raise
                _run(["git", "pull", "--rebase", "origin", "main"])
        return True, "Saved and pushed to GitHub."
    except subprocess.CalledProcessError as e:
        return False, f"Git error: {e.stderr or e.stdout}"


def load_env_file() -> dict:
    """Parse .env (KEY=VALUE per line) without needing python-dotenv."""
    env_path = REPO_DIR / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def run_watcher_now() -> tuple[bool, str]:
    env = os.environ.copy()
    env.update(load_env_file())
    try:
        result = subprocess.run(
            ["python3", "run.py"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=20 * 60,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Run timed out after 20 minutes."


def list_to_text(values) -> str:
    return "\n".join(values) if values else ""


def text_to_list(text: str) -> list:
    return [line.strip() for line in text.splitlines() if line.strip()]


GREETING_NAME = os.environ.get("GREETING_NAME", "Alex")


@app.route("/")
def index():
    if not session.get("welcomed"):
        session["welcomed"] = True
        return render_template("welcome.html", name=GREETING_NAME)

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
    fields = fields_for_category(category)
    return render_template(
        "edit_item.html",
        item=item,
        category=category,
        fields=fields,
        all_categories=all_category_names(config),
        list_to_text=list_to_text,
    )


@app.route("/category/new", methods=["GET"])
def new_category_form():
    return render_template("new_category.html", available_sites=AVAILABLE_SITES)


@app.route("/category/new", methods=["POST"])
def create_category():
    config = load_config()
    name = request.form.get("name", "").strip().lower().replace(" ", "-")
    sites = request.form.getlist("adapters")

    if not name:
        return "Category name is required", 400
    if not sites:
        return "Pick at least one site to search", 400
    if name in all_category_names(config):
        return f"Category '{name}' already exists", 400

    settings = config.setdefault("settings", {})
    custom = settings.setdefault("custom_categories", {})
    custom[name] = {"adapters": sites}

    save_config(config)
    ok, msg = git_commit_and_push(f"Add custom category: {name}")
    return redirect(url_for("edit_item", category=name, flash=msg, flash_ok=int(ok)))


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
        "adapters": adapters_for_category(config, category),
    }

    for key, _, input_type, *_rest in fields_for_category(category):
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
        # Preserve pause state across an edit — editing filters shouldn't
        # silently un-pause an item you deliberately paused.
        if items[idx].get("enabled", True) is False:
            new_item["enabled"] = False
        items[idx] = new_item

    save_config(config)
    ok, msg = git_commit_and_push(f"Update shopping list item: {item_id}")
    return redirect(url_for("index", flash=msg, flash_ok=int(ok)))


@app.route("/run-now", methods=["POST"])
def run_now():
    ok, output = run_watcher_now()
    return render_template("run_result.html", ok=ok, output=output)


@app.route("/item/<item_id>/toggle", methods=["POST"])
def toggle_item(item_id):
    config = load_config()
    items = config.get("items", [])
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return "Item not found", 404

    currently_enabled = item.get("enabled", True) is not False
    item["enabled"] = not currently_enabled

    save_config(config)
    state = "paused" if currently_enabled else "resumed"
    ok, msg = git_commit_and_push(f"{'Pause' if currently_enabled else 'Resume'} shopping list item: {item_id}")
    return redirect(url_for("index", flash=f"{item_id} {state}." if ok else msg, flash_ok=int(ok)))


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
