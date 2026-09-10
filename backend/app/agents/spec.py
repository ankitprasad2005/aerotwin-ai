from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentSpec:
    agent_type: str
    task_description: str
    system_instructions: str
    tool_name: str
    tool_fn: Callable[[AsyncSession], Awaitable[dict]]
    output_schema: type[BaseModel]
