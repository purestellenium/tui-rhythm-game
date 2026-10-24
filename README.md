# tui-rhythm-game

a 4-key rhythm game for your terminal, made with textual

## features

- support for custom songs & beatmaps
- record your own beatmaps by tapping along to the song
- themes based off of default textual themes
- configurable hotkeys
- timing judgements, health, grades, and high scores for every song
- audio offset calibration

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

every hit is judged by how close it was to the hit line: **perfect** (within 45ms) is worth 300, **great** (90ms) is worth 200, and **good** (135ms) is worth 100. your combo multiplies that, going up every 10 notes (up to 4x). pressing a key way too early doesn't do anything, so you won't lose your combo for a stray tap.

missing notes drains your health bar, and hitting them fills it back up. if it hits zero you fail (you can turn on **no fail** in settings if you'd rather not).

you also receive a grade, based off of your accuracy - not your score. perfects count fully, greats count for 2/3, goods for 1/3. your best score and best grade for each song show up in the menu.

### settings

press `2` in the menu to open settings. you can change the theme, scroll speed, and lane keys there.

if notes feel early or late, try **calibrate offset**: it plays a click track, you tap along, and it works out your audio delay for you (bluetooth headphones usually need this). you can also nudge the **audio offset** by hand.

## custom songs

custom songs live in a `.json` file, and they reference assets which you need to add as well. beatmaps (the `.json` file) go in the `beatmaps` folder, and assets (like the music files + cover images) go into the `assets` folder.
the location of the game files is listed in settings, and can vary by OS.

a beatmap looks something like this:

```json
{
 "title": "song name",
 "artist": "artist name",
 "bpm": 170,
 "offset": 0.5,
 "start_at": 0.0,
 "cover_path": "song.jpg",
 "song_path": "song.mp3",
 "notes": [
  {"beat": 0.0, "lane": 0},
  {"beat": 1.5, "lane": 3}
 ]
}
```

`offset` is when beat 0 happens in the song (in seconds), and `start_at` is where gameplay starts. lanes go from 0 to 3, left to right.

press `r` in the menu to reload songs after adding or editing them. if a beatmap has a mistake in it, it'll show up greyed out, and the preview will tell you what's wrong.

### recording beatmaps

the easiest way to make a beatmap is to record it. make a `.json` with everything above but an empty `notes` list, then highlight it in the menu and press `e`. the song plays, and you tap along using your lane keys (`backspace` undoes the last tap).

when you stop (or the song ends), pick what grid to snap your taps to (1/4 beat is a good start, 1/3 or 1/6 for triplets), and choose whether to **replace** the notes or **add** to the existing ones. adding lets you build a chart up in a few passes, like one hand at a time.

### beatmap editor

there's a browser-based editor in `editor/index.html`. just open it in a browser (no install needed), load your song, place notes, and hit download to get the `.json`. you can also import an existing beatmap to edit it. the controls are listed in the editor's sidebar.

## ai declaration

all AI usage on this project has been marked with the `ai:` prefix on their commits! all other code outside of these commits were completely human-written.

## license

the code is MIT licensed.

okay thanks have fun bye
