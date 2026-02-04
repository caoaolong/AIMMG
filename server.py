"""剧本信息展示网站：首页列出剧本，详情页展示场景与角色。"""

import json
from pathlib import Path

from flask import Flask, abort, render_template, send_from_directory

app = Flask(__name__)
# 剧本 JSON 与资源目录（默认与 server.py 同目录）
STORIES_DIR = Path(__file__).resolve().parent
RESULTS_CHARACTERS_DIR = STORIES_DIR / "results" / "characters"


def scan_stories() -> list[dict]:
    """扫描目录下所有 story__*.json，返回 [{id, name}, ...]。"""
    result = []
    for path in sorted(STORIES_DIR.glob("story__*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            story_id = path.stem.replace("story__", "", 1)
            result.append({"id": story_id, "name": data.get("name", story_id)})
        except (json.JSONDecodeError, OSError):
            continue
    return result


def load_story(story_id: str) -> dict:
    """加载单个剧本 JSON，不存在或无效则 abort 404。"""
    path = STORIES_DIR / f"story__{story_id}.json"
    if not path.is_file():
        abort(404)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        abort(404)


@app.route("/")
def index():
    stories = scan_stories()
    return render_template("index.html", stories=stories)


@app.route("/results/characters/<path:filename>")
def character_image(filename: str):
    """提供 results/characters 下的角色图片。"""
    if not RESULTS_CHARACTERS_DIR.is_dir():
        abort(404)
    return send_from_directory(RESULTS_CHARACTERS_DIR, filename, mimetype="image/png")


@app.route("/story/<story_id>")
def story_detail(story_id: str):
    story = load_story(story_id)
    return render_template("detail.html", story_id=story_id, story=story)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
