import asyncio
import pathlib
from asyncio import Semaphore
from importlib import metadata
from io import BytesIO
from typing import Literal

import emoji
import httpx
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


def get_emojis_from_file_name(file_name: str):
    _result = []
    emoji_name = emoji.emojize(file_name, variant="emoji_type")
    for _char in emoji_name:
        if emoji.is_emoji(_char):
            _result.append(_char)

    return _result


async def create_sticker(
        sticker_type: Literal["mask", "regular", "custom_emoji"],
        sticker_file: pathlib.Path,
) -> InputSticker | None:
    """
    Create sticker from local file by telegram_sticker_utils.
    First check if it is animated or static sticker, then process according to sticker type.
    If sticker type is custom_emoji, scale is 100, otherwise scale is 512.
    If sticker name is emoji, emojis is sticker name, otherwise emojis return from telegram_sticker_utils.
    :param sticker_type: sticker type
    :param sticker_file: local file
    :return: InputSticker | None
    """
    if sticker_type == "custom_emoji":
        scale = 100
    else:
        scale = 512
    sticker_file_path = sticker_file.as_posix()

    try:
        emojis = get_emojis_from_file_name(sticker_file.stem)
        sticker = ImageProcessor.make_sticker(
            input_name=sticker_file.stem,
            input_data=sticker_file_path,
            scale=scale,
            master_edge="width"
        )
        # If emojis is empty, use sticker emojis instead
        if not emojis:
            emojis = sticker.emojis
        return InputSticker(
            sticker=InputFile(BytesIO(sticker.data)),
            emoji_list=emojis,
            format=sticker.sticker_type
        )
    except Exception as e:
        console.print(f"[bold red]Failed to create sticker because {e}[/]")
        return None


async def check_for_updates():
    try:
        CURRENT_VERSION = metadata.version("tsticker")
        # 发送 GET 请求到 PyPI API
        async with httpx.AsyncClient(
                timeout=10, headers={"User-Agent": "tsticker"}
        ) as client:
            response = await client.get(PYPI_URL)

        if response.status_code != 200:
            console.print(f"[bold green]Skipping update check: HTTP {response.status_code}[/]")
            return

        # 从 JSON 响应中提取所需的信息
        package_info = response.json()
        latest_version = package_info.get('info', {}).get('version', "")

        # 如果版本已是最新，直接返回
        if latest_version == CURRENT_VERSION:
            return

        # 获取更新说明
        release_notes = package_info.get('releases', {}).get(latest_version, [])
        release_info = release_notes[0] if release_notes else {}
        description = release_info.get('comment_text', '')

        # 打印更新版本信息
        console.print(
            f"[blue]INFO:[/] [gray42]tsticker [cyan]{CURRENT_VERSION}[/] is installed, while [cyan]{latest_version}[/] is available.[/]"
        )

        # 如果提供了 release 的 description，显示正确信息
        if description:
            console.print(f"[blue]COMMENT:[/]\n{description}")

    except Exception as e:
        console.print(f"[blue]! Skipping update check: {type(e)}: {e}[/]")


async def close_session():
    if session_manager.session and not session_manager.session.closed:
        await session_manager.session.close()


def close_session_sync():
    # 由于 aexit 需要同步函数，所以必须在调用前获取事件循环
    loop = asyncio.new_event_loop()
    loop.run_until_complete(close_session())
