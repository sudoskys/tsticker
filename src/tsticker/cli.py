import asyncio
import atexit
import os
import pathlib
from asyncio import Semaphore
from collections import defaultdict
from io import BytesIO
from typing import Literal, Optional

import asyncclick as click
import keyring
from magika import Magika
from pydantic import BaseModel, ValidationError, SecretStr, model_validator
from rich.console import Console
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_helper import session_manager
from telebot.types import StickerSet, InputSticker, InputFile
from telegram_sticker_utils import ImageProcessor

from tsticker.core import User, AppSetting
from tsticker.core import get_bot_user
from tsticker.core.const import SERVICE_NAME, USERNAME
from tsticker.core.create import StickerPack, Emote

magika = Magika()
console = Console()
# 全局请求限制器
semaphore = Semaphore(20)
request_interval = 60 / 30  # 每个请求间隔时间为 60 秒 / 30 请求 = 2 秒


async def limited_request(coro):
    async with semaphore:
        result = await coro
        await asyncio.sleep(request_interval)
        return result


async def close_session():
    if session_manager.session and not session_manager.session.closed:
        await session_manager.session.close()


def close_session_sync():
    # 由于 aexit 需要同步函数，所以必须在调用前获取事件循环
    loop = asyncio.new_event_loop()
    loop.run_until_complete(close_session())


# 注册关闭钩子
atexit.register(close_session_sync)


class StickerApp:
    def __init__(self, setting: AppSetting):
        self.setting = setting
        self.bot_user = setting.bot_user
        self.bot = AsyncTeleBot(setting.bot_token.get_secret_value())


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


def save_credentials(
        token: str,
        owner_id: str,
        bot_proxy: str | None
) -> Credentials:
    credentials = Credentials(token=token, bot_proxy=bot_proxy, owner_id=owner_id)
    keyring.set_password(SERVICE_NAME, USERNAME, credentials.model_dump_json())
    return credentials


def get_credentials() -> Credentials | None:
    stored_data = keyring.get_password(SERVICE_NAME, USERNAME)
    if stored_data:
        return Credentials.model_validate_json(stored_data)
    return None


def delete_same_name_files(sticker_table_dir: pathlib.Path):
    # Check if the directory exists
    if not sticker_table_dir.exists():
        console.print(f"Directory {sticker_table_dir} does not exist.")
        return
    # Group files by their base name
    files_by_name = defaultdict(list)
    for file in sticker_table_dir.iterdir():
        if file.is_file():
            files_by_name[file.stem].append(file)
    # Delete files that have the same name but different extensions
    for files in files_by_name.values():
        if len(files) > 1:
            for file in files[1:]:
                console.print(f"[bold yellow]Deleting duplicate file: {file.name}[/]")
                file.unlink()


@click.group()
async def cli():
    """TSticker CLI."""
    pass


@click.command()
@click.option(
    '-t', '--token',
    required=True,
    help='Your BotToken, you can get it from @BotFather, e.g. 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
)
@click.option(
    '-u', '--user',
    required=True,
    help='Owner id of sticker pack'
)
@click.option(
    '-p', '--proxy',
    required=False,
    help='Your bot proxy'
)
async def login(
        token: str,
        user: str,
        proxy: str | None = None
):
    """Log in using a token and optional bot proxy."""
    # 判断是否是 int 的 id
    try:
        int(user)
    except ValueError:
        console.print("[bold red]Invalid user id[/]")
        return
    try:
        save_credentials(token=token, bot_proxy=proxy, owner_id=user)
    except Exception as e:
        console.print(f"[bold red]Failed to save credentials: {e}[/]")
        return
    console.print("[bold yellow]NOTE:[/] Sticker packs created by this bot can only be managed by this bot.")
    console.print(f"[bold green]You are now logged in.[/]")


async def download_and_write_file(app, file_id, file_unique_id, sticker_table_dir):
    """下载文件并写入本地文件夹。"""
    sticker_raw = await limited_request(app.bot.get_file(file_id=file_id))
    sticker_io = await limited_request(app.bot.download_file(file_path=sticker_raw.file_path))
    if not sticker_io:
        return console.print(f"[bold red]Failed to download file: {file_unique_id}[/]")
    else:
        console.print(f"[bold green]Downloaded file: {file_unique_id}[/]")
    idf = magika.identify_bytes(sticker_io)
    content_type_label = idf.output.ct_label
    file_name = f"{file_unique_id}.{content_type_label}"
    sticker_file = sticker_table_dir.joinpath(file_name)
    sticker_file.write_bytes(sticker_io)
    return sticker_file


async def sync_index(
        app: StickerApp,
        index_file: pathlib.Path,
        sticker_set: StickerSet
):
    """
    从云端下载索引文件，同步本地索引文件
    :param app:
    :param index_file:
    :param sticker_set:
    """
    try:
        pack = StickerPack.model_validate_json(index_file.read_text())
    except Exception as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return

    sticker_table_dir = index_file.parent.joinpath("stickers")
    sticker_table_dir.mkdir(exist_ok=True)
    delete_same_name_files(sticker_table_dir)
    local_files = {
        f.stem: f
        for f in sticker_table_dir.glob('*')
    }
    cloud_files = {
        sticker.file_unique_id: sticker
        for sticker in sticker_set.stickers
    }
    to_delete = [
        local_files[ids]
        for ids in local_files if ids not in cloud_files
    ]
    to_validate = [
        local_files[ids]
        for ids in local_files if ids in cloud_files
    ]
    to_download = [
        ids
        for ids in cloud_files if ids not in local_files
    ]

    for file_path in to_delete:
        console.print(f"Deleting extra file: {file_path.name}")
        file_path.unlink()

    for file_path in to_validate:
        local_size = file_path.stat().st_size
        sticker_size = cloud_files[file_path.stem].file_size
        if local_size != sticker_size:
            console.print(f"[bold yellow]File size mismatch for {file_path.name}, re-downloading...[/]")
            file_path.unlink()
            to_download.append(file_path.stem)

    with console.status("[bold blue]Synchronizing index...[/]", spinner='dots') as status:
        # 不用 asyncio.gather 是因为 Telegram 服务器会Block
        index = 0
        for file_id in to_download:
            index += 1
            status.update(f"[bold blue]Downloading file: {file_id}...[/] {index}/{len(to_download)}")
            await download_and_write_file(
                app,
                file_id=cloud_files[file_id].file_id,
                file_unique_id=cloud_files[file_id].file_unique_id,
                sticker_table_dir=sticker_table_dir
            )
        """
        tasks = [
            download_and_write_file(app, cloud_files[file_id], sticker_table_dir)
            for file_id in to_download
        ]
        await asyncio.gather(*tasks)
        """

    emote_update = []
    for file_id, sticker in cloud_files.items():
        emote_update.append(
            Emote(
                emoji=sticker.emoji,
                file_id=file_id,
            )
        )
    pack.emotes = emote_update
    with index_file.open("w") as f:
        f.write(pack.model_dump_json(indent=2))
    console.print("[bold green]Synchronization completed![/]")


@click.command()
@click.option(
    '-s', '--sticker-type',
    type=click.Choice(['mask', 'regular', 'custom_emoji'], case_sensitive=False),
    required=False,
    default='regular',
    help='Type of the sticker (mask, regular, custom_emoji)'
)
@click.option('-n', '--pack-name', required=True, help='Your pack name')
@click.option('-t', '--pack-title', required=True, help='Your pack title')
async def init(
        pack_name: str,
        pack_title: str,
        sticker_type: Literal["mask", "regular", "custom_emoji"] = "regular"
):
    """Initialize with pack name, pack title, and sticker type."""
    credentials = get_credentials()
    if not credentials:
        console.print("[bold red]You are not logged in. Please login first.[/]")
        return
    try:
        bot_setting = AppSetting(
            pack_name=pack_name,
            pack_title=pack_title,
            sticker_type=sticker_type,
            bot_token=SecretStr(credentials.token),
            bot_proxy=credentials.bot_proxy,
            bot_user=credentials.bot_user,
            owner_id=int(credentials.owner_id)
        )
    except Exception as e:
        console.print(f"[bold red]Failed to create app: {e}[/]")
        console.print("[bold red]Pack name must be alphanumeric and underscore only.[/]")
        return
    console.print(
        f"[bold blue]Initializing with pack name:[/] {pack_name}, "
        f"[bold blue]Pack Title:[/] {pack_title}, "
        f"[bold blue]Sticker Type:[/] {sticker_type}"
    )
    root_dir = pathlib.Path(os.getcwd())
    # 尝试使用 Packname 创建文件夹
    try:
        sticker_dir = root_dir.joinpath(pack_name)
        if sticker_dir.exists():
            console.print(f"[bold red]Pack directory already exists:[/] {sticker_dir}")
            return
        sticker_dir.mkdir(exist_ok=False)
    except Exception as e:
        console.print(f"[bold red]Failed to create pack directory: {e}[/]")
        return
    console.print(f"[bold blue]Pack directory inited:[/] {sticker_dir}")
    index_file = sticker_dir.joinpath("index.json")
    index_file.write_text(
        StickerPack.create(
            title=bot_setting.pack_title,
            name=bot_setting.make_set_name(bot_setting.pack_name, bot_setting.bot_user.username),
            sticker_type=bot_setting.sticker_type,
            operator_id=str(bot_setting.bot_user.id)
        ).model_dump_json(indent=2)
    )
    # 创建 App
    app = StickerApp(bot_setting)
    with console.status("[bold blue]Retrieving sticker...[/]", spinner='dots'):
        try:
            sticker_set = await limited_request(app.bot.get_sticker_set(bot_setting.pack_name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {bot_setting.pack_name}: {e}[/]")
                return
    # 创建资源文件夹
    sticker_table_dir = sticker_dir.joinpath("stickers")
    sticker_table_dir.mkdir(exist_ok=True)
    if not sticker_set:
        console.print(f"[bold blue]Empty pack, and index file created:[/] {index_file}")
    else:
        # 同步索引文件
        await sync_index(app, index_file, sticker_set)
    console.print("[bold blue]Initialization completed![/]")


async def upon_credentials() -> tuple[Optional[StickerPack], Optional[pathlib.Path], Optional[StickerApp]]:
    credentials = get_credentials()
    if not credentials:
        console.print("[bold red]You are not logged in. Please login first.[/]")
        return None, None, None
    root = pathlib.Path(os.getcwd())
    index_file = root.joinpath("index.json")
    if not index_file.exists():
        console.print("[bold red]Index file not found. Please sync in an initialized directory.[/]")
        return None, None, None
    try:
        pack = StickerPack.model_validate_json(index_file.read_text())
    except ValidationError as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return None, None, None
    try:
        app_settings = AppSetting(
            pack_name=pack.name,
            pack_title=pack.title,
            sticker_type=pack.sticker_type,
            bot_token=SecretStr(credentials.token),
            bot_proxy=credentials.bot_proxy,
            bot_user=credentials.bot_user,
            owner_id=int(credentials.owner_id)
        )
        app = StickerApp(app_settings)
    except Exception as e:
        console.print(f"[bold red]Failed to create app: {e}[/]")
        return None, None, None
    return pack, index_file, app


@click.command()
async def sync():
    """Synchronize data."""
    pack, index_file, app = await upon_credentials()
    if not pack or not index_file or not app:
        return
    with console.status("[bold magenta]Retrieving sticker...[/]", spinner='dots'):
        try:
            sticker_set = await limited_request(app.bot.get_sticker_set(pack.name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {pack.name}: {e}[/]")
                return
    if not sticker_set:
        console.print("[bold red]Sticker Set not created yet. Please push first.[/]")
        return
    console.print(f"[bold cyan]Working on pack:[/] https://t.me/addstickers/{app.setting.pack_name}")
    console.print("[bold magenta]Synchronizing data...[/]")
    await sync_index(app, index_file, sticker_set)


async def create_sticker(
        app: StickerApp,
        sticker_file: pathlib.Path,
) -> InputSticker | None:
    """
    创建贴纸，然后替换本地文件为合法的贴纸文件。
    首先判断是动态还是静态贴纸，然后按照贴纸类型进行处理。
    :param app: StickerApp
    :param sticker_file: 本地贴纸文件
    :return: InputSticker | None
    """
    if app.setting.sticker_type == "custom_emoji":
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
        console.print(f"[bold red]Failed to create sticker: {e}[/]")
        return None


async def push_to_cloud(
        app: StickerApp,
        index_file: pathlib.Path,
        sticker_set: StickerSet | None,
):
    """
    推送本地文件更改到云端，如果不存在则创建。
    :param app: StickerApp
    :param index_file: 本地索引文件
    :param sticker_set: 云端的贴纸集
    """
    try:
        pack = StickerPack.model_validate_json(index_file.read_text())
    except Exception as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return
    sticker_table_dir = index_file.parent.joinpath("stickers")
    sticker_table_dir.mkdir(exist_ok=True)
    delete_same_name_files(sticker_table_dir)
    # 获取本地文件
    local_files = {
        f.stem: f
        for f in sticker_table_dir.glob('*')
    }
    if not sticker_set:
        # TODO 413 => 'Payload Too Large',
        stickers = []
        for sticker_file in local_files.values():
            sticker = await create_sticker(app, sticker_file)
            if not sticker:
                console.print(f"[bold red]Failed to create sticker for file: {sticker_file.name}[/]")
                return False
            stickers.append(sticker)
        if len(stickers) > 30:
            console.print("[bold red]You have more than 30 stickers, which is too large to create a sticker set.[/]")
            return
        if len(stickers) == 0:
            console.print(
                "[bold red]You have no stickers to create a sticker set. Place your stickers in the stickers folder.[/]"
            )
            return
        with console.status("[bold yellow]Creating sticker set...[/]", spinner='dots'):
            try:
                success = await limited_request(
                    app.bot.create_new_sticker_set(
                        user_id=app.setting.owner_id,
                        title=pack.title,
                        name=pack.name,
                        stickers=stickers,
                        sticker_type=pack.sticker_type
                    )
                )
                assert success, "Request failed"
            except Exception as e:
                if "USER_IS_BOT" in str(e):
                    console.print(f"[bold yellow]You cant create sticker set with a bot account: {e}[/]")
                console.print(f"[bold red]Failed to create sticker set: {e}[/]")
                return False
        return True
    # 获取云端文件
    cloud_files = {
        sticker.file_unique_id: sticker
        for sticker in sticker_set.stickers
    }
    # 本地文件中不存在的文件
    to_upload = [
        file_id
        for file_id in local_files if file_id not in cloud_files
    ]
    # 云端文件中不存在的文件
    to_delete = [
        sticker.file_id
        for file_id, sticker in cloud_files.items() if file_id not in local_files
    ]
    # 如果本地文件和云端文件都存在，但是文件大小不一致，重新下载
    to_fix = [
        (file_unique_id, cloud_files[file_unique_id].file_id)
        for file_unique_id in local_files
        if file_unique_id in cloud_files and local_files[file_unique_id].stat().st_size != cloud_files[
            file_unique_id].file_size
    ]
    if pack.title != sticker_set.title:
        with console.status("[bold yellow]Updating title...[/]", spinner='dots'):
            await limited_request(
                app.bot.set_sticker_set_title(pack.name, pack.title)
            )
        console.print(f"[bold yellow]Title updated to: {pack.title}[/]")
    if to_delete or to_upload or to_fix:
        console.print("[bold yellow]Changes detected:[/]")
        console.print(f"[bold yellow]Files to delete:[/] {len(to_delete)}")
        console.print(f"[bold yellow]Files to upload:[/] {len(to_upload)}")
        console.print(f"[bold yellow]Files to fix:[/] {len(to_fix)}")
    # 计算最后结果是否超过 120
    if len(cloud_files) - len(to_delete) + len(to_upload) > 120:
        console.print("[bold red]Your wanted operation will exceed the limit of 120 stickers, so it's aborted.[/]")
        return
    # 删除云端文件
    with console.status("[bold yellow]Deleting extra files...[/]", spinner='dots') as status:
        index = 0
        for file_id in to_delete:
            # 更新进度条
            index += 1
            status.update(f"[bold yellow]Deleting file: {file_id}...[/] {index}/{len(to_delete)}")
            try:
                success = await limited_request(
                    app.bot.delete_sticker_from_set(sticker=file_id)
                )
                assert success, "Request failed"
            except Exception as e:
                console.print(f"[bold red]Failed to delete sticker: {e}[/]")
            else:
                console.print(f"[bold green]Deleted sticker: {file_id}[/]")

    # 上传文件到云端
    with console.status(f"[bold yellow]Uploading sticker...[/]", spinner='dots') as status:
        index = 0
        for file_name in to_upload:
            index += 1
            status.update(f"[bold yellow]Uploading sticker: {file_name}...[/] {index}/{len(to_upload)}")
            sticker_file = local_files[file_name]
            sticker = await create_sticker(app, sticker_file)
            if sticker:
                success = await limited_request(
                    app.bot.add_sticker_to_set(
                        user_id=app.setting.owner_id,
                        name=pack.name,
                        sticker=sticker
                    )
                )
                if success:
                    console.print(f"[bold green]Uploaded sticker: {file_name}[/]")
                    # 删除本地文件
                    sticker_file.unlink()
                else:
                    console.print(f"[bold red]Failed to upload sticker: {file_name}[/]")
            else:
                console.print(f"[bold red]Failed to create sticker for file: {file_name}[/]")

    # 更新云端文件
    with console.status("[bold yellow]Correcting stickers...[/]", spinner='dots') as status:
        index = 0
        for local_file_name, cloud_file_id in to_fix:
            index += 1
            need_delete = local_files[local_file_name]
            status.update(
                f"[bold yellow]Correcting stickers: {local_file_name}: {cloud_file_id}...[/] {index}/{len(to_fix)}")
            try:
                # 删除本地文件

                await download_and_write_file(
                    app,
                    file_id=cloud_file_id,
                    file_unique_id=local_file_name,
                    sticker_table_dir=sticker_table_dir
                )
            except Exception as e:
                console.print(f"[bold red]Failed to correct sticker: {local_file_name} {e}[/]")
                return False
            else:
                need_delete.unlink(missing_ok=True)
                console.print(f"[bold green]Corrected sticker: {local_file_name}[/]")

    if to_delete or to_upload or to_fix:
        console.print("[bold green]Changes applied![/]")
    return True


@click.command()
async def push():
    """Push local file changes to Telegram."""
    pack, index_file, app = await upon_credentials()
    if not pack or not index_file or not app:
        return
    with console.status("[bold yellow]Retrieving sticker...[/]", spinner='dots'):
        try:
            sticker_set = await limited_request(app.bot.get_sticker_set(pack.name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {pack.name}: {e}[/]")
                return
    console.print(f"[bold cyan]Working on pack:[/] https://t.me/addstickers/{app.setting.pack_name}")
    try:
        if not await push_to_cloud(app=app, index_file=index_file, sticker_set=sticker_set):
            console.print("[bold red]Push aborted![/]")
    except Exception as e:
        from loguru import logger
        logger.exception(e)
        console.print(f"[bold red]Push failed: {e}[/]")
        return
    # 同步索引文件
    with console.status("[bold yellow]Synchronizing index...[/]", spinner='dots'):
        try:
            sticker_set = await limited_request(app.bot.get_sticker_set(pack.name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {pack.name}: {e}[/]")
                return
    if sticker_set:
        await sync_index(app, index_file, sticker_set=sticker_set)
        console.print("[bold green]Cleanup completed![/]")


cli.add_command(login)
cli.add_command(init)
cli.add_command(push)
cli.add_command(sync)

if __name__ == "__main__":
    cli(_anyio_backend="asyncio")
