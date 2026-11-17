# Game Sync server

Stripped down Game Sync server for use in the [Dream World Revival server](https://github.com/minibug1021/dreamworld-reawakened).

It is a rewrite of [Entralinked](https://github.com/kuroppoi/entralinked) in Python.

This repository is a submodule of the Dream World server and is not meant to be used on its own.

## Running

Its dependencies are part of the Dream World Revival's project, so set it up and start it from there with [uv](https://docs.astral.sh/uv/).

```
cd dreamworld-reawakened
uv sync
uv run game_sync_server/server.py
```

On Linux the server has to be started as root, because ports 53 and 443 are privileged. Run `uv sync` as your normal user, then `sudo .venv/bin/python game_sync_server/server.py`.

When it has started, the server prints an address. Enter that as the DNS server in the game's "Nintendo WFC Settings", and the DS will reach this server instead of Nintendo's.