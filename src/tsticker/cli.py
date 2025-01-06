import atexit
import datetime
import os
import pathlib
import shutil
from collections import defaultdict
from typing import Literal, Optional, Text

import asyncclick
import keyring
from magika import Magika
from pydantic import ValidationError
from rich.panel import Panel
from rich.text import Text
from telebot.async_telebot import AsyncTeleBot
from telebot.types import StickerSet

from tsticker.const import STICKER_DIR_NAME, SNAPSHOT_DIR_NAME
from tsticker.core import StickerValidateInput
from tsticker.core.const import SERVICE_NAME, USERNAME
from tsticker.core.create import StickerIndexFile, Emote
from tsticker.utils import console, Credentials, create_sticker, check_for_updates, \
    close_session_sync, limited_request

magika = Magika()
# 注册关闭钩子
atexit.register(close_session_sync)


def save_credentials(
        token: str,
        owner_id: str,
        bot_proxy: str | None
) -> Credentials:
    """
    Save credentials to keyring.
    :param token: Get it from @BotFather, e.g. 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    :param owner_id: Owner(Human) id of sticker pack
    :param bot_proxy: Your bot proxy
    :return: Credentials
    """
    credentials = Credentials(token=token, bot_proxy=bot_proxy, owner_id=owner_id)
    keyring.set_password(SERVICE_NAME, USERNAME, credentials.model_dump_json())
    return credentials


def get_credentials() -> Credentials | None:
    stored_data = keyring.get_password(SERVICE_NAME, USERNAME)
    if stored_data:
        return Credentials.model_validate_json(stored_data)
    return None


def delete_same_name_files(sticker_table_dir: pathlib.Path):
    """
    Delete files that have the same name but different extensions.
    :param sticker_table_dir: pathlib.Path
    :return: None
    """
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


def get_stickers_path(index_file: pathlib.Path):
    """
    Get the path to the stickers directory.
    :param index_file: pathlib.Path
    :return: pathlib.Path
    :raise FileNotFoundError: if the stickers directory does not exist
    """
    sticker_table_dir = index_file.parent.joinpath(STICKER_DIR_NAME)
    if not sticker_table_dir.exists():
        sticker_table_dir.mkdir(exist_ok=True)
    if not sticker_table_dir.is_dir():
        raise FileNotFoundError(f"Sticker path is not a directory: {sticker_table_dir}")
    return sticker_table_dir


def get_snapshot_path(index_file: pathlib.Path):
    """
    Get the path to the snapshot directory.
    :param index_file: pathlib.Path
    :return: pathlib.Path
    :raise FileNotFoundError: if the snapshot directory does not exist
    """
    snapshot_dir = index_file.parent.joinpath(SNAPSHOT_DIR_NAME)
    if not snapshot_dir.exists():
        snapshot_dir.mkdir(exist_ok=True)
    if not snapshot_dir.is_dir():
        raise FileNotFoundError(f"Snapshot path is not a directory: {snapshot_dir}")
    return snapshot_dir


def backup_snapshot(index_file: pathlib.Path):
    """
    Create a backup of the stickers directory.
    :param index_file: pathlib.Path
    :return: None
    :raise FileNotFoundError: if the snapshot directory does not exist
    """
    sticker_table_dir = get_stickers_path(index_file=index_file)
    snapshot_dir = get_snapshot_path(index_file=index_file)
    # 获取现有快照
    snapshots = sorted(snapshot_dir.glob(f"{SNAPSHOT_DIR_NAME}_*"), key=os.path.getmtime)
    # 如果快照超过三个，删除最旧的
    while len(snapshots) >= 4:
        deleted_snapshot = snapshots.pop(0)
        console.print(f"[bold cyan]Cleaning up old snapshot: {deleted_snapshot}[/]")
        shutil.rmtree(deleted_snapshot)
    # 创建新的快照
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    new_snapshot = snapshot_dir.joinpath(f"{SNAPSHOT_DIR_NAME}_{timestamp}")
    shutil.copytree(sticker_table_dir, new_snapshot)
    console.print(f"[bold steel_blue3]✔ Snapshot backup created successfully at:[/] {new_snapshot}")
    console.print(f"[bold steel_blue3]    You can restore it by copying the contents back to the stickers directory.[/]")


@asyncclick.group()
async def cli():
    """TSticker CLI."""
    pass


@asyncclick.command()
@asyncclick.option(
    '-t', '--token',
    required=True,
    help='Your BotToken, you can get it from @BotFather, e.g. 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
)
@asyncclick.option(
    '-u', '--user',
    required=True,
    help='Owner id of sticker pack'
)
@asyncclick.option(
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
    console.print(f"[bold dark_green]You are now logged in.[/]")


async def download_and_write_file(
        telegram_bot: AsyncTeleBot,
        file_id: str,
        file_unique_id: str,
        sticker_table_dir: pathlib.Path
):
    """下载文件并写入本地文件夹。"""
    sticker_raw = await limited_request(telegram_bot.get_file(file_id=file_id))
    sticker_io = await limited_request(telegram_bot.download_file(file_path=sticker_raw.file_path))
    if not sticker_io:
        return console.print(f"[bold red]Failed to download file: {file_unique_id}[/]")
    idf = magika.identify_bytes(sticker_io)
    content_type_label = idf.output.ct_label
    file_name = f"{file_unique_id}.{content_type_label}"
    sticker_file = sticker_table_dir.joinpath(file_name)
    sticker_file.write_bytes(sticker_io)
    return sticker_file


async def download_sticker_set(
        pack_name: str,
        telegram_bot: AsyncTeleBot,
        download_dir: pathlib.Path
):
    sticker_set = await limited_request(telegram_bot.get_sticker_set(pack_name))
    if not sticker_set:
        console.print(f"[bold red]Sticker set not found: {pack_name}[/]")
        return
    sticker_set: StickerSet
    sticker_table_dir = download_dir.joinpath(pack_name)
    sticker_table_dir.mkdir(exist_ok=True)
    delete_same_name_files(sticker_table_dir)
    total_stickers = len(sticker_set.stickers)
    with console.status("[bold cyan]Downloading pack...[/]", spinner='dots') as status:
        # 不用 asyncio.gather 是因为 Telegram 服务器会Block
        index = 0
        for sticker in sticker_set.stickers:
            index += 1
            status.update(f"[bold cyan]Synchronizing indexes: {sticker.file_id}...[/] {index}/{total_stickers}")
            await download_and_write_file(
                telegram_bot=telegram_bot,
                file_id=sticker.file_id,
                file_unique_id=sticker.file_unique_id,
                sticker_table_dir=sticker_table_dir
            )
    console.print(f"[bold dark_green]Downloaded sticker set: {pack_name}[/]")


async def sync_index(
        telegram_bot: AsyncTeleBot,
        index_file: pathlib.Path,
        cloud_sticker_set: StickerSet
):
    """
    从云端下载索引文件，同步本地索引文件
    :param telegram_bot: AsyncTeleBot
    :param index_file: 索引文件
    :param cloud_sticker_set: 云端的贴纸集
    """
    try:
        pack = StickerIndexFile.model_validate_json(index_file.read_text())
    except Exception as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return
    try:
        sticker_table_dir = get_stickers_path(index_file=index_file)
    except FileNotFoundError as e:
        console.print(f"[bold red]Sticker directory not found: {e}[/]")
        return
    delete_same_name_files(sticker_table_dir)
    local_files: dict[str, pathlib.Path] = {
        f.stem: f
        for f in sticker_table_dir.glob('*')
    }
    cloud_files = {
        sticker.file_unique_id: sticker
        for sticker in cloud_sticker_set.stickers
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

    if to_delete:
        # 格式化列表内容
        file_list_text = "\n".join([f"- [bold gray]{file_name.name}[/]" for file_name in to_delete])
        # 创建 Panel
        panel = Panel(
            Text(file_list_text),
            title="Cleaning Up Files",
            subtitle=f"Files to delete: {len(to_delete)}",
            style="yellow",
        )
        console.print(panel)

    for file_path in to_delete:
        file_path.unlink()

    for file_path in to_validate:
        local_size = file_path.stat().st_size
        sticker_size = cloud_files[file_path.stem].file_size
        if local_size != sticker_size:
            console.print(f"[bold yellow]File size mismatch for {file_path.name}, re-downloading...[/]")
            file_path.unlink()
            to_download.append(file_path.stem)
    """
    Telegram Server 会 Block，所以不要使用 asyncio.gather
    tasks = [
                download_and_write_file(app, cloud_files[file_id], sticker_table_dir)
                for file_id in to_download
            ]
    await asyncio.gather(*tasks)
    """
    with console.status("[bold steel_blue3]Synchronizing index...[/]", spinner='dots') as status:
        # 不用 asyncio.gather 是因为 Telegram 服务器会Block
        index = 0
        for file_id in to_download:
            index += 1
            status.update(f"[bold steel_blue3]Synchronizing indexes: {file_id}...[/] {index}/{len(to_download)}")
            await download_and_write_file(
                telegram_bot=telegram_bot,
                file_id=cloud_files[file_id].file_id,
                file_unique_id=cloud_files[file_id].file_unique_id,
                sticker_table_dir=sticker_table_dir
            )

    # 更新索引文件
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
    console.print("[bold dark_green]✔ Synchronization completed![/]")


@asyncclick.command()
async def logout():
    """Log out."""
    keyring.delete_password(SERVICE_NAME, USERNAME)
    console.print("[bold yellow]You are now logged out.[/]")


@asyncclick.command()
@asyncclick.option('-l', '--link', required=True, help='Link for downloading stickers')
async def download(link: str):
    """Download stickers from Telegram."""
    credentials = get_credentials()
    if not credentials:
        console.print("[bold red]You are not logged in. To access telegram api, you need to login first.[/]")
        return
    pack_name = link.removesuffix("/").split("/")[-1]
    root_download_dir = pathlib.Path(os.getcwd())
    if not root_download_dir.exists():
        console.print(f"[bold red]Download directory does not exist: {root_download_dir}[/]")
        return
    console.print(f"[bold cyan]Preparing to download pack: {pack_name} to {root_download_dir.as_posix()}[/]")
    telegram_bot = AsyncTeleBot(credentials.token)
    await download_sticker_set(pack_name, telegram_bot, root_download_dir)
    console.print("[bold dark_green]Download completed![/]")


@asyncclick.command()
@asyncclick.option('-l', '--link', required=True, help='Link to import stickers')
async def trace(link: str):
    """Initialize with pack name, pack title, and sticker type."""
    credentials = get_credentials()
    if not credentials:
        return console.print("[bold red]You are not logged in. Please login first.[/]")
    with console.status("[bold cyan]Retrieving sticker set from Telegram...[/]", spinner="dots"):
        _pack_name = link.removesuffix("/").split("/")[-1]
        try:
            telegram_bot = AsyncTeleBot(credentials.token)
            cloud_sticker_set: StickerSet = await limited_request(
                AsyncTeleBot(credentials.token).get_sticker_set(_pack_name)
            )
        except Exception as e:
            console.print(
                f"[bold red]Cant fetch stickers named {_pack_name}: {e}, you cant import a non-exist pack.[/]"
            )
            return
    console.print(
        f"[bold steel_blue3]Cloud sticker with pack name:[/] {cloud_sticker_set.name}\n"
        f"[bold steel_blue3]Pack Title:[/] {cloud_sticker_set.title} \n"
        f"[bold steel_blue3]Sticker Type:[/] {cloud_sticker_set.sticker_type}"
    )
    if not cloud_sticker_set.name.endswith("_by_" + credentials.bot_user.username):
        console.print(
            f"[bold red]You can only change sticker-set created by BOT USER now logged: @{credentials.bot_user.username} {credentials.bot_user.full_name}[/]"
        )
        console.print(f"[bold red]The pack name should end with `_by_{credentials.bot_user.username}` [/]")
        return
    root_dir = pathlib.Path(os.getcwd())
    # 尝试使用 Packname 创建文件夹
    try:
        sticker_dir = root_dir.joinpath(cloud_sticker_set.name)
        if sticker_dir.exists():
            console.print(f"[bold red]Pack directory already exists:[/] {sticker_dir}")
            return
        sticker_dir.mkdir(exist_ok=False)
    except Exception as e:
        console.print(f"[bold red]Failed to create pack directory: {e}[/]")
        return
    console.print(f"[bold steel_blue3]Pack directory inited:[/] {sticker_dir}")
    index_file = sticker_dir.joinpath("index.json")
    index_file.write_text(
        StickerIndexFile.create(
            title=cloud_sticker_set.title,
            name=cloud_sticker_set.name,
            sticker_type=cloud_sticker_set.sticker_type,
            operator_id=str(credentials.bot_user.id)
        ).model_dump_json(indent=2)
    )
    # 创建资源文件夹
    sticker_table_dir = sticker_dir.joinpath(STICKER_DIR_NAME)
    sticker_table_dir.mkdir(exist_ok=True)
    if not cloud_sticker_set:
        console.print(f"[bold steel_blue3] Empty pack, and index file created:[/] {index_file}")
    else:
        # 同步索引文件
        await sync_index(telegram_bot, index_file, cloud_sticker_set)
    console.print("[bold steel_blue3]Initialization completed![/]")
    console.print(f"\n[bold cyan]Put your stickers in {sticker_table_dir}, [/]")
    console.print("[bold cyan]then run 'tsticker push' to push your stickers to Telegram.[/]")


@asyncclick.command()
@asyncclick.option(
    '-s', '--sticker-type',
    type=asyncclick.Choice(['mask', 'regular', 'custom_emoji'], case_sensitive=False),
    required=False,
    default='regular',
    help='Type of the sticker (mask, regular, custom_emoji)'
)
@asyncclick.option('-n', '--pack-name', required=True, help='Your pack name')
@asyncclick.option('-t', '--pack-title', required=True, help='Your pack title')
async def init(
        pack_name: str,
        pack_title: str,
        sticker_type: Literal["mask", "regular", "custom_emoji"] = "regular"
):
    """Initialize with pack name, pack title, and sticker type."""
    credentials = get_credentials()
    if not credentials:
        console.print(Panel("[bold red]You are not logged in. Please login first.[/]", style="red", expand=False))
        return
    try:
        validate_input = StickerValidateInput(
            pack_name=pack_name,
            pack_title=pack_title,
            sticker_type=sticker_type,
        )
        telegram_bot = AsyncTeleBot(credentials.token)
    except Exception as e:
        console.print(f"[bold red]Failed to initialize app: {e}[/]")
        console.print("[bold yellow]Hint: Pack name must only contain alphanumeric characters and underscores.[/]")
        return

    root_dir = pathlib.Path(os.getcwd())
    try:
        sticker_dir = root_dir.joinpath(validate_input.pack_name)
        if sticker_dir.exists():
            console.print(
                Panel(f"[bold red]Pack directory already exists:[/] {sticker_dir}", style="red", expand=False))
            return
        sticker_dir.mkdir(exist_ok=False)
    except Exception as e:
        console.print(Panel(f"[bold red]Failed to create pack directory: {e}[/]", style="red", expand=False))
        return

    # 成功创建 Pack 目录
    console.print(f"[bold steel_blue3]✔ Pack directory initialized:[/] {sticker_dir}")

    # 生成索引文件和相关配置
    index_file = sticker_dir.joinpath("index.json")
    index_file_model = StickerIndexFile.create(
        title=validate_input.pack_title,
        name=StickerValidateInput.make_set_name(validate_input.pack_name, credentials.bot_user.username),
        sticker_type=sticker_type,
        operator_id=str(credentials.owner_id)
    )

    index_file.write_text(index_file_model.model_dump_json(indent=2))

    # 输出索引信息
    console.print(Panel(
        f"[bold cyan]New index created:[/]\n"
        f"  [bold black]Pack Title:[/] {index_file_model.title}\n"
        f"  [bold cyan]Link Name:[/] {index_file_model.name}\n"
        f"  [bold cyan]Sticker Type:[/] {index_file_model.sticker_type}\n"
        f"  [bold cyan]Bot Owner:[/] {index_file_model.operator_id}",
        style="cyan",
        title="StickerSet Info",
        expand=False
    ))

    if len(index_file_model.operator_id) != 10:
        console.print(Panel(
            "[bold yellow]Are you sure?[/] Bot Owner must be a human account ID and not a bot account ID.",
            style="yellow",
            expand=False
        ))

    # 检索贴纸包
    with console.status("[bold cyan]Retrieving sticker set from Telegram...[/]", spinner="dots"):
        try:
            sticker_set: Optional[StickerSet] = await limited_request(
                telegram_bot.get_sticker_set(index_file_model.name)
            )
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to retrieve sticker set {index_file_model.name}: {e}[/]")
                return

    # 处理贴纸文件夹
    try:
        sticker_table_dir = get_stickers_path(index_file=index_file)
    except Exception as e:
        console.print(f"[bold red]Error: Failed to create sticker directory: {e}[/]")
        return

    # 输出创建成功
    if not sticker_set:
        console.print(f"[bold steel_blue3]✔ Empty pack, and index file created at:[/] {index_file}")
    else:
        await sync_index(telegram_bot, index_file, sticker_set)

    # 提示下一步操作
    console.print("\n[bold dark_green]✔ Initialization completed![/]")
    console.print(Panel(
        f"[bold yellow]Put your stickers in:[/] {sticker_table_dir}\n"
        "[bold yellow]Then run 'tsticker push' to push your stickers to Telegram.[/]",
        style="yellow",
        title="Next Steps",
        expand=False
    ))


async def upon_credentials() -> tuple[Optional[StickerIndexFile], Optional[pathlib.Path], Optional[AsyncTeleBot]]:
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
        local_sticker_model = StickerIndexFile.model_validate_json(index_file.read_text())
    except ValidationError as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return None, None, None
    try:
        StickerValidateInput(
            pack_name=local_sticker_model.name,
            pack_title=local_sticker_model.title,
            sticker_type=local_sticker_model.sticker_type,
        )
        telegram_bot = AsyncTeleBot(credentials.token)
    except Exception as e:
        console.print(f"[bold red]Failed to create app: {e}[/]")
        return None, None, None
    return local_sticker_model, index_file, telegram_bot


@asyncclick.command()
async def sync():
    """Overwrite local file changes using Telegram."""
    local_sticker, index_file, telegram_bot = await upon_credentials()
    if not local_sticker or not index_file or not telegram_bot:
        return
    with console.status("[bold cyan]Retrieving sticker set from Telegram...[/]", spinner="dots"):
        try:
            now_sticker_set: Optional[StickerSet] = await limited_request(
                telegram_bot.get_sticker_set(local_sticker.name)
            )
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                now_sticker_set = None
            else:
                console.print(f"[bold red]Error: Failed to retrieve sticker set '{local_sticker.name}':[/] {e}")
                return
    if not now_sticker_set:
        console.print(
            "[bold red]Error: Sticker set not found in Telegram. It seems the sticker pack is not created yet.[/]")
        console.print(
            "[bold yellow]Hint: If you already created the sticker pack, please push it to Telegram first.[/]"
        )
        return
    # 显示当前工作目标
    console.print(f"[bold steel_blue3]Working on sticker pack: [/] "
                  f"[link=https://t.me/addstickers/{local_sticker.name}]https://t.me/addstickers/{local_sticker.name}[/link]")
    await sync_index(telegram_bot, index_file, cloud_sticker_set=now_sticker_set)


async def push_to_cloud(
        telegram_bot: AsyncTeleBot,
        index_file: pathlib.Path,
        cloud_sticker_set: StickerSet | None,
):
    """
    推送本地文件更改到云端，如果不存在则创建。
    :param telegram_bot: 电报机器人
    :param index_file: 本地索引文件
    :param cloud_sticker_set: 云端的贴纸集
    """
    try:
        local_sticker = StickerIndexFile.model_validate_json(index_file.read_text())
    except Exception as e:
        console.print(f"[bold red]Index file was corrupted: {e}[/]")
        return
    try:
        sticker_table_dir = get_stickers_path(index_file=index_file)
    except FileNotFoundError as e:
        console.print(f"[bold red]Sticker directory not found: {e}[/]")
        return
    delete_same_name_files(sticker_table_dir)
    # 获取本地文件
    local_files = {
        f.stem: f
        for f in sticker_table_dir.glob('*')
    }
    if not cloud_sticker_set:
        # TODO 413 => 'Payload Too Large',
        stickers = []
        _index = 0
        _all = len(local_files)
        with console.status("[bold yellow]Building sticker set...[/]", spinner='dots') as status:
            for sticker_file in local_files.values():
                _index += 1
                status.update(
                    f"[bold cyan]Creating sticker for file: {sticker_file.name}...[/] {_index}/{_all}"
                )
                sticker = await create_sticker(
                    sticker_type=local_sticker.sticker_type,
                    sticker_file=sticker_file
                )
                if not sticker:
                    console.print(f"[bold red]Failed to create sticker for file: {sticker_file.name}, stopping...[/]")
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
        with console.status("[bold steel_blue3]Creating sticker set...[/]", spinner='dots'):
            try:
                success = await limited_request(
                    telegram_bot.create_new_sticker_set(
                        user_id=int(local_sticker.operator_id),
                        title=local_sticker.title,
                        name=local_sticker.name,
                        stickers=stickers,
                        sticker_type=local_sticker.sticker_type
                    )
                )
                assert success, "Request failed"
            except Exception as e:
                if "USER_IS_BOT" in str(e):
                    console.print(f"[bold yellow]You cant create sticker set with a bot account: {e}[/]"
                                  f"\nAre you sure ID[{local_sticker.operator_id}] is your user id not the bot id?"
                                  )
                console.print(f"[bold red]Failed to create sticker set: {e}[/]")
                return False
        return True
    # 获取云端文件
    cloud_files = {
        sticker.file_unique_id: sticker
        for sticker in cloud_sticker_set.stickers
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
    if local_sticker.title != cloud_sticker_set.title:
        with console.status("[bold yellow]Updating title...[/]", spinner='dots'):
            await limited_request(
                telegram_bot.set_sticker_set_title(local_sticker.name, local_sticker.title)
            )
        console.print(f"[bold yellow]Title updated to: {local_sticker.title}[/]")
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
    with console.status("[bold yellow]Deleting stickers from telegram...[/]", spinner='dots') as status:
        _index = 0
        _all = len(to_delete)
        for file_id in to_delete:
            # 更新进度条
            _index += 1
            status.update(f"[bold yellow]Deleting stickers for all users: {file_id}...[/] {_index}/{_all}")
            try:
                success = await limited_request(
                    telegram_bot.delete_sticker_from_set(sticker=file_id)
                )
                assert success, "Request failed"
            except Exception as e:
                console.print(f"[bold red]Failed to delete sticker: {e}[/]")
            else:
                console.print(f"[bold dark_green]Deleted sticker: {file_id}[/]")

    # 上传文件到云端
    with console.status(f"[bold yellow]Uploading sticker...[/]", spinner='dots') as status:
        _index = 0
        _all = len(to_upload)
        for file_name in to_upload:
            _index += 1
            status.update(f"[bold yellow]Uploading sticker: {file_name}...[/] {_index}/{_all}")
            sticker_file = local_files[file_name]
            sticker = await create_sticker(sticker_type=local_sticker.sticker_type, sticker_file=sticker_file)
            if sticker:
                success = await limited_request(
                    telegram_bot.add_sticker_to_set(
                        user_id=int(local_sticker.operator_id),
                        name=local_sticker.name,
                        sticker=sticker
                    )
                )
                if success:
                    console.print(f"[bold dark_green]Uploaded sticker: {file_name}[/]")
                    # 删除本地文件
                    sticker_file.unlink()
                else:
                    console.print(f"[bold red]Failed to upload sticker: {file_name}[/]")
            else:
                console.print(f"[bold red]Failed to create sticker for file: {file_name}[/]")

    # 更新云端文件
    with console.status("[bold yellow]Correcting stickers...[/]", spinner='dots') as status:
        _index = 0
        _all = len(to_fix)
        for local_file_name, cloud_file_id in to_fix:
            _index += 1
            need_delete = local_files[local_file_name]
            status.update(
                f"[bold yellow]Correcting stickers: {local_file_name}: {cloud_file_id}...[/] {_index}/{_all}")
            try:
                # 删除本地文件
                await download_and_write_file(
                    telegram_bot=telegram_bot,
                    file_id=cloud_file_id,
                    file_unique_id=local_file_name,
                    sticker_table_dir=sticker_table_dir
                )
            except Exception as e:
                console.print(f"[bold red]Failed to correct sticker: {local_file_name} {e}[/]")
                return False
            else:
                need_delete.unlink(missing_ok=True)
                console.print(f"[bold dark_green]Corrected sticker: {local_file_name}[/]")

    if to_delete or to_upload or to_fix:
        console.print("[bold dark_green]Changes applied![/]")
    return True


@asyncclick.command()
async def push():
    """Overwrite telegram stickers using local files."""
    # 检查仓库更新
    await check_for_updates()
    """Push local file changes to Telegram."""
    local_sticker, index_file, telegram_bot = await upon_credentials()
    if not local_sticker or not index_file or not telegram_bot:
        return
    # 获取云端文件
    with console.status("[bold cyan]Retrieving sticker set from Telegram...[/]", spinner="dots"):
        try:
            sticker_set: Optional[StickerSet] = await limited_request(telegram_bot.get_sticker_set(local_sticker.name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {local_sticker.name}: {e}[/]")
                return
    console.print(
        f"[bold steel_blue3]Working on sticker pack:[/] [link=https://t.me/addstickers/{local_sticker.name}]https://t.me/addstickers/{local_sticker.name}[/link]"
    )
    try:
        backup_snapshot(index_file)
    except Exception as e:
        console.print(f"[bold red]Failed to create backup for stickers: {e}[/]")
        return

    try:
        if not await push_to_cloud(telegram_bot=telegram_bot, index_file=index_file, cloud_sticker_set=sticker_set):
            console.print("[bold red]Push aborted![/]")
    except Exception as e:
        from loguru import logger
        logger.exception(e)
        console.print(f"[bold red]Push failed: {e}[/]")
        return
    # 同步索引文件
    with console.status("[bold yellow]Synchronizing index...[/]", spinner='dots'):
        try:
            sticker_set: Optional[StickerSet] = await limited_request(telegram_bot.get_sticker_set(local_sticker.name))
        except Exception as e:
            if "STICKERSET_INVALID" in str(e):
                sticker_set = None
            else:
                console.print(f"[bold red]Failed to get sticker set {local_sticker.name}: {e}[/]")
                return
    if sticker_set:
        await sync_index(telegram_bot=telegram_bot, index_file=index_file, cloud_sticker_set=sticker_set)
        console.print(Panel(
            "[bold dark_green]🎉 Push and cleanup completed successfully![/]",
            style="green",
            title="Done",
            expand=False
        ))


cli.add_command(init)
cli.add_command(login)
cli.add_command(push)
cli.add_command(sync)
cli.add_command(trace)
cli.add_command(download)

if __name__ == "__main__":
    cli(_anyio_backend="asyncio")
