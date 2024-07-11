import re
from typing import Literal, Optional

from loguru import logger
from pydantic import BaseModel, SecretStr, model_validator, field_validator, ConfigDict
from telebot import TeleBot, logger
from telebot.types import User

from .create import Emote


class AppSetting(BaseModel):
    pack_name: str
    pack_title: str
    bot_token: SecretStr
    bot_proxy: str | None
    bot_user: User
    owner_id: int
    sticker_type: Literal["mask", "regular", "custom_emoji"]
    needs_repainting: Optional[bool] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @staticmethod
    def make_set_name(pack_name: str, username: str):
        if "_by_" in pack_name:
            return pack_name
        return f"{pack_name}_by_{username}"

    @field_validator("pack_name", mode="before")
    def validate_pack_name(cls, value):
        # 假设 pack_name 必须符合特定正则表达式
        pattern = r'^[a-zA-Z0-9_]+$'
        if not re.match(pattern, value):
            raise ValueError(f"Invalid pack_name '{value}': must match pattern '{pattern}'")
        return value

    @field_validator("pack_title", mode="before")
    def validate_pack_title(cls, value):
        # 假设 pack_title 的长度限制为 1 到 64 个字符
        if not (1 <= len(value) <= 64):
            raise ValueError(f"Invalid pack_title '{value}': length must be between 1 and 64 characters")
        return value

    @model_validator(mode="after")
    def validate_setting(self):
        if self.needs_repainting is not None:
            if self.sticker_type != "custom_emoji":
                logger.warning("needs_repainting is only available for custom_emoji sticker type")
                self.needs_repainting = None
        return self


class AppInitError(Exception):
    pass


def get_bot_user(bot_token: str, bot_proxy: str = None) -> User:
    """
    Get bot user info
    :return: User instance
    :raise AppInitError: if bot token is invalid or bot username is invalid or other exceptions
    """
    from telebot import apihelper
    if bot_proxy:
        if "socks5://" in bot_proxy:
            bot_proxy = bot_proxy.replace("socks5://", "socks5h://")
        apihelper.proxy = {'https': bot_proxy}
    apihelper.CONNECT_TIMEOUT = 20
    bot = TeleBot(bot_token)
    try:
        me = bot.get_me()
        assert me.id, "Bot token is invalid"
        assert me.username, "Bot username is invalid"
    except AssertionError as e:
        raise AppInitError(e)
    except Exception as e:
        if "404" in str(e):
            raise AppInitError("Bot token is invalid")
        raise AppInitError(e)
    return me
