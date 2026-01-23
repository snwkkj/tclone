# tclone

![License](https://img.shields.io/badge/License-GPLv3-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat&logo=python&logoColor=white)

Minimal Telegram message "clone" tool built on [Telethon](https://github.com/LonamiWebs/Telethon).

## Project Structure

```text
├── .env.example
├── config.yml
├── main.py
├── requirements.txt
├── README.md
└── src
    └── tclone
        ├── __init__.py
        ├── analyzer.py
        ├── clonner.py
        ├── config.py
        ├── forward.py
        └── session.py
```

It reads a `config.yml` (or optional `.env`), logs in using a Telethon session, and provides three main modes:
- **Mirror**: Clone messages from source to a backup group
- **Forward**: Forward messages with optional attribution control
- **Analyze**: Generate storage usage reports for target chats/channels

All modes include rate limiting, automatic resume via offset files, and FloodWait handling.

## Features

- **Mirror mode**: Clone messages to backup group
- **Forward mode**: Forward messages with attribution control
- **Analyze mode**: Generate storage usage reports (text + PNG graph)
- Supports IDs, usernames, and `t.me` links (including topic/message links)
- Resume support via `offset.json`
- FloodWait handling with countdowns
- Rate limiting (delay + periodic long pause)
- Optional `.env` support for API credentials
- `--settings` helper to open `config.yml` in your default system editor

## Requirements

- Python 3.8+
- Telegram API credentials (`api_id` and `api_hash`)

## Installation

### Option 1: From source (recommended)

Clone the repository:

```bash
git clone https://github.com/snowzf4/tclone.git
cd tclone
```

Create and activate a virtual environment (optional, recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install the project:

```bash
pip install -e .
```

### Termux (Android) notes (Pillow)

If you use Termux, Pillow may need native libraries and a compiler toolchain.

1) Update packages:

```bash
pkg update -y
pkg upgrade -y
```

2) Install Pillow dependencies (required):

```bash
pkg install -y \
  libjpeg-turbo \
  libpng \
  freetype \
  libwebp \
  libtiff \
  littlecms \
  zlib \
  clang \
  make
```

3) Install Python tooling (recommended):

```bash
pkg install -y python
python -m pip install --upgrade pip setuptools wheel
```

4) Install the project:

```bash
pip install -r requirements.txt
```

Or (editable install):

```bash
pip install -e .
```

5) Quick check that Pillow is OK:

```bash
python -c "from PIL import Image; print('Pillow OK')"
```

## Configuration

### Option 1: config.yml (default)

Create a `config.yml` in the folder where you will run the tool:

```yml
api_id: 0
api_hash: ""
source: -1000000000000
target: -1000000000000

batch_size: 100
message_delay_s: 1.0

pause_every_messages: 1000
pause_duration_s: 300

session_name: "session"
log_file: "log.log"
offset_file: "offset.json"
drop_author: true
```

### Option 2: .env file (optional)

Create a `.env` file (or copy `.env.example`) to override API credentials:

```env
API_ID=
API_HASH=
```

The `.env` file only needs to contain `API_ID` and `API_HASH`. Other settings remain in `config.yml`.

### Notes

- `source` / `target` examples:
  - Numeric ID: `-1001234567890`
  - Username: `somechannel`
  - Link: `https://t.me/c/1234567890/114`

## Usage

### Basic modes

```bash
# Forward mode (default): forward messages
tclone

# Mirror mode: create/reuse a backup group and mirror topics
tclone -m

# Analyze mode: generate storage report
tclone -a
```

### Command options

```text
-h, --help      Show this help message and exit
-q, --quiet     Run in silent mode (no terminal output, no spinner)
-l, --logs      Write detailed execution logs to log.log
-d, --delete    Delete session file and offsets.json, then exit
-c, --config    Open config.yml in the default editor and exit
-f, --forward   Forward mode (default)
-m, --mirror    Mirror a group: create a [backup] group, copy photo, and create topics
-a, --analyzer  Analyze a target chat and generate a storage report (txt + png)
-s, --source    Override source chat/channel (ignores config.yml source)
-t, --target    Override target chat/channel (ignores config.yml target)
```

### Examples

Quiet mode:
```bash
tclone --quiet
```

Write logs to `log.log`:
```bash
tclone --logs
```

Open settings:
```bash
tclone --settings
```

Clean session + offset:
```bash
tclone --clean
```

Forward mode:
```bash
tclone --forward
```

Analyze storage:
```bash
tclone -a

# Shorthand target (no --target needed)
tclone -a -1001234567890
```

Mirror with shorthand source:
```bash
tclone -m -1001234567890
```

## Files

- `config.yml`: runtime configuration
- `.env` / `.env.example`: optional API credentials override
- `session.session`: Telethon session (created after first login)
- `offset.json`: last processed message id for resume
- `log.log`: optional logs (enabled with `--logs`)
- Analyzer reports: `<chat_or_channel_name>.txt` and `<chat_or_channel_name>.png` (analyzer mode)

By default, config/session/offset/log/fonts are stored in a per-user application directory:

```text
Linux / Termux: ~/.tclone/
Windows: C:\Users\<you>\tclone\
```

Analyzer reports are saved to your Pictures folder by default:

```text
Linux: ~/Pictures (or XDG Pictures dir)
Termux: ~/storage/pictures
Windows: C:\Users\<you>\Pictures\
```

You can override the analyzer output folder via `reports_dir` in `config.yml`.

If a local `config.yml` exists in the current directory, files are stored locally instead.

Use `--settings` to open the active `config.yml`.

## Dependencies

- `python-dotenv==1.2.1` - Environment variable support
- `telethon==1.34.0` - Telegram client library
- `pyyaml==6.0.3` - YAML configuration parsing
- `pillow==10.0.0` - Image processing for analyzer charts

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

## Disclaimer

Use responsibly and comply with Telegram ToS and the rules of the chats you interact with.
