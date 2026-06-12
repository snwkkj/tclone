# tclone

<p align="center">
  A small command-line tool for forwarding, mirroring, and analyzing Telegram chats with Telethon.
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="https://github.com/LonamiWebs/Telethon"><img src="https://img.shields.io/badge/Telethon-1.34.0-2AABEE?logo=telegram&logoColor=white" alt="Telethon 1.34.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue" alt="GPLv3 License"></a>
</p>

## Project Structure

```text
tclone/
├── fonts/
│   ├── DejaVuSans-Bold.ttf
│   ├── DejaVuSans.ttf
│   └── Roboto-Bold.ttf
├── src/
│   ├── analyzer.py
│   ├── cli.py
│   ├── clonner.py
│   ├── config.py
│   ├── forward.py
│   ├── runtime.py
│   └── session.py
├── .env.example
├── config.yml
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Overview

`tclone` uses a Telegram user session to process messages between chats, channels, and forum topics. It provides three operating modes:

- **Forward** messages from one Telegram entity to another.
- **Mirror** a forum into a reusable backup group, including its photo and topics.
- **Analyze** the estimated media storage used by a group or channel.

The tool supports rate limiting, FloodWait handling, persistent offsets, topic links, optional author attribution removal, and local debug logs.

> [!IMPORTANT]
> Use `tclone` only with chats and content you are authorized to access. Follow the Telegram Terms of Service and the rules of each community.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/snwkkj/tclone.git
cd tclone
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install the project

```bash
pip install -e .
```

### 4. Configure Telegram credentials

Edit `config.yml`:

```yaml
api_id: 12345678
api_hash: "your_api_hash"
source: -1001234567890
target: -1009876543210
```

Telegram API credentials can be created at [my.telegram.org](https://my.telegram.org/).

For better credential isolation, leave `api_id` and `api_hash` empty in `config.yml` and create a `.env` file:

```env
API_ID=12345678
API_HASH=your_api_hash
```

### 5. Run tclone

```bash
tclone -m -1001234567890
```

On the first run, Telethon asks for your phone number, login code, and two-factor authentication password when applicable. The authenticated session is then reused.

## Usage

```text
Basic usage:
  tclone -m -1001234567890

Options:
  -h, --help      Show the help message
  -q, --quiet     Hide terminal output and progress indicators
  -d, --debug     Write detailed logs to log.log
  -c, --config    Open the active config.yml
  -f, --forward   Forward messages (default mode)
  -m, --mirror    Mirror a Telegram forum into a backup group
  -a, --analyzer  Generate a storage report for a group or channel
  -s, --source    Override the configured source
  -t, --target    Override the configured target
```

### Forward messages

Forward mode is the default:

```bash
tclone
```

Override the source and target from the command line:

```bash
tclone -f -s -1001234567890 -t -1009876543210
```

Topic and message links are also accepted:

```bash
tclone -f \
  -s https://t.me/c/1234567890/42 \
  -t https://t.me/c/9876543210/10
```

### Mirror a forum

Create or reuse a backup group and mirror the source forum topics:

```bash
tclone -m -1001234567890
```

Mirror mode can:

- Create a `[backup]` group.
- Copy the source group photo.
- Add a configurable `BACKUP` banner to the copied photo.
- Recreate forum topics in the backup group.
- Resume topic messages using `offset.json`.
- Skip deleted topic markers returned by Telegram.

The current mirror implementation is designed for Telegram forums. A non-forum source can create the backup group, but its regular message history is not mirrored.

### Analyze storage

Analyze a group or channel:

```bash
tclone -a -1001234567890
```

The analyzer creates:

- A text summary with message and estimated media totals.
- A PNG chart grouped by media type.

Telegram exposes metadata rather than a complete storage accounting API, so report sizes should be treated as estimates.

### Other examples

```bash
# Run quietly
tclone -q -m -1001234567890

# Enable detailed logs
tclone -d -m -1001234567890

# Open the active configuration file
tclone -c
```

## Configuration

The default `config.yml` contains:

```yaml
api_id:
api_hash: ""
source: -1000000000
target: -1000000000

batch_size: 100
message_delay_s: 1.0

pause_every_messages: 1000
pause_duration_s: 700

drop_author: true
ignore_topics: []

banner:
  enabled: true
  text: "BACKUP"
  font_file: "Roboto-Bold"
  band_color: "#9b0000"
  band_alpha: 90
```

### Main settings

| Setting | Description |
| --- | --- |
| `api_id` | Telegram application ID. Can be supplied through `API_ID`. |
| `api_hash` | Telegram application hash. Can be supplied through `API_HASH`. |
| `source` | Source chat, channel, username, or `t.me` link. |
| `target` | Destination chat, channel, username, or `t.me` link. |
| `batch_size` | Number of messages requested per batch. |
| `message_delay_s` | Delay between processed messages. |
| `pause_every_messages` | Number of messages processed before a longer pause. |
| `pause_duration_s` | Duration of the longer pause in seconds. |
| `drop_author` | Request forwarding without original author attribution. |
| `ignore_topics` | Topic IDs or links that should be skipped. |
| `reports_dir` | Optional custom directory for analyzer reports. |

### Supported entity formats

```text
-1001234567890
channel_username
https://t.me/channel_username
https://t.me/c/1234567890/42
```

### Ignoring topics

```yaml
ignore_topics:
  - 42
  - https://t.me/c/1234567890/114
```

## Runtime Files

When a `config.yml` exists in the current directory or in an editable project checkout, runtime files are stored beside it:

| File | Purpose |
| --- | --- |
| `config.yml` | Runtime configuration. |
| `.env` | Optional API credential overrides. |
| `session.session` | Authenticated Telethon session. |
| `offset.json` | Resume state for forwarded and mirrored messages. |
| `log.log` | Detailed output created with `--debug`. |

Without a project configuration, the default application directory is:

```text
Linux / Termux: ~/.tclone/
macOS:          ~/Library/Application Support/tclone/
Windows:        C:\Users\<user>\tclone\
```

Analyzer reports are saved to the system Pictures directory unless `reports_dir` is configured.

## Termux

Pillow may require native libraries on Termux:

```bash
pkg update -y
pkg install -y \
  python \
  clang \
  make \
  zlib \
  freetype \
  libjpeg-turbo \
  libpng \
  libwebp \
  libtiff \
  littlecms

python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

Verify Pillow after installation:

```bash
python -c "from PIL import Image; print('Pillow OK')"
```

## Development

Install the project in editable mode:

```bash
pip install -e .
```

Compile-check the source files:

```bash
python -m compileall -q src
```

Build a wheel:

```bash
python -m pip wheel . --no-deps -w dist
```

## License

This project is distributed under the [GNU General Public License v3.0](LICENSE).
