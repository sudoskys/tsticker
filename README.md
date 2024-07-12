# tsticker

[![PyPI version](https://badge.fury.io/py/tsticker.svg)](https://badge.fury.io/py/tsticker) [![Downloads](https://pepy.tech/badge/tsticker)](https://pepy.tech/project/tsticker)

## 🌟 Overview

`tsticker` is a command-line interface (CLI) tool designed to streamline the creation and management of Telegram
stickers. It automatically adjusts image sizes and suggests appropriate emojis based on image names. The tool supports
both static and animated stickers (webm format).

![intro](.github/intro.png)

## 🤖 Key Features

- 🌟 **Emoji Suggestions:** Automatically suggests emojis based on image names.
- 📐 **Automatic Image Adjustment:** Resizes and adjusts images to fit Telegram sticker requirements.
- 🖼️ **Support for Multiple Sticker Types:** Capable of managing both static and animated stickers.
- 📦 **git-like Operations:** The logic is similar to git, with commands like `init`, `push`, and `sync`.

## 📋 Prerequisites

Ensure the following dependencies are installed before using `tsticker`:

| Dependency   | Installation Link                                   |
|--------------|-----------------------------------------------------|
| **ffmpeg**   | [Download ffmpeg](https://ffmpeg.org/download.html) |
| **pngquant** | [Download pngquant](https://pngquant.org/)          |

## 🛠️ Installation

### Installing Dependencies

| System              | Commands                                                                                                                                                       |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 🐧 **Debian-based** | `sudo apt install ffmpeg`<br>`sudo apt install pngquant`                                                                                                       |
| 🍏 **macOS**        | `brew install ffmpeg`<br>`brew install pngquant`                                                                                                               |
| 🪟 **Windows**      | [Download ffmpeg](https://ffmpeg.org/download.html)<br>[Download pngquant](https://pngquant.org/)<br>Ensure both dependencies are added to your system's PATH. |

### Installing `tsticker`

Install `tsticker` using `pipx` for isolated environments:

```bash
pipx install tsticker
```

If `pipx` is not installed, install it as follows:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

## 🤖 Bot Token Setup

To create and manage stickers with `tsticker`, you need a Telegram Bot Token:

1. Open Telegram and search for the [BotFather](https://t.me/BotFather) bot.
2. Initiate a conversation with BotFather.
3. Send the command `/newbot`.
4. Follow the instructions to set your bot's name and username.
5. Upon completion, BotFather will provide an HTTP API token which serves as your `BotToken`.

## 🚀 Usage

### Initial Setup

**Login to your Telegram account:**

```bash
tsticker login -t <token> -u <user>
```

Replace `<token>` with your Telegram bot token from [BotFather](https://t.me/BotFather) and `<user>` with your Telegram
user ID (Get your user ID from [getidsbot](https://t.me/getidsbot)).

**Create a new sticker pack:**

```bash
mkdir <pack_name>
cd <pack_name>
tsticker init -n <pack_name> -t <pack_title>
```

Replace `<pack_name>` with your desired directory name and `<pack_title>` with the title for your sticker pack.

**Add stickers to your pack:**

Place your sticker images in the `<pack_name>` folder. The tool will automatically adjust the size and pick suitable
emojis based on image names.

**Push stickers to Telegram:**

```bash
tsticker push
```

**Sync stickers from Telegram to your local directory:**

```bash
tsticker sync
```

### Operations

| Operation               | Description                                                                                                |
|-------------------------|------------------------------------------------------------------------------------------------------------|
| **Adding Stickers**     | New stickers added to the folder will be recognized and pushed to Telegram upon executing `tsticker push`. |
| **Deleting Stickers**   | Stickers removed from the folder will update accordingly when synchronized.                                |
| **Renaming Pack Title** | Update the title in the JSON file and use `tsticker sync` to apply changes.                                |

## 🚧 Roadmap & ⚠️ Important Notes

| Note                                | Description                                                                                                                          |
|-------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| 📜 **No Support for Tgs Stickers**  | Only `webm` format is supported for animated stickers.                                                                               |
| ⏳ **Rate Limiting**                 | Each request is throttled to 2 seconds to prevent getting blocked by Telegram.                                                       |
| 📝 **Limited Emoji Auto-Selection** | Automatic emoji selection may not work optimally for all languages.                                                                  |
| 🚫 **Rate Limits**                  | Avoid excessive uploads in a short period to prevent Telegram from restricting your bot's actions.                                   |
| 🔒 **Security**                     | Keep your bot token secure. Stickers can only be managed through your bot or the official @Stickers bot by the sticker pack creator. |

## 📄 License

MIT License

## 🤝 Contributing

Contributions are welcome! For more details on how to get started, please refer to
our [Contributing Guide](CONTRIBUTING.md).

## 🙏 Acknowledgments

Special thanks to all contributors for making `tsticker` better. For any issues or feature requests, please use
the [GitHub issue tracker](https://github.com/sudoskys/tsticker/issues).

---

Enhance your Telegram sticker creation process with `tsticker` and become part of our community striving to simplify
sticker management through the command line!