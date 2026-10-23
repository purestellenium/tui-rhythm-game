from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Digits, Footer, DataTable, OptionList, TabbedContent, TabPane, Select, Button, Label
from textual.reactive import var
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from just_playback import Playback
from pyfiglet import figlet_format
from rich.text import Text
from rich_pixels import Pixels
from PIL import Image
from textual.color import Color
from pathlib import Path
import json

from tui_rhythm_game.settings import PACKAGE_DIR, USER_DIR, SPEED_MIN, SPEED_MAX, SPEED_STEP, DEFAULTS, ensure_user_dirs, load_settings, save_settings

def assets_dir(chart_path: str) -> Path:
    """Charts live in <root>/beatmaps/, so their audio + covers live in <root>/assets/."""
    return Path(chart_path).parent.parent / "assets"

class Canvas(Widget):
    music = None
    notes = []
    speed = DEFAULTS["speed"] * 4.0
    lane_keys = {}
    can_focus = True
    hits = 0
    misses = 0
    combo = var(0, init=False)
    max_combo = 0
    score = var(0, init=False)
    timeout = None

    def watch_combo(self, old: int, new: int) -> None:
        self.screen.query_one("#combo", Static).update("COMBO: " + str(self.combo))

    def watch_score(self, old: int, new: int) -> None:
        self.screen.query_one("#score", Static).update("SCORE: " + str(self.score))

    def flashHud(self, type: str) -> None:
        if self.timeout is not None:
            self.timeout.stop()
        self.screen.query_one("#hud", Horizontal).remove_class("hit", "miss")
        self.screen.query_one("#hud", Horizontal).add_class(type)
        self.timeout = self.set_timer((0.5 * 60 / self.bpm), lambda: self.screen.query_one("#hud", Horizontal).remove_class(type))

    def tick(self) -> None:
        now = self.elapsed()
        for note in self.notes:
            if note["time"] + 1.5 / self.speed + 0.12 >= now:
                break
            if note.get("state") is not None:
                continue
            self.flashHud("miss")
            note["state"] = "missed"
            self.misses += 1
            self.max_combo = max(self.combo, self.max_combo)
            self.combo = 0
        if not self.music.active:
            self.ticker.stop()
            self.max_combo = max(self.combo, self.max_combo)
            self.app.switch_screen(ResultsScreen(
                chart_path=self.screen.chart_path,
                title=self.title, artist=self.artist,
                score=self.score, max_combo=self.max_combo,
                hits=self.hits, misses=self.misses,
            ))
        self.refresh()

    def on_mount(self) -> None:
        self.title = self.screen.title
        self.artist = self.screen.artist
        self.notes = self.screen.notes
        self.bpm = self.screen.bpm
        self.start_at = self.screen.start_at
        self.song_path = self.screen.song_path
        self.speed = self.app.settings["speed"] * 4.0
        self.lane_keys = {key: lane for lane, key in enumerate(self.app.settings["lane_keys"])}
        self.ticker = self.set_interval(1 / 60, self.tick)
        self.music = Playback()
        self.music.load_file(str(assets_dir(self.screen.chart_path) / self.song_path))
        self.music.play()
        self.music.seek(self.start_at)

    def elapsed(self) -> float:
        if self.music is None:
            return 0.0
        return self.music.curr_pos

    def render(self) -> Text:
        """Draws the game canvas based off of the current tick."""
        now = self.elapsed()
        lane_width = self.size.width // 4 - 1
        width = lane_width * 4 + 4
        height = self.size.height
        hit_line = self.size.height - 5

        # build the grid
        grid = [["-"] * width if i == hit_line else [" "] * width for i in range(height)]

        # populate the grid
        for note in self.notes:
            if note["time"] + (height - hit_line + 1) / self.speed < now or note.get("state") == "hit":
                continue
            if note["time"] > now + height / self.speed:
                break
            # calculate what height to draw the note
            note_height = int(round(hit_line - (note["time"] - now) * self.speed))
            # note is drawn on the note_height + 1 above + 1 below
            # get index for the first X of the note
            i = note["lane"] * (lane_width + 1)
            for j in range(3):
                k = note_height + (j - 1)
                if 0 <= k < height:
                    grid[k][i:i+lane_width] = ["█"] * lane_width


        # return grid as a string
        return Text("\n".join("".join(r) for r in grid))

    def on_key(self, event) -> None:
        now = self.elapsed()
        lane = self.lane_keys.get(event.key)
        if self.notes == [] or lane is None:
            return
        closest = min([d for d in self.notes if d.get("lane") == lane and d.get("state") is None], key=lambda t: abs(t["time"] - now), default=None)
        if not closest:
            return
        if abs(closest["time"] - now) <= (1.5 / self.speed) + 0.12:
            self.flashHud("hit")
            closest["state"] = "hit"
            self.hits += 1
            self.combo += 1
            self.score += (100 * min(self.combo // 10 + 1, 4))
        else:
            self.flashHud("miss")
            self.misses += 1
            self.max_combo = max(self.combo, self.max_combo)
            self.combo = 0
        
class GameScreen(Screen):
    CSS = """
        #hud {
            dock: top;
            height: auto;
            align: center top;
            padding: 1;
            background: $surface;
        }
    
        #hud.miss {
            background: $error;
        }
    
        #hud.hit {
            background: $success;
        }
    
        #hud Static {
            width: 1fr;
            text-align: center;
        }
    
        Canvas {
            color: $primary;
        }
        """

    def __init__(self, chart_path: str) -> None:
            super().__init__()
            
            # load chart settings

            with open(chart_path, 'r') as file:
                chart = json.load(file)

            self.chart_path = chart_path
            self.title = chart.get("title", "Untitled")

            self.artist = chart.get("artist", "Unknown Artist")
            self.notes = chart.get("notes", [])
            self.bpm = chart["bpm"]
            self.chart_offset = chart.get("offset", 0.0)
            self.start_at = chart.get("start_at", 0.0)
            self.song_path = chart.get("song_path")

            # convert beatmap to seconds

            for note in self.notes:
                note["time"] = self.chart_offset + note["beat"] * 60 / self.bpm
                if note["time"] < self.start_at:
                    note["state"] = "skipped"
    
    def compose(self) -> ComposeResult:
        yield Canvas()
        with Horizontal(id="hud"):
            yield Static("SCORE: 0", id="score")
            yield Static("COMBO: 0", id="combo")

class KeyBindButton(Button):
    """Button for one lane's key. Press it, then press the new key (escape cancels)."""

    def __init__(self, lane: int, key: str) -> None:
        super().__init__(id=f"lane_{lane}", classes="keybind")
        self.lane = lane
        self.key = key
        self.listening = False
        self.update_label()

    def update_label(self) -> None:
        if self.listening:
            self.label = f"Lane {self.lane + 1}: press a key..."
        else:
            self.label = f"Lane {self.lane + 1}: [bold]{self.key.upper()}[/bold]"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.listening = True
        self.update_label()

    def on_blur(self) -> None:
        self.listening = False
        self.update_label()

    def on_key(self, event) -> None:
        if not self.listening:
            return
        # swallow the key so it doesn't trigger bindings (tab, enter, etc.)
        event.stop()
        event.prevent_default()
        self.listening = False
        if event.key != "escape":
            self.screen.rebind_lane(self, event.key)
        self.update_label()

class MenuScreen(Screen):
    BINDINGS = []
    CSS = """
    #songlist {
        width: 1fr;
        height: 100%;
    }

    #settings {
        padding: 1 2;
    }

    #settings .setting {
        height: auto;
        margin-bottom: 1;
    }

    #settings .setting-name {
        width: 16;
        padding: 1 0;
        text-style: bold;
    }

    #theme_select { width: 32; }

    #speed_value {
        width: 8;
        padding: 1 0;
        text-align: center;
    }

    #speed_down, #speed_up { min-width: 5; }

    .keybind { margin-right: 1; }

    #songs_folder { width: 100%; color: $text-muted; }

    #preview {
        width: 2fr;
        height: 100%;
        align: center middle;
        border: round $primary;
        border-title-align: center;
        border-subtitle-align: center;
    }

    #preview > * { width: auto; }

    #cover { width: 48; height: 24; margin: 1; }
    """

    def cover_color(self, path: Path) -> Color:
        r, g, b = Image.open(path).convert("RGB").resize((1, 1)).getpixel((0, 0))
        color = Color(r, g, b)
        if color.brightness < 0.4:
            color = color.lighten(0.3)
        return color

    def format_length(self, seconds: float) -> str:
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"

    def __init__(self):
        super().__init__()
        # bundled songs first, then any the user dropped into their songs folder
        self.song_paths = sorted((PACKAGE_DIR / "beatmaps").glob("*.json")) + sorted((USER_DIR / "beatmaps").glob("*.json"))
        self.songlist = []
        for path in self.song_paths:
            try:
                with open(path, 'r') as file:
                    temp = json.load(file)
            except (OSError, ValueError):
                continue
            song_assets = assets_dir(path)
            playable = temp.get("song_path") is not None and (song_assets / temp["song_path"]).is_file()
            display = "[italic]" + temp.get("title", "Untitled") + "[/italic] - [bold]" + temp.get("artist", "Unknown Artist") + "[/bold]"
            if not playable:
                display = "[dim]" + display + " (audio missing)[/dim]"
            cover_path = None
            if temp.get("cover_path") is not None and (song_assets / temp["cover_path"]).is_file():
                cover_path = song_assets / temp["cover_path"]
            self.songlist.append({"path": str(path), "display": display, "playable": playable, "song_path": temp.get("song_path"), "cover_path": cover_path, "title": temp.get("title", "Untitled"), "artist": temp.get("artist", "Unknown Artist"), "bpm": temp.get("bpm")})
            if cover_path is not None:
                self.songlist[-1]["color"] = self.cover_color(cover_path)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        song = self.songlist[event.option_index]
        if not song["playable"]:
            self.app.notify(f"Put {song['song_path']} in {USER_DIR / 'assets'} to play this song.", title="Audio missing", severity="error")
            return
        self.app.switch_screen(GameScreen(song["path"]))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        song = self.songlist[event.option_index]
        preview = self.query_one("#preview", Vertical)
        preview.border_title = song["title"]
        preview.border_subtitle = song["artist"]
        if song.get("color", None) is not None:
            preview.styles.border = ("round", song["color"])
        else:
            preview.styles.border = ("round", self.app.theme_variables["primary"])

        if song['cover_path'] is not None:
            cover_pixels = Pixels.from_image_path(song["cover_path"], resize=(48, 48))
            self.query_one("#cover", Static).update(cover_pixels)
        else:
            self.query_one("#cover", Static).update()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "theme_select" or event.value == Select.BLANK:
            return
        self.app.theme = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id not in ("speed_down", "speed_up"):
            return
        step = SPEED_STEP if event.button.id == "speed_up" else -SPEED_STEP
        speed = min(max(self.app.settings["speed"] + step, SPEED_MIN), SPEED_MAX)
        self.app.settings["speed"] = speed
        save_settings(self.app.settings)
        self.query_one("#speed_value", Label).update(f"{speed:.1f}")

    def rebind_lane(self, button: KeyBindButton, key: str) -> None:
        keys = self.app.settings["lane_keys"]
        if key in keys and keys.index(key) != button.lane:
            self.app.notify(f"{key.upper()} is already bound to lane {keys.index(key) + 1}.", severity="warning")
            return
        keys[button.lane] = key
        button.key = key
        save_settings(self.app.settings)

    def compose(self) -> ComposeResult:
            with TabbedContent():
                with TabPane("Songs", id="songs_tab"):
                    with Horizontal(id="menu"):
                        yield OptionList(*[d.get("display") for d in self.songlist], id="songlist")
                        with Vertical(id="preview"):
                            yield Static(id="cover")
                with TabPane("Settings", id="settings_tab"):
                    with VerticalScroll(id="settings"):
                        with Horizontal(classes="setting"):
                            yield Label("Theme", classes="setting-name")
                            themes = sorted(self.app.available_themes)
                            yield Select([(name, name) for name in themes], value=self.app.theme, allow_blank=False, id="theme_select")
                        with Horizontal(classes="setting"):
                            yield Label("Scroll speed", classes="setting-name")
                            yield Button("-", id="speed_down")
                            yield Label(f"{self.app.settings['speed']:.1f}", id="speed_value")
                            yield Button("+", id="speed_up")
                        with Horizontal(classes="setting"):
                            yield Label("Lane keys", classes="setting-name")
                            for lane, key in enumerate(self.app.settings["lane_keys"]):
                                yield KeyBindButton(lane, key)
                        yield Label(f"Custom songs folder: {USER_DIR}\n(charts go in beatmaps/, audio + covers in assets/)", id="songs_folder")
            yield Footer()

class ResultsScreen(Screen):
    GRADES = [(1.0, "SS"), (0.95, "S"), (0.90, "A"), (0.80, "B"), (0.70, "C")]
    BINDINGS = [
        ("escape", "menu", "Menu"),
        ("r", "retry", "Retry"),
    ]
    CSS = """
    #stats_container {
        width: 2fr;
        margin: 1;
        align: center middle;
    }

    #score_container {
        align: center middle;
        width: 1fr;
        padding: 1;
    }

    #score_container > * {
        width: auto;
    }

    #stats, #song {
        margin: 1;
    }

    #score {
        text-style: bold;
    }

    """
    def __init__(self, chart_path: str, title: str, artist: str, score: int, max_combo: int, hits: int, misses: int) -> None:
        super().__init__()
        self.chart_path = chart_path
        self.title = title
        self.artist = artist
        self.score = score
        self.max_combo = max_combo
        self.hits = hits
        self.misses = misses
        if hits + misses == 0:
            self.accuracy = 0
        else:
            self.accuracy = hits / (hits + misses)

    def on_mount(self) -> None:
        table = self.query_one("#stats", DataTable)
        table.add_columns("stat", "value")
        table.add_rows([
            ("Hits", str(self.hits)),
            ("Misses", str(self.misses)),
            ("Max Combo", str(self.max_combo))
        ])

    def action_retry(self) -> None:
        self.app.switch_screen(GameScreen(self.chart_path))

    def action_menu(self) -> None:
        self.app.switch_screen(MenuScreen())

    def compose(self) -> ComposeResult:
        with Horizontal(id="results"):
            with Vertical(id="score_container"):
                yield Static(figlet_format(next((letter for cutoff, letter in self.GRADES if self.accuracy >= cutoff), "D"), font="ansi_regular"))
                yield Digits(str(self.score), id="score")
            with Vertical(id="stats_container"):
                yield Static("[italic]" + self.title + "[/italic] - [bold]" + self.artist + "[/bold]", id="song")
                yield DataTable(id="stats", show_header=False, zebra_stripes=True, cursor_type="none")
        yield Footer()
            

class Game(App):
    def on_mount(self) -> None:
        ensure_user_dirs()
        self.settings = load_settings()
        if self.settings["theme"] not in self.available_themes:
            self.settings["theme"] = DEFAULTS["theme"]
        self.theme = self.settings["theme"]
        # save themes picked anywhere (settings tab or the command palette)
        self.theme_changed_signal.subscribe(self, self.save_theme)
        self.push_screen(MenuScreen())

    def save_theme(self, theme) -> None:
        if self.settings["theme"] != theme.name:
            self.settings["theme"] = theme.name
            save_settings(self.settings)


def main() -> None:
    game = Game()

    game.run()

if __name__ == "__main__":
    main()