from turtle import mode
import uuid
from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeMultiAgentFormatter
from agentscope.model import DashScopeChatModel
from agentscope.message import Msg
from typing import Type
from pydantic import BaseModel

class PlayerAgent(ReActAgent):
    async def reply(self, msg: Msg | list[Msg] | None = None, structured_model: Type[BaseModel] | None = None) -> Msg:
        return await super().reply(msg, structured_model)

class Character:
    id: str
    name: str
    system_prompt: str
    agent: PlayerAgent
    def __init__(self, config: dict, id: str, name: str, system_prompt: str):
        self.id = id
        self.name = name
        self.system_prompt = system_prompt
        self.agent = PlayerAgent(
            name=name, 
            sys_prompt=system_prompt, formatter=DashScopeMultiAgentFormatter(),
            model=DashScopeChatModel(
                model_name=config["model"],
                api_key=config["api_key"],
                stream=False
            ))

class Scene:
    id: str
    name: str
    system_prompt: str
    def __init__(self, id: str, name: str, system_prompt: str):
        self.id = id
        self.name = name
        self.system_prompt = system_prompt