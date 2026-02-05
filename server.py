"""剧本信息展示网站：首页列出剧本，详情页展示场景与角色。"""

import json
from pathlib import Path

from flask import Flask, abort, render_template, send_from_directory

app = Flask(__name__)
# 剧本 JSON 在 data 目录；results 按 story_id 分子目录
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"


def scan_stories() -> list[dict]:
    """扫描 data 目录下所有 story__*.json，返回 [{id, name, cover_url, character_count, scene_count}, ...]。"""
    result = []
    if not DATA_DIR.is_dir():
        return result
    for path in sorted(DATA_DIR.glob("story__*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            story_id = path.stem.replace("story__", "", 1)
            characters = data.get("characters") or []
            scenes = data.get("scenes") or data.get("master") or []
            result.append({
                "id": story_id,
                "name": data.get("name", story_id),
                "cover_url": f"/results/{story_id}/covers/{story_id}.jpg",
                "character_count": len(characters),
                "scene_count": len(scenes),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


# step 内 type 对应的展示标签：memory=自动上下文，user=用户提示词
STEP_TYPE_LABELS = {"memory": "【自动上下文】", "user": "【用户提示词】"}


def _extract_step_blocks(step) -> list[dict]:
    """从单个 step 中按 type 拆成块，返回 [{ type, label, lines }, ...]。"""
    blocks = []
    if isinstance(step, list):
        for item in step:
            if not isinstance(item, dict) or "value" not in item:
                continue
            lines = [v for v in item["value"] if isinstance(v, str)]
            if not lines:
                continue
            t = item.get("type") or "memory"
            blocks.append({
                "type": t,
                "label": STEP_TYPE_LABELS.get(t, f"【{t}】"),
                "lines": lines,
            })
    elif isinstance(step, dict):
        lines = []
        if "value" in step:
            lines.extend(v for v in step["value"] if isinstance(v, str))
        if "prompts" in step:
            for p in step["prompts"]:
                if isinstance(p, dict) and "value" in p:
                    lines.extend(v for v in p["value"] if isinstance(v, str))
                elif isinstance(p, str):
                    lines.append(p)
        if "tasks" in step:
            lines.extend(t for t in step["tasks"] if isinstance(t, str))
        if lines:
            t = step.get("type") or "memory"
            blocks.append({
                "type": t,
                "label": STEP_TYPE_LABELS.get(t, f"【{t}】"),
                "lines": lines,
            })
    return blocks


def _build_scene_steps_display(scene: dict) -> list[dict]:
    """将场景的 steps 转为 [{ blocks: [{ type, label, lines }, ...] }, ...]，每个 step 可含多块。"""
    steps = scene.get("steps") or []
    result = []
    for step in steps:
        blocks = _extract_step_blocks(step)
        if blocks:
            result.append({"blocks": blocks})
    # 兼容旧版：无 steps 但有 prompts 时视为一个步骤，单块为自动上下文
    if not result and scene.get("prompts"):
        prompts = [p for p in scene["prompts"] if isinstance(p, str)]
        if prompts:
            result.append({
                "blocks": [{"type": "memory", "label": STEP_TYPE_LABELS["memory"], "lines": prompts}],
            })
    return result


def load_story(story_id: str) -> dict:
    """加载 data 目录下单个剧本 JSON，不存在或无效则 abort 404。统一使用 scenes 字段并规范化展示。"""
    path = DATA_DIR / f"story__{story_id}.json"
    if not path.is_file():
        abort(404)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        abort(404)
    # 场景：优先 scenes，兼容旧版 master
    raw_scenes = data.get("scenes") or data.get("master") or []
    scenes = []
    for s in raw_scenes:
        scenes.append({
            "id": s.get("id"),
            "name": s.get("name") or "",
            "steps_display": _build_scene_steps_display(s),
            "notes": s.get("notes") or [],
            "choices": s.get("choices") or {},
        })
    data["scenes"] = scenes
    data["cover_url"] = f"/results/{story_id}/covers/{story_id}.jpg"
    return data


@app.route("/")
def index():
    stories = scan_stories()
    return render_template("index.html", stories=stories)


@app.route("/results/<story_id>/characters/<path:filename>")
def character_image(story_id: str, filename: str):
    """提供 results/<story_id>/characters 下的角色图片。"""
    dir_path = RESULTS_DIR / story_id / "characters"
    if not dir_path.is_dir():
        abort(404)
    return send_from_directory(dir_path, filename, mimetype="image/png")


@app.route("/results/<story_id>/covers/<path:filename>")
def cover_image(story_id: str, filename: str):
    """提供 results/<story_id>/covers 下的剧本封面。"""
    dir_path = RESULTS_DIR / story_id / "covers"
    if not dir_path.is_dir():
        abort(404)
    return send_from_directory(dir_path, filename, mimetype="image/jpeg")


@app.route("/story/<story_id>")
def story_detail(story_id: str):
    story = load_story(story_id)
    return render_template("detail.html", story_id=story_id, story=story)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
