import hashlib
import hmac
from typing import List, Literal

from pydantic import BaseModel, model_validator


class Emote(BaseModel):
    emoji: str
    file_id: str


class StickerPack(BaseModel):
    title: str
    name: str
    sticker_type: Literal["mask", "regular", "custom_emoji"]
    operator_id: str
    lock_ns: str
    emotes: List[Emote] = []

    @model_validator(mode="after")
    def validate_lock_ns(self):
        expected_lock_ns = generate_lock_ns(
            bot_id=self.operator_id,
            name=self.name,
            sticker_type=self.sticker_type
        )
        if not hmac.compare_digest(self.lock_ns, expected_lock_ns):
            raise ValueError("metadata has been tampered")
        return self

    @classmethod
    def create(cls, title: str, name: str, sticker_type: str, operator_id: str) -> "StickerPack":
        lock_ns = generate_lock_ns(bot_id=operator_id, name=name, sticker_type=sticker_type)
        return cls(
            title=title,
            name=name,
            sticker_type=sticker_type,
            operator_id=operator_id,
            lock_ns=lock_ns
        )


def generate_lock_ns(bot_id: str, name: str, sticker_type: str) -> str:
    secret_key = bot_id.encode('utf-8')
    message = f"{name}:{sticker_type}".encode('utf-8')
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()
