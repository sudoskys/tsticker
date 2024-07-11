import json
import random
from pathlib import Path

import emoji

SERVICE_NAME = "TStickerService"
USERNAME = "telegram"

# 读取规则，本文件目录下的rules.json
rule_file = Path(__file__).parent / "rules.json"
EMOJI_RULES = json.loads(rule_file.read_text())


def get_random_emoji_from_text(text: str) -> str:
    """
    从给定的文本中提取字母并根据映射规则生成随机emoji。
    如果文本中没有匹配的字符，则返回默认emoji（❤️）。如果生成的emoji不受支持，则引发ValueError。
    :param text: 输入的字符串
    :return: 生成的emoji字符
    :raises ValueError: 如果生成的emoji不受支持
    """
    emoji_candidates = []
    # 仅处理文本中下划线后的部分
    if "_" in text:
        text = text.split("_")[-1]
    # 根据规则寻找字符映射的emoji
    for char in text:
        if char in EMOJI_RULES:
            emoji_candidates.append(EMOJI_RULES[char])
    # 未找到匹配字符使用默认emoji
    if not emoji_candidates:
        selected_emoji = "❤️"
    else:
        selected_emoji = random.choice(emoji_candidates)
    # 处理和确认emoji是有效的
    selected_emoji = emoji.emojize(emoji.demojize(selected_emoji.strip()))
    if not emoji.is_emoji(selected_emoji):
        raise ValueError(f"Emoji {selected_emoji} is not supported")
    return selected_emoji
