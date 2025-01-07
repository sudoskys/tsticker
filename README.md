# tsticker

[![PyPI version](https://badge.fury.io/py/tsticker.svg)](https://badge.fury.io/py/tsticker) [![Downloads](https://pepy.tech/badge/tsticker)](https://pepy.tech/project/tsticker)

## 📘 Overview

`tsticker` is a telegram sticker pack management cli.

Just put your images in the `<sticker dir>/stickers` directory and run `tsticker push` to override your cloud sticker
with local stickers.

![intro](.github/intro.png)

Or you can use the `tsticker sync` command to override your local sticker pack with the cloud sticker pack.

Simple? Yes, it is!

- Auto select emoji for sticker
- Auto resize image for sticker
- Auto convert (gif,webm,mov ...) to webm for animated sticker

## 📦 Commands

| Command             | Description                                                                                      |
|---------------------|--------------------------------------------------------------------------------------------------|
| `tsticker init`     | Initializes a new sticker pack.                                                                  |
| `tsticker sync`     | **Override**, Syncs the sticker pack from your local directory with changes from the cloud.      |
| `tsticker push`     | **Override**, Pushes changes from your local directory to the cloud, updating existing stickers. |
| `tsticker login`    | Logs in to your Telegram account.                                                                |
| `tsticker logout`   | Logs out of your Telegram account.                                                               |
| `tsticker help`     | Displays help information for the CLI.                                                           |
| `tsticker download` | Download any sticker pack from the cloud to your local directory.                                |
| `tsticker trace`    | Import cloud sticker pack from url.                                                              |

| Example                                                          | Description                                  |
|------------------------------------------------------------------|----------------------------------------------|
| `tsticker init -s regular -n 'sticker_id' -t 'My sticker title'` | Initialize a new sticker                     |
| `tsticker sync`                                                  | Sync sticker pack                            |
| `tsticker push`                                                  | Push sticker pack                            |
| `tsticker login -t <token> -u <user>`                            | Log in to Telegram                           |
| `tsticker logout`                                                | Log out of Telegram                          |
| `tsticker download -l <any sticker link>`                        | Download any sticker pack, cant make changes |
| `tsticker trace -l <sticker link>`                               | Import sticker pack(can make changes)        |

**If you encounter any issues, please [create a new Issue](https://github.com/sudoskys/tsticker/issues) on our GitHub
repository.**

## 📋 Prerequisites

Wait! Before installing `tsticker`, ensure that your computer meets the following requirements:

- [install ffmpeg](https://ffmpeg.org/download.html)

- [install ImageMagick](https://docs.wand-py.org/en/0.6.12/guide/install.html)

## Installing `tsticker`

The recommended way to install `tsticker` is through `pipx` for isolated environments:

```bash
pipx install tsticker
```

If `pipx` is not installed, install it with the following commands:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

If you want to upgrade `tsticker` to the latest version, use the following command:

```bash
pipx upgrade tsticker
```

## 🔑 Login with Telegram

We need create a bot as a bridge to manage stickers.

Remember the bot can **only** **auto** manage stickers **created by the bot itself**, once you lost your bot, you can
only manage stickers manually.

To create and manage stickers with `tsticker`, you need a **Telegram Bot Token**. Follow these steps:

1. Open Telegram and search for the [BotFather](https://t.me/BotFather) bot.
2. Start a conversation with BotFather and send the command `/newbot`.
3. Follow the instructions to create your bot and acquire the bot token.

The bot token provided by BotFather will be used as your `BotToken`.

Win + R, type `cmd`, and press Enter to open the command prompt. Run the following command to login

Replace `<token>` with your Telegram bot token and `<user>` with your Telegram user ID (you can get your user ID
from [getidsbot](https://t.me/getidsbot) by sending `/my_id`).

```bash
tsticker login -t <token> -u <user>
```

We use https://pypi.org/project/keyring/ to manage your tokens, which may require additional steps. If you encounter
problems, refer to: https://github.com/jaraco/keyring

## Adding or Removing Stickers

Just put your images in the `<pack>/stickers` directory and run `tsticker push` to override your cloud sticker pack with
the local sticker pack. We support almost all image formats, including `png`, `jpg`, `jpeg`, `gif`, `webm`, and
`mov` and so on.

Please don't operate lots of stickers at once time, if there is any error, it will break your workflow, but you can
use `tsticker sync` to recover.

```bash
tsticker push
```

even there are auto-resize and auto-convert, there still have some bad input such as too large image, too long video, so
be careful.

The name of the sticker file can be some direct emoji(like `😄some🧑` ), or you can fill in the name freely, and we will look for the most similar
emoji!

## Limitations of `tsticker`

| Note                            | Description                                                                                                          |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------|
| **No Support for Tgs Stickers** | `tgs` format is not supported for this cli. We using mixed `png` and `webm` format for static and animated stickers. |
| **Rate Limiting**               | Each request is throttled to 2 seconds to avoid being blocked by Telegram.                                           |
| **Only Bot User**               | Stickers can only be managed through your bot or the official @Stickers bot by the sticker pack creator.             |

## 📄 License

`tsticker` is released under the MIT License. See [LICENSE](LICENSE) for more information.

---

Enhance your Telegram sticker creation process with `tsticker` and become part of our community striving to simplify
sticker management through the command line!

---