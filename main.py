from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Digits, Footer, DataTable, OptionList
from textual.reactive import var
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from just_playback import Playback
from pyfiglet import figlet_format
from rich.text import Text
from rich_pixels import Pixels
from glob import glob
import json

# game settings
speed = 16.0 * 3
LANE_KEYS = {"d": 0, "f": 1, "j": 2, "k": 3}

class Canvas(Widget):
    music = None
    notes = []
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
            if note["time"] + 1.5 / speed + 0.12 >= now:
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
        self.ticker = self.set_interval(1 / 60, self.tick)
        self.music = Playback()
        self.music.load_file(f"assets/{self.song_path}")
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
            if note["time"] + (height - hit_line + 1) / speed < now or note.get("state") == "hit":
                continue
            if note["time"] > now + height / speed:
                break
            # calculate what height to draw the note
            note_height = int(round(hit_line - (note["time"] - now) * speed))
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
        lane = LANE_KEYS.get(event.key)
        if self.notes == [] or lane is None:
            return
        closest = min([d for d in self.notes if d.get("lane") == lane and d.get("state") is None], key=lambda t: abs(t["time"] - now), default=None)
        if not closest:
            return
        if abs(closest["time"] - now) <= (1.5 / speed) + 0.12:
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

class MenuScreen(Screen):
    BINDINGS = []
    CSS = """
    #songlist {
        width: 1fr;
        height: 100%;
    }

    #preview {
        width: 2fr;
        height: 100%;
        align: center middle;
    }

    #cover {
    }
    """

    def __init__(self):
        super().__init__()
        self.song_paths = glob("beatmaps/*.json")
        self.songlist = []
        for path in self.song_paths:
            with open(path, 'r') as file:
                temp = json.load(file)
            self.songlist.append({"path": path, "display": "[italic]" + temp.get("title", "Untitled") + "[/italic] - [bold]" + temp.get("artist", "Unknown Artist") + "[/bold]", "cover_path": temp.get("cover_path", None)})

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.switch_screen(GameScreen(self.songlist[event.option_index]["path"]))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if self.songlist[event.option_index]["cover_path"] is not None:
            cover_pixels = Pixels.from_image_path(f"assets/{self.songlist[event.option_index]["cover_path"]}", resize=(32, 32))
            self.query_one("#cover", Static).update(cover_pixels)
        else:
            self.query_one("#cover", Static).update()

    def compose(self) -> ComposeResult:
            with Horizontal(id="menu"):
                yield OptionList(*[d.get("display") for d in self.songlist], id="songlist")
                with Vertical(id="preview"):
                    yield Static(id="cover")
                    yield DataTable()
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
        self.theme = "nord"
        self.push_screen(MenuScreen())


if __name__ == "__main__":
    game = Game()

    game.run()