# tui-rhythm-game
A 4-lane rhythm game for your terminal.

## Install

```sh
pipx install git+https://github.com/purestellenium/tui-rhythm-game
# or, from a local clone:
pipx install .
```

Then run `tui-rhythm-game`.

To run from source instead: `pip install -r requirements.txt`, then `python -m tui_rhythm_game`.

## Settings

The **Settings** tab in the menu has the theme, scroll speed (5.0–15.0) and lane keys (default `D F J K`). Changes save automatically.

## Custom songs

Drop your own songs into the custom songs folder (its exact path is shown in the Settings tab):

| OS      | Folder                                    |
| ------- | ----------------------------------------- |
| Windows | `%LOCALAPPDATA%\tui-rhythm-game`          |
| macOS   | `~/Library/Application Support/tui-rhythm-game` |
| Linux   | `~/.local/share/tui-rhythm-game`          |

It uses the same layout as the bundled songs: charts go in `beatmaps/`, and the audio + cover files they reference (`song_path`, `cover_path`) go in `assets/`.

For example, the `crystallized` chart in this repo isn't shipped with the package (the audio is copyrighted). To play it, copy `tui_rhythm_game/beatmaps/crystallized.json` into `beatmaps/`, `tui_rhythm_game/assets/crystallized.jpg` into `assets/`, and supply your own `crystallized.mp3` in `assets/`.
