import argparse
import asyncio
import json
from pathlib import Path
from agentscope.message import Msg
import yaml
from typing import Dict

from agentscope.pipeline import MsgHub

from rich.rule import Rule
from rich.table import Table
from rich.console import Console
from rich.panel import Panel

from entity import Character, PlayerAgent
from store.memory import StoryMemory

parser = argparse.ArgumentParser()
console = Console()
DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_story(story_id: str) -> dict:
    # 读取 data 目录下剧本文件
    path = DATA_DIR / f"story__{story_id}.json"
    with open(path, "r", encoding="utf-8") as f:
        story = json.load(f)
        console.print("Story: " + story["name"],
                      justify="center", style="bold magenta")
        console.print(Rule())
        # 处理角色
        characters_table = Table(title="Characters", expand=True)
        characters_table.add_column("Name")
        characters_table.add_column("Description")
        characters_table.add_column("Introduction")
        characters_table.add_column("Background")
        for character in story["characters"]:
            background = "[bold magenta]Null"
            if "scenes" in character:
                if len(character["scenes"]) > 0:
                    background = ", ".join(character["scenes"][0]["prompts"])
            characters_table.add_row(
                character["name"], character["description"], character["introduction"], background)
        # 处理场景
        scenes_table = Table(title="Scenes", expand=True)
        scenes_table.add_column("Name")
        scenes_table.add_column("Prompts")
        scenes_table.add_column("Notes")
        scenes_table.add_column("Choices")
        for index, scene in enumerate(story["master"]):
            scene_name = f"场景{index + 1}"
            if "name" in scene:
                scene_name = scene["name"]
            scene_prompts = "[bold magenta]Null"
            if "prompts" in scene:
                scene_prompts = ", ".join([p for p in scene["prompts"]])
            scene_notes = "[bold magenta]Null"
            if "notes" in scene:
                scene_notes = ", ".join([n for n in scene["notes"]])
            scene_choices = "[bold magenta]Null"
            if "choices" in scene:
                scene_choices = ", ".join(scene["choices"].keys())
            scenes_table.add_row(
                scene_name,
                str(scene_prompts),
                str(scene_notes),
                scene_choices)
        console.print(characters_table)
        console.print(Rule())
        console.print(scenes_table)
        return story


def create_moderator(config: dict) -> Character:
    return Character(config["moderator"], "moderator", "moderator", f"""你现在是一名剧本杀的主持人""")


def create_characters(characters: list[dict], config: dict) -> Dict[str, Character]:

    result: Dict[str, Character] = {}
    for character in characters:
        id = character["id"]
        name = character["name"]
        description = character["description"]
        introduction = character["introduction"]
        if "scenes" not in character:
            continue
        if len(character["scenes"]) == 0:
            continue
        background = ", ".join(character["scenes"][0]["prompts"])
        tasks = "\n".join(character["scenes"][0]["tasks"])
        character_obj = Character(config["characters"], id, name, f"""你现在是一名剧本杀的玩家.
你的名字叫{name},

你的个人信息如下:
{description}
{introduction}

你的背景故事如下:
{background}

你目前的任务如下:
{tasks}
""")
        result[character_obj.id] = character_obj
    return result


def _msg_content(reply_msg) -> str:
    """从 Msg 中取出纯文本 content。"""
    content = getattr(reply_msg, "content", str(reply_msg))
    if isinstance(content, list):
        return " ".join(getattr(block, "text", str(block)) for block in content)
    return content if isinstance(content, str) else str(content)


async def run_scenes(story: dict, moderator: Character, characters: Dict[str, Character], memory: StoryMemory):
    participants: list[PlayerAgent] = [moderator.agent,
                                       *[c.agent for c in characters.values()]]
    scene = story["master"][1]
    scene_id = scene["id"]
    scene_name = scene.get("name", "场景 2")
    console.print(Rule(f"[bold cyan]{scene_name}[/bold cyan]", style="cyan"))
    async with MsgHub(participants=participants) as scene_hub:
        if "prompts" in scene:
            prompt = f"现在是第二幕, {', '.join(scene['prompts'])}\n\n注意：时刻要注意自己当前要完成的任务，不要偏离任务目标！"
            console.print(
                Panel(prompt, title="[bold]主持人[/bold]", border_style="yellow"))
            memory.add(scene_id, scene_name, moderator.id,
                       moderator.name, json.dump({
                           "type": "text",
                           "text": prompt
                       }))
            for agent in scene_hub.participants:
                if agent.name == "moderator":
                    continue
                reply_msg = await agent(Msg("moderator", prompt, "user"))
                content = _msg_content(reply_msg)
                console.print(Panel(
                    content, title=f"[bold green]{agent.name}[/bold green]", border_style="green"))
                char = next((c for c in characters.values()
                            if c.agent is agent), None)
                if char:
                    memory.add(scene_id, scene_name,
                               char.id, char.name, content)
    console.print(Rule(style="dim"))


if __name__ == "__main__":
    parser.add_argument("--story", type=str, default="shou_huo_ri")
    parser.add_argument("--config", type=str, default="config.yaml")
    # 解析参数
    args = parser.parse_args()
    story_id = args.story
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)
    # 读取文件
    story = parse_story(story_id)
    # 创建游戏对象
    memory = StoryMemory(story_id)
    moderator = create_moderator(config)
    characters = create_characters(story["characters"], config)
    # 按顺序进行场景推演
    console.print(Rule(f"[bold cyan]开始游戏[/bold cyan]", style="cyan"))
    asyncio.run(run_scenes(story, moderator, characters, memory))
