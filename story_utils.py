import json
import dotenv
from pathlib import Path
import alibabacloud_oss_v2 as oss
import requests
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.rule import Rule
from rich.table import Table
import os
dotenv.load_dotenv()

credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
cfg = oss.config.load_default()
cfg.credentials_provider = credentials_provider
cfg.region = "cn-beijing"
cfg.endpoint = "oss-cn-beijing.aliyuncs.com"
client = oss.Client(config=cfg)

parser = argparse.ArgumentParser()

STATUS_TEXT = {"running": "进行中", "succeeded": "成功", "failed": "失败"}

NANO_BANANA_API_KEY = os.getenv("NANO_BANANA_API_KEY")
NANO_BANANA_API_URL = os.getenv("NANO_BANANA_API_URL")
OSS_URL = os.getenv("OSS_URL")
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
console = Console()


def _download_image(url: str, save_path: Path) -> None:
    """下载图片并保存到指定路径。"""
    r = requests.get(url, stream=True)
    r.raise_for_status()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def _parse_sse_line(line: str) -> dict | None:
    """解析单行 SSE data，返回 JSON 或 None。"""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _load_story(story_id: str) -> dict:
    """加载故事 JSON，只读一次。"""
    path = Path(__file__).resolve().parent / f"story__{story_id}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_image(
    prompt: str,
    urls: list[str],
    save_path: Path,
    *,
    aspect_ratio: str = "9:16",
    image_size: str = "1K",
    request_title: str = "请求参数",
    show_request_panel: bool = True,
) -> str:
    """调用绘图 API 生成图片并保存到指定路径。返回图片 URL，失败返回空字符串。"""
    request_body = {
        "model": "nano-banana-pro",
        "urls": urls,
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "imageSize": image_size,
    }
    if show_request_panel:
        console.print(Panel(
            f"[bold]model[/bold] {request_body['model']}\n"
            f"[bold]aspectRatio[/bold] {request_body['aspectRatio']}  [bold]imageSize[/bold] {request_body['imageSize']}\n"
            f"[bold]urls[/bold]\n  " + "\n  ".join(request_body["urls"] or ["(无参考图)"]) + "\n"
            f"[bold]prompt[/bold]\n  " + request_body["prompt"].replace("\n", "\n  "),
            title=f"[yellow]{request_title}[/yellow]",
            border_style="yellow",
        ))
    response = requests.post(
        NANO_BANANA_API_URL,
        json=request_body,
        headers={"Authorization": f"Bearer {NANO_BANANA_API_KEY}"},
        stream=True,
    )
    response.raise_for_status()

    last: dict = {}
    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("—"),
        TextColumn("[cyan]{task.fields[status]}"),
        expand=True,
    ) as progress:
        task = progress.add_task("生成中", total=100, status=STATUS_TEXT["running"])
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            data = _parse_sse_line(raw_line)
            if data is None:
                continue
            last = data
            p = data.get("progress", 0)
            s = data.get("status", "running")
            progress.update(task, completed=p, status=STATUS_TEXT.get(s, s))
            if s in ("succeeded", "failed"):
                break

    if last.get("status") == "succeeded" and last.get("results"):
        image_url = last["results"][0].get("url", "")
        if image_url:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            _download_image(image_url, save_path)
            console.print(Panel(f"[green]已保存[/green] [cyan]{save_path}[/cyan]", title="完成", border_style="green"))
            return image_url
    elif last.get("status") == "failed":
        console.print(Panel(
            last.get("failure_reason") or last.get("error") or "未知错误",
            title="[red]生成失败[/red]",
            border_style="red",
        ))
    return ""


def generate_character(story_id: str, character_id: str, story_data: dict | None = None) -> str:
    """生成角色立绘并保存到 results/characters/{character_id}.png。"""
    if story_data is None:
        story_data = _load_story(story_id)
    prompt_text = ""
    urls = []
    for character in story_data.get("characters", []):
        if character["id"] == character_id:
            prompt_text = character["description"] + "\n" + character["introduction"]
            urls.append(f"{OSS_URL}/{story_id}/characters/{character_id}.png")
            break
    prompt = f"参考图片绘制一张写实动漫风格的角色图片，彩色，上半身，正面，不要有任何其他元素，图片的描述如下：{prompt_text}"
    save_path = RESULTS_DIR / "characters" / f"{character_id}.png"
    return generate_image(
        prompt,
        urls,
        save_path,
        aspect_ratio="9:16",
        request_title="角色图片",
    )


def _character_image_exists(character_id: str) -> bool:
    """检查角色图片是否已存在。"""
    return (RESULTS_DIR / f"characters/{character_id}.png").is_file()


def fetch_local_resources(prefix: str) -> list[str]:
    result = []
    for file in (RESOURCE_DIR / prefix).glob("*.png"):
        result.append(file.name)
    return result


def fetch_oss_objects(story_id: str, prefix: str) -> list[str]:
    result = []
    paginator = client.list_objects_v2_paginator()
    for page in paginator.iter_page(oss.ListObjectsV2Request(
        bucket="aimmg",
        prefix=f"{story_id}/{prefix}/",
        delimiter="/"
    )):
        for obj in page.contents:
            filename = obj.key.split("/")[-1]
            if filename.endswith(".png"):
                result.append(filename)
    return result


def compare_resources(story_id: str, prefix: str) -> list[str]:
    # 需要上传的文件列表
    result = []
    local_resources = fetch_local_resources(prefix)
    oss_resources = fetch_oss_objects(story_id, prefix)
    for local_resource in local_resources:
        if local_resource not in oss_resources:
            result.append(local_resource)
    return result


def _scene_image_exists(scene_id: str) -> bool:
    """检查场景图片是否已存在。"""
    return (RESULTS_DIR / "scenes" / f"{scene_id}.png").is_file()


def generate_scene(scene: dict, scene_index: int = 0) -> str:
    """生成场景图并保存到 results/scenes/{scene_id}.png。"""
    scene_id = scene.get("id", "")
    if not scene_id:
        return ""
    # 用场景名称 + 首段 prompts/notes 作为描述
    name = scene.get("name") or f"第 {scene_index + 1} 幕"
    parts = [name]
    if "prompts" not in scene:
        console.print(f"[dim]场景 {scene_id} 没有剧本片段[/dim]")
        return ""
    parts.extend(scene["prompts"])
    prompt_text = "\n".join(parts)
    prompt = f"参考以下剧本场景描述，绘制一张写实动漫风格的场景插画，彩色，氛围感强，不要出现具体人物正脸，描述如下：{prompt_text}"
    urls = []
    save_path = RESULTS_DIR / "scenes" / f"{scene_id}.png"
    console.print(prompt)
    console.print(save_path)
    return generate_image(
        prompt,
        urls,
        save_path,
        aspect_ratio="16:9",
        request_title="场景图片",
    )


def generate_all_scenes(story_id: str) -> None:
    story_data = _load_story(story_id)
    for index, scene in enumerate(story_data.get("master", [])):
        scene_id = scene.get("id", "")
        scene_name = scene.get("name", f"场景 {index + 1}")
        if not scene_id:
            continue
        if _scene_image_exists(scene_id):
            console.print(f"[dim]跳过（已存在）[/dim] {scene_name} ({scene_id})")
            continue
        console.print(Panel(f"[bold]{scene_name}[/bold] ({scene_id})", title="当前场景", border_style="blue"))
        generate_scene(scene, scene_index=index)


def prepare_story_resources(story_id: str) -> None:
    """同步故事角色资源到 OSS，使用 rich 输出日志。"""
    console.print(Rule(f"[bold]准备故事资源[/bold] — {story_id}", style="cyan"))
    prefix = "characters"
    local_resources = fetch_local_resources(prefix)
    oss_resources = fetch_oss_objects(story_id, prefix)
    to_upload = [f for f in local_resources if f not in oss_resources]
    # 统计
    table = Table(title="资源对比")
    table.add_column("项目", style="cyan")
    table.add_column("数量", justify="right", style="green")
    table.add_row("本地文件", str(len(local_resources)))
    table.add_row("OSS 已有", str(len(oss_resources)))
    table.add_row("待上传", str(len(to_upload)))
    console.print(table)
    if not to_upload:
        console.print(
            Panel("所有角色资源已同步，无需上传。", title="[green]完成[/green]", border_style="green"))
        return
    console.print(Panel("\n".join(to_upload),
                  title="[yellow]待上传文件[/yellow]", border_style="yellow"))
    for i, filename in enumerate(to_upload, 1):
        local_path = RESOURCE_DIR / prefix / filename
        key = f"{story_id}/characters/{filename}"
        try:
            client.put_object_from_file(
                oss.PutObjectRequest(bucket="aimmg", key=key),
                local_path.as_posix(),
            )
            console.print(
                f"  [green]✓[/green] [{i}/{len(to_upload)}] {filename} → {key}")
        except Exception as e:
            console.print(
                f"  [red]✗[/red] [{i}/{len(to_upload)}] {filename}: [red]{e}[/red]")
    console.print(Panel(f"已上传 [bold]{len(to_upload)}[/bold] 个文件到 OSS。",
                  title="[green]完成[/green]", border_style="green"))


if __name__ == "__main__":
    parser.add_argument("--story", type=str, default="shou_huo_ri")
    subparsers = parser.add_subparsers(dest="command", required=True)
    # character command
    character_parser = subparsers.add_parser(
        "character", help="generate character")
    character_parser.add_argument(
        "--id", type=str, default=None, help="角色 id，不传则生成该故事下全部角色")
    # prepare command
    prepare_parser = subparsers.add_parser(
        "prepare", help="prepare story resources")
    # scene command
    scene_parser = subparsers.add_parser(
        "scene", help="generate scene")
    scene_parser.add_argument(
        "--id", type=str, default=None, help="场景 id，不传则生成该故事下全部场景")
    args = parser.parse_args()
    if args.command == "character":
        if args.id is None:
            story_data = _load_story(args.story)
            for char in story_data.get("characters", []):
                cid = char["id"]
                if _character_image_exists(cid):
                    console.print(f"[dim]跳过（已存在）[/dim] {char['name']} ({cid})")
                    continue
                console.print(
                    Panel(f"[bold]{char['name']}[/bold] ({cid})", title="当前角色", border_style="blue"))
                generate_character(args.story, cid, story_data)
        else:
            if _character_image_exists(args.id):
                console.print(f"[dim]跳过（已存在）[/dim] {args.id}")
            else:
                generate_character(args.story, args.id)
    elif args.command == "prepare":
        prepare_story_resources(args.story)
    elif args.command == "scene":
        if args.id is None:
            generate_all_scenes(args.story)
        else:
            story_data = _load_story(args.story)
            for scene in story_data.get("master", []):
                if scene["id"] == args.id:
                    if _scene_image_exists(args.id):
                        console.print(f"[dim]跳过（已存在）[/dim] {args.id}")
                        continue
                    generate_scene(scene)
                    break
    else:
        console.print(f"Unknown command: {args.command}")
