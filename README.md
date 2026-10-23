# tui-rhythm-game

a 4-key rhythm game for your terminal, made with textual

## features

- support for custom songs & beatmaps
- themes based off of default textual themes
- configurable hotkeys
- simple scoring and grading system

## install

you'll need python 3.10+ and something to play audio through.

the easiest way is with [pipx](https://pipx.pypa.io/stable/installation/):

```sh
pipx install tui-rhythm-game
```

or pip:

```sh
pip install tui-rhythm-game
```

then run it with:

```sh
tui-rhythm-game
```

to update later, run `pipx upgrade tui-rhythm-game` (or `pip install -U tui-rhythm-game`).

## how to play

pretty self-explanatory! notes will fall in 4 different lanes, left to right, with each lane corresponding to one key. by default, the keybinds are DFJK (left to right). hit the notes when they're on the hit line (or a bit before) by pressing the key that corresponds to that lane.

your score increases by 100 for every note you hit, and there's also a combo that can increase the amount of score per note hit.

you also receive a grade, based off of your accuracy - not your score.

## custom songs

custom songs live in a `.json` file, and they reference assets which you need to add as well. beatmaps (the `.json` file) go in the `beatmaps` folder, and assets (like the music files + cover images) go into the `assets` folder.
the location of the game files is listed in settings, and can vary by OS.

### beatmap editor

there's a browser-based editor in `editor/index.html`. just open it in a browser (no install needed), load your song, place notes, and hit download to get the `.json`. you can also import an existing beatmap to edit it. the controls are listed in the editor's sidebar.

## ai declaration

all AI usage on this project has been marked with the `ai:` prefix on their commits! all other code outside of these commits were completely human-written.

## license

the code is MIT licensed.

okay thanks have fun bye
