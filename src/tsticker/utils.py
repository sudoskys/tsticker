import asyncio
import pathlib
from asyncio import Semaphore
from importlib import metadata
from io import BytesIO
from typing import Literal

import requests
from pydantic import BaseModel, model_validator
from rich.console import Console
from telebot.asyncio_helper import session_manager
from telebot.types import User, InputSticker, InputFile
from telegram_sticker_utils import ImageProcessor

from tsticker.const import PYPI_URL
from tsticker.core import get_bot_user

console = Console()

semaphore = Semaphore(20)
request_interval = 60 / 30  # 每个请求间隔时间为 60 秒 / 30 请求 = 2 秒


async def limited_request(coro):
    """
    limit request
    :param coro:
    :return:
    """
    async with semaphore:
        result = await coro
        await asyncio.sleep(request_interval)
        return result


class Credentials(BaseModel):
    token: str
    owner_id: str
    bot_proxy: str | None = None
    _bot_user: User | None = None

    @model_validator(mode='after')
    def validate_token(self):
        with console.status("[bold blue]Validating token...[/]", spinner='dots'):
            bot_user = get_bot_user(bot_token=self.token, bot_proxy=self.bot_proxy)
        self._bot_user = bot_user
        try:
            int(self.owner_id)
        except ValueError:
            raise ValueError("Invalid owner id")
        return self

    @property
    def bot_user(self) -> User:
        if not self._bot_user:
            raise ValueError("Bot user is not available")
        return self._bot_user


async def create_sticker(
        sticker_type: Literal["mask", "regular", "custom_emoji"],
        sticker_file: pathlib.Path,
) -> InputSticker | None:
    """
    创建贴纸，然后替换本地文件为合法的贴纸文件。
    首先判断是动态还是静态贴纸，然后按照贴纸类型进行处理。
    :param sticker_type: 贴纸类型
    :param sticker_file: 本地文件
    :return: InputSticker | None
    """
    if sticker_type == "custom_emoji":
        scale = 100
    else:
        scale = 512
    sticker_file_path = sticker_file.as_posix()
    try:
        sticker = ImageProcessor.make_sticker(
            input_name=sticker_file.stem,
            input_data=sticker_file_path,
            scale=scale,
            master_edge="width"
        )
        return InputSticker(
            sticker=InputFile(BytesIO(sticker.data)),
            emoji_list=sticker.emojis,
            format=sticker.sticker_type
        )
    except Exception as e:
        console.print(f"[bold red]Failed to create sticker because {e}[/]")
        return None


async def check_for_updates():
    try:
        CURRENT_VERSION = metadata.version("tsticker")
        response = requests.get(PYPI_URL)
        if response.status_code == 200:
            package_info = response.json()
            latest_version = package_info['info']['version']
            if latest_version != CURRENT_VERSION:
                release_notes = package_info['releases'].get(latest_version, [])
                release_info = release_notes[0] if release_notes else {}
                description = release_info.get('comment_text', '')
                console.print(
                    f"[bold yellow]INFO:[/] tsticker {CURRENT_VERSION} is installed, while {latest_version} is available."
                )
                if description:
                    console.print(f"[bold blue]COMMENT:[/]\n{description}")
    except Exception as e:
        console.print(f"[bold green]Skipping update check: {type(e)}[/]")


async def close_session():
    if session_manager.session and not session_manager.session.closed:
        await session_manager.session.close()


def close_session_sync():
    # 由于 aexit 需要同步函数，所以必须在调用前获取事件循环
    loop = asyncio.new_event_loop()
    loop.run_until_complete(close_session())
