from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Digits, Footer, DataTable, OptionList, TabbedContent, TabPane, Tabs, Button, Label, ProgressBar
from textual.reactive import var
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.message import Message
from textual.widgets.option_list import Option
from textual.keys import format_key
from just_playback import Playback
from platformdirs import user_cache_path
from pyfiglet import figlet_format
from rich.text import Text
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from rich_pixels import Pixels
from PIL import Image
from textual.color import Color
from pathlib import Path
from statistics import median
from array import array
from time import perf_counter
import math
import wave

from tui_rhythm_game.settings import APP_NAME, PACKAGE_DIR, USER_DIR, SPEED_MIN, SPEED_MAX, SPEED_STEP, OFFSET_MIN, OFFSET_MAX, OFFSET_STEP, DEFAULTS, ensure_user_dirs, load_settings, save_settings, score_key, load_scores, save_scores
from tui_rhythm_game.charts import ChartError, assets_dir, load_chart, snap_taps, save_notes

GRADES = [(1.0, "SS"), (0.95, "S"), (0.90, "A"), (0.80, "B"), (0.70, "C")]

# how far off (in seconds) a press can be for each judgement, tightest first
JUDGEMENTS = [(0.045, "perfect"), (0.09, "great"), (0.135, "good")]
HIT_WINDOW = JUDGEMENTS[-1][0]
# presses earlier than a hit but within this count as a miss, anything earlier is ignored
MISS_WINDOW = 0.18
POINTS = {"perfect": 300, "great": 200, "good": 100}
ACCURACY_WEIGHTS = {"perfect": 1.0, "great": 2 / 3, "good": 1 / 3, "miss": 0.0}
HEALTH_CHANGE = {"perfect": 2, "great": 1, "good": 0, "miss": -8}
# theme variables used to color each judgement (and plain key presses)
JUDGEMENT_COLORS = {"perfect": "success", "great": "accent", "good": "warning", "miss": "error", "press": "secondary"}
FLASH_TIME = 0.15

# notes per second -> difficulty label shown in the song preview
DIFFICULTIES = [(2.0, "Easy"), (4.0, "Normal"), (6.0, "Hard")]

def grade(accuracy: float) -> str:
    return next((letter for cutoff, letter in GRADES if accuracy >= cutoff), "D")

def accuracy(counts: dict) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0
    return sum(ACCURACY_WEIGHTS[name] * count for name, count in counts.items()) / total

def key_label(key: str) -> str:
    """Textual key names as they're printed on the keyboard, e.g. "comma" -> ","."""
    return format_key(key).upper()

def format_length(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"

def draw_lanes(width: int, height: int, hit_line: int, lane_keys: list, flashes: dict, now: float, app: App) -> tuple:
    """Empty lane grid with the hit line and key labels, lit up for lanes with an active flash.
    Returns (grid, lane_width, styles) where styles is a list of (row, start, end, style)."""
    lane_width = max(width // 4 - 1, 1)
    width = lane_width * 4 + 4
    grid = [["-"] * width if i == hit_line else [" "] * width for i in range(height)]
    label_row = hit_line + 2
    styles = []
    for lane, key in enumerate(lane_keys):
        start = lane * (lane_width + 1)
        if 0 <= label_row < height:
            label = key_label(key)[:lane_width].center(lane_width)
            grid[label_row][start:start + lane_width] = list(label)
        flash = flashes.get(lane)
        if flash is None or flash[1] < now:
            continue
        style = "bold " + app.theme_variables[JUDGEMENT_COLORS[flash[0]]]
        if 0 <= hit_line < height:
            grid[hit_line][start:start + lane_width] = ["━"] * lane_width
            styles.append((hit_line, start, start + lane_width, style))
        if 0 <= label_row < height:
            styles.append((label_row, start, start + lane_width, style))
    return grid, lane_width, styles

class AudioClock:
    """Smooths Playback.curr_pos, which only moves every ~10ms (and unevenly), by running off the system clock
    between updates and easing towards the audio whenever it reports a new position."""

    def __init__(self, music: Playback) -> None:
        self.music = music
        self.anchor_pos = 0.0
        self.anchor_time = perf_counter()
        self.last_pos = None

    def time(self) -> float:
        pos = self.music.curr_pos
        now = perf_counter()
        if not self.music.playing:
            self.anchor_pos, self.anchor_time, self.last_pos = pos, now, pos
            return pos
        predicted = self.anchor_pos + (now - self.anchor_time)
        if pos != self.last_pos:
            self.last_pos = pos
            # jump straight to the audio after a seek or a stall, otherwise ease towards it so notes don't stutter
            predicted = pos if abs(predicted - pos) > 0.05 else predicted + (pos - predicted) * 0.1
            self.anchor_pos, self.anchor_time = predicted, now
        return predicted

class LaneView(Widget):
    """Draws a lane grid through Textual's line API. Handing over ready-made lines skips the
    text wrapping and cleanup Textual would otherwise do on the whole canvas every frame."""

    lines = []
    built_size = None
    dirty = True

    def frame(self) -> tuple:
        """Returns (grid, styles) for the current moment, see draw_lanes."""
        raise NotImplementedError

    def redraw(self) -> None:
        self.dirty = True
        self.refresh()

    def build_lines(self) -> list:
        grid, styles = self.frame()
        base = self.rich_style
        row_styles = {}
        for row, start, end, style in styles:
            row_styles.setdefault(row, []).append((start, end, base + Style.parse(style)))
        lines = []
        for y, row in enumerate(grid):
            segments = []
            position = 0
            for start, end, style in sorted(row_styles.get(y, [])):
                segments.append(Segment("".join(row[position:start]), base))
                segments.append(Segment("".join(row[start:end]), style))
                position = end
            segments.append(Segment("".join(row[position:]), base))
            lines.append(Strip(segments).extend_cell_length(self.size.width, base))
        return lines

    def render_line(self, y: int) -> Strip:
        if self.dirty or self.built_size != self.size:
            self.lines = self.build_lines()
            self.built_size = self.size
            self.dirty = False
        if y < len(self.lines):
            return self.lines[y]
        return Strip.blank(self.size.width, self.rich_style)

class Canvas(LaneView):
    music = None
    notes = []
    flashes = {}
    speed = DEFAULTS["speed"] * 4.0
    lane_keys = {}
    can_focus = True
    combo = var(0, init=False)
    max_combo = 0
    score = var(0, init=False)
    health = var(100.0, init=False)
    finished = False

    def watch_combo(self, old: int, new: int) -> None:
        self.screen.query_one("#combo", Static).update("COMBO: " + str(self.combo))

    def watch_score(self, old: int, new: int) -> None:
        self.screen.query_one("#score", Static).update("SCORE: " + str(self.score))

    def watch_health(self, old: float, new: float) -> None:
        health = self.screen.query_one("#health", ProgressBar)
        health.update(progress=new)
        health.set_class(new < 30, "low")

    def judge(self, note: dict, judgement: str) -> None:
        note["state"] = judgement
        self.counts[judgement] += 1
        self.flashes[note["lane"]] = (judgement, self.elapsed() + FLASH_TIME)
        self.screen.show_judgement(judgement)
        self.health = min(max(self.health + HEALTH_CHANGE[judgement], 0), 100)
        if judgement == "miss":
            self.max_combo = max(self.combo, self.max_combo)
            self.combo = 0
        else:
            self.combo += 1
            self.score += POINTS[judgement] * min(self.combo // 10 + 1, 4)
        if self.health == 0 and not self.app.settings["no_fail"]:
            self.finish(failed=True)

    def finish(self, failed: bool = False) -> None:
        self.finished = True
        self.ticker.stop()
        self.music.stop()
        self.max_combo = max(self.combo, self.max_combo)
        self.app.switch_screen(ResultsScreen(
            chart_path=self.screen.chart_path,
            title=self.title, artist=self.artist,
            score=self.score, max_combo=self.max_combo,
            counts=self.counts, failed=failed,
        ))

    def tick(self) -> None:
        if self.finished:
            return
        now = self.elapsed()
        for note in self.notes:
            if note["time"] + HIT_WINDOW >= now:
                break
            if note.get("state") is not None:
                continue
            self.judge(note, "miss")
            if self.finished:
                return
        if not self.music.active:
            self.finish()
            return
        total = max(self.music.duration - self.start_at, 0.01)
        self.screen.query_one("#progress", ProgressBar).update(total=total, progress=min(max(self.music.curr_pos - self.start_at, 0), total))
        self.redraw()

    def on_mount(self) -> None:
        self.title = self.screen.title
        self.artist = self.screen.artist
        self.notes = self.screen.notes
        self.bpm = self.screen.bpm
        self.start_at = self.screen.start_at
        self.song_path = self.screen.song_path
        self.counts = {name: 0 for name in ACCURACY_WEIGHTS}
        self.flashes = {}
        self.speed = self.app.settings["speed"] * 4.0
        self.audio_offset = self.app.settings["offset"] / 1000
        self.lane_keys = {key: lane for lane, key in enumerate(self.app.settings["lane_keys"])}
        self.ticker = self.set_interval(1 / 60, self.tick)
        self.music = Playback()
        self.music.load_file(str(assets_dir(self.screen.chart_path) / self.song_path))
        self.clock = AudioClock(self.music)
        self.music.play()
        self.music.seek(self.start_at)

    def elapsed(self) -> float:
        if self.music is None:
            return 0.0
        return self.clock.time() - self.audio_offset

    def frame(self) -> tuple:
        """Draws the game canvas based off of the current tick."""
        now = self.elapsed()
        height = self.size.height
        hit_line = self.size.height - 5

        # build the grid
        grid, lane_width, styles = draw_lanes(self.size.width, height, hit_line, self.app.settings["lane_keys"], self.flashes, now, self.app)

        # populate the grid
        for note in self.notes:
            if note["time"] + (height - hit_line + 1) / self.speed < now or note.get("state") in POINTS:
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

        return grid, styles

    def on_key(self, event) -> None:
        lane = self.lane_keys.get(event.key)
        if lane is None or self.finished:
            return
        now = self.elapsed()
        self.flashes[lane] = ("press", now + FLASH_TIME)
        # the earliest note in this lane that can still be hit
        note = next((n for n in self.notes if n["lane"] == lane and n.get("state") is None and n["time"] >= now - HIT_WINDOW), None)
        if note is None or note["time"] - now > MISS_WINDOW:
            # nothing close enough, so don't punish the tap
            return
        offset = abs(note["time"] - now)
        self.judge(note, next((name for window, name in JUDGEMENTS if offset <= window), "miss"))

class PauseScreen(ModalScreen):
    BINDINGS = [("escape", "resume", "Resume")]
    CSS = """
    PauseScreen {
        align: center middle;
        background: $background 60%;
    }

    #pause_menu {
        width: 30;
        height: auto;
        border: round $primary;
        border-title-align: center;
    }
    """

    def action_resume(self) -> None:
        self.dismiss("resume")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    def compose(self) -> ComposeResult:
        menu = OptionList(Option("Resume", id="resume"), Option("Retry", id="retry"), Option("Quit to menu", id="menu"), id="pause_menu")
        menu.border_title = "Paused"
        yield menu

HUD_CSS = """
    #hud {
        dock: top;
        height: auto;
        padding: 1 1 0 1;
        background: $surface;
    }

    #hud > Horizontal {
        height: auto;
        margin-bottom: 1;
    }

    #hud Static {
        width: 1fr;
        text-align: center;
    }

    #hud ProgressBar Bar { width: 1fr; }
    #hud Bar > .bar--bar, #hud Bar > .bar--complete { background: $panel; }
    #hud .bar-label { width: auto; margin-right: 1; }
    #health { width: 1fr; margin-right: 2; }
    #progress { width: 3fr; }
    #health Bar > .bar--bar, #health Bar > .bar--complete { color: $success; }
    #health.low Bar > .bar--bar { color: $error; }
    #progress Bar > .bar--bar, #progress Bar > .bar--complete { color: $primary; }

    Canvas {
        color: $primary;
    }
    """

class GameScreen(Screen):
    BINDINGS = [("escape", "pause", "Pause")]
    CSS = HUD_CSS

    def __init__(self, chart_path: str, chart: dict) -> None:
            super().__init__()

            self.chart_path = chart_path
            self.app.last_chart = chart_path
            self.title = chart["title"]
            self.artist = chart["artist"]
            self.notes = chart["notes"]
            self.bpm = chart["bpm"]
            self.start_at = chart["start_at"]
            self.song_path = chart["song_path"]

            for note in self.notes:
                if note["time"] < self.start_at:
                    note["state"] = "skipped"
            self.judgement_timer = None

    def on_mount(self) -> None:
        self.query_one("#health", ProgressBar).update(progress=100)

    def show_judgement(self, judgement: str) -> None:
        color = self.app.theme_variables[JUDGEMENT_COLORS[judgement]]
        label = self.query_one("#judgement", Static)
        label.update(Text(judgement.upper(), style="bold " + color))
        if self.judgement_timer is not None:
            self.judgement_timer.stop()
        self.judgement_timer = self.set_timer(0.5, lambda: label.update(""))

    def action_pause(self) -> None:
        canvas = self.query_one(Canvas)
        if canvas.finished:
            return
        canvas.music.pause()
        canvas.ticker.pause()
        self.app.push_screen(PauseScreen(), self.on_pause_closed)

    def on_pause_closed(self, choice: str) -> None:
        canvas = self.query_one(Canvas)
        if choice == "resume":
            canvas.music.resume()
            canvas.ticker.resume()
            return
        canvas.music.stop()
        if choice == "retry":
            self.app.play_chart(self.chart_path)
        else:
            self.app.switch_screen(MenuScreen())

    def compose(self) -> ComposeResult:
        yield Canvas()
        with Vertical(id="hud"):
            with Horizontal():
                yield Static("SCORE: 0", id="score")
                yield Static(id="judgement")
                yield Static("COMBO: 0", id="combo")
            with Horizontal():
                yield Label("HP", classes="bar-label")
                yield ProgressBar(total=100, show_eta=False, show_percentage=False, id="health")
                yield ProgressBar(show_eta=False, show_percentage=False, id="progress")

class RecordCanvas(LaneView):
    """Draws recorded taps rising away from the hit line."""

    def frame(self) -> tuple:
        screen = self.screen
        now = screen.elapsed()
        height = self.size.height
        hit_line = self.size.height - 5
        speed = self.app.settings["speed"] * 4.0
        grid, lane_width, styles = draw_lanes(self.size.width, height, hit_line, self.app.settings["lane_keys"], screen.flashes, now, self.app)
        for tap in reversed(screen.taps):
            note_height = int(round(hit_line - (now - tap["time"]) * speed))
            if note_height < -1:
                break
            i = tap["lane"] * (lane_width + 1)
            for k in (note_height - 1, note_height, note_height + 1):
                if 0 <= k < hit_line:
                    grid[k][i:i+lane_width] = ["█"] * lane_width
        return grid, styles

class SaveRecordingScreen(ModalScreen):
    """Asks what to do with a recording. Dismisses with (choice, snap division)."""

    SNAPS = [1, 2, 3, 4, 6, 8, 12, 16]
    BINDINGS = [
        Binding("left", "snap(-1)", "Finer", group=Binding.Group("Snap")),
        Binding("right", "snap(1)", "Coarser", group=Binding.Group("Snap")),
        ("escape", "resume", "Keep recording"),
    ]
    CSS = """
    SaveRecordingScreen {
        align: center middle;
        background: $background 60%;
    }

    #save_menu {
        width: 44;
        height: auto;
        border: round $primary;
        border-title-align: center;
        padding: 0 1;
    }

    #save_menu > Horizontal { height: auto; margin: 1 0; }
    #save_menu Label { padding: 1 1 0 0; }
    #save_menu .stepper { width: 1fr; height: 3; content-align: center middle; border: tall $border-blurred; }
    #save_menu OptionList { border: none; padding: 0; }
    """

    def __init__(self, taps: int, can_resume: bool) -> None:
        super().__init__()
        self.taps = taps
        self.can_resume = can_resume

    def action_snap(self, delta: int) -> None:
        # left is a finer grid (bigger division), which reads more naturally as "smaller notes"
        self.query_one(Stepper).action_step(-delta)

    def action_resume(self) -> None:
        if self.can_resume:
            self.dismiss(("resume", None))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss((event.option_id, self.query_one(Stepper).value))

    def compose(self) -> ComposeResult:
        with Vertical(id="save_menu") as menu:
            menu.border_title = f"Recorded {self.taps} taps"
            with Horizontal():
                yield Label("Snap to")
                stepper = Stepper(self.SNAPS, 4, format=lambda d: f"1/{d} beat")
                stepper.can_focus = False
                yield stepper
            options = [
                Option("Replace notes", id="replace", disabled=self.taps == 0),
                Option("Add to existing notes", id="add", disabled=self.taps == 0),
                Option("Record again", id="again"),
                Option("Discard", id="discard"),
            ]
            if self.can_resume:
                options.insert(0, Option("Keep recording", id="resume"))
            yield OptionList(*options)
        yield Footer()

class RecordScreen(Screen):
    """Plays the song and records lane presses, then snaps them to the beat and saves them into the chart."""

    BINDINGS = [
        ("escape", "stop", "Stop"),
        ("backspace", "undo", "Undo last tap"),
    ]
    CSS = HUD_CSS + """
    RecordCanvas { color: $primary; }
    """

    def __init__(self, chart_path: str, chart: dict) -> None:
        super().__init__()
        self.chart_path = chart_path
        self.chart = chart
        self.app.last_chart = chart_path
        self.taps = []
        self.flashes = {}
        self.stopped = False

    def on_mount(self) -> None:
        self.audio_offset = self.app.settings["offset"] / 1000
        self.lane_keys = {key: lane for lane, key in enumerate(self.app.settings["lane_keys"])}
        self.music = Playback()
        self.music.load_file(str(assets_dir(self.chart_path) / self.chart["song_path"]))
        self.clock = AudioClock(self.music)
        self.music.play()
        self.music.seek(self.chart["start_at"])
        self.ticker = self.set_interval(1 / 60, self.tick)

    def elapsed(self) -> float:
        return self.clock.time() - self.audio_offset

    def tick(self) -> None:
        if not self.music.active:
            self.action_stop()
            return
        beat = (self.elapsed() - self.chart["offset"]) * self.chart["bpm"] / 60
        self.query_one("#score", Static).update(f"BAR {int(beat // 4) + 1} · BEAT {int(beat % 4) + 1}")
        self.query_one("#combo", Static).update(f"TAPS: {len(self.taps)}")
        total = max(self.music.duration - self.chart["start_at"], 0.01)
        self.query_one("#progress", ProgressBar).update(total=total, progress=min(max(self.music.curr_pos - self.chart["start_at"], 0), total))
        self.query_one(RecordCanvas).redraw()

    def on_key(self, event) -> None:
        lane = self.lane_keys.get(event.key)
        if lane is None or self.stopped:
            return
        now = self.elapsed()
        self.taps.append({"time": now, "lane": lane})
        self.flashes[lane] = ("perfect", now + FLASH_TIME)

    def action_undo(self) -> None:
        if self.taps and not self.stopped:
            self.taps.pop()

    def action_stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.ticker.pause()
        can_resume = self.music.active
        if can_resume:
            self.music.pause()
        self.app.push_screen(SaveRecordingScreen(len(self.taps), can_resume), self.on_save_closed)

    def on_save_closed(self, result: tuple) -> None:
        choice, snap = result
        if choice == "resume":
            self.stopped = False
            self.music.resume()
            self.ticker.resume()
            return
        self.music.stop()
        if choice == "again":
            self.app.record_chart(self.chart_path)
            return
        if choice in ("replace", "add"):
            try:
                count = save_notes(self.chart_path, snap_taps(self.taps, self.chart, snap), keep_existing=choice == "add")
            except (OSError, ValueError) as error:
                self.app.notify(str(error), title="Couldn't save the chart", severity="error")
            else:
                self.app.notify(f"{Path(self.chart_path).name} now has {count} notes.", title="Chart saved")
        self.app.switch_screen(MenuScreen())

    def compose(self) -> ComposeResult:
        yield RecordCanvas()
        with Vertical(id="hud"):
            with Horizontal():
                yield Static(id="score")
                yield Static("[bold]● REC[/bold]", id="judgement")
                yield Static("TAPS: 0", id="combo")
            with Horizontal():
                yield ProgressBar(show_eta=False, show_percentage=False, id="progress")
        yield Footer()

class CalibrationScreen(Screen):
    """Plays a click track and measures how late the player taps along. Dismisses with the new offset or None."""

    BPM = 120
    COUNT_IN = 4
    CLICKS = 20
    LEAD_IN = 1.0
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "save", "Save"),
        ("r", "restart", "Restart"),
    ]
    CSS = """
    CalibrationScreen { align: center middle; }

    #calibration {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $primary;
        border-title-align: center;
        text-align: center;
    }
    """

    @classmethod
    def metronome_path(cls) -> Path:
        """Generates the click track once (the first click of each bar is higher) and caches it."""
        path = user_cache_path(APP_NAME, appauthor=False) / f"metronome-{cls.BPM}.wav"
        if path.is_file():
            return path
        rate = 44100
        interval = 60 / cls.BPM
        click = int(0.03 * rate)
        samples = array("h", bytes(2 * int(rate * (cls.LEAD_IN + (cls.CLICKS + 1) * interval))))
        for i in range(cls.CLICKS):
            start = int((cls.LEAD_IN + i * interval) * rate)
            pitch = 1500 if i % 4 == 0 else 1000
            for j in range(click):
                samples[start + j] = int(12000 * math.sin(2 * math.pi * pitch * j / rate) * (1 - j / click))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(rate)
            file.writeframes(samples.tobytes())
        return path

    def on_mount(self) -> None:
        self.music = Playback()
        self.music.load_file(str(self.metronome_path()))
        self.clock = AudioClock(self.music)
        self.ticker = self.set_interval(1 / 30, self.tick)
        self.action_restart()

    def action_restart(self) -> None:
        self.deltas = []
        self.music.stop()
        self.music.play()

    def click_index(self, position: float) -> float:
        return (position - self.LEAD_IN) * self.BPM / 60

    def measured(self) -> int | None:
        if len(self.deltas) < 4:
            return None
        offset = round(median(self.deltas) * 1000 / OFFSET_STEP) * OFFSET_STEP
        return min(max(offset, OFFSET_MIN), OFFSET_MAX)

    def tick(self) -> None:
        click = self.click_index(self.clock.time())
        if not self.music.active:
            status = "Done! Press [bold]enter[/bold] to save, or [bold]r[/bold] to try again."
        elif click < self.COUNT_IN:
            status = f"Get ready... [bold]{max(int(click) + 1, 1)}[/bold]"
        else:
            status = f"Tap along! Click [bold]{int(click) - self.COUNT_IN + 1}[/bold] of {self.CLICKS - self.COUNT_IN}"
        offset = self.measured()
        result = "Tap at least 4 clicks to measure." if offset is None else f"Measured offset: [bold]{offset} ms[/bold] ({len(self.deltas)} taps)"
        self.query_one("#calibration", Static).update(
            "Listen to the clicks and tap [bold]space[/bold] or any lane key on each one.\n"
            "Close your eyes if it helps, this is measuring your audio.\n\n"
            f"{status}\n\n{result}"
        )

    def on_key(self, event) -> None:
        if event.key != "space" and event.key not in self.app.settings["lane_keys"]:
            return
        click = self.click_index(self.clock.time())
        nearest = round(click)
        # ignore the count-in and anything nowhere near a click
        if nearest < self.COUNT_IN or nearest >= self.CLICKS or abs(click - nearest) > 0.4:
            return
        self.deltas.append((click - nearest) * 60 / self.BPM)

    def action_save(self) -> None:
        offset = self.measured()
        if offset is None:
            self.app.notify("Tap along with at least 4 clicks first.", severity="warning")
            return
        self.music.stop()
        self.dismiss(offset)

    def action_cancel(self) -> None:
        self.music.stop()
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        calibration = Static(id="calibration")
        calibration.border_title = "Audio calibration"
        yield calibration
        yield Footer()

class Stepper(Widget, can_focus=True):
    """A value picked with left/right (or by clicking either half)."""

    BINDINGS = [
        Binding("left", "step(-1)", "Previous", group=Binding.Group("Change")),
        Binding("right", "step(1)", "Next", group=Binding.Group("Change")),
    ]

    class Changed(Message):
        def __init__(self, stepper: "Stepper", value) -> None:
            super().__init__()
            self.stepper = stepper
            self.value = value

    def __init__(self, values: list, value, wrap: bool = False, format=str, id: str | None = None) -> None:
        super().__init__(id=id, classes="stepper")
        self.values = values
        self.wrap = wrap
        self.format = format
        self.set_value(value)

    def set_value(self, value) -> None:
        # snap to the closest option in case the saved value isn't one of them
        if value in self.values:
            self.index = self.values.index(value)
        elif all(isinstance(v, (int, float)) for v in self.values):
            self.index = min(range(len(self.values)), key=lambda i: abs(self.values[i] - value))
        else:
            self.index = 0
        self.refresh()

    @property
    def value(self):
        return self.values[self.index]

    def render(self) -> str:
        return f"◀ {self.format(self.value)} ▶"

    def action_step(self, delta: int) -> None:
        if self.wrap:
            index = (self.index + delta) % len(self.values)
        else:
            index = min(max(self.index + delta, 0), len(self.values) - 1)
        if index != self.index:
            self.index = index
            self.refresh()
            self.post_message(self.Changed(self, self.value))

    def on_click(self, event) -> None:
        self.action_step(-1 if event.x < self.size.width // 2 else 1)

class SettingsPane(VerticalScroll):
    """Up/down move between settings rows instead of scrolling."""

    BINDINGS = [
        Binding("up", "app.focus_previous", "Up", group=Binding.Group("Move")),
        Binding("down", "app.focus_next", "Down", group=Binding.Group("Move")),
    ]

class SongList(OptionList):
    BINDINGS = [
        Binding("enter", "select", "Play"),
        Binding("e", "screen.record", "Record"),
    ]

class KeyBindButton(Button):
    """Button for one lane's key. Press it, then press the new key (escape cancels)."""

    BINDINGS = [Binding("enter", "press", "Rebind")]

    def __init__(self, lane: int, key: str) -> None:
        super().__init__(id=f"lane_{lane}", classes="keybind")
        self.lane = lane
        self.key = key
        self.listening = False
        self.update_label()

    def update_label(self) -> None:
        if self.listening:
            self.label = "press a key..."
        else:
            self.label = Text(key_label(self.key), style="bold")

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
    BINDINGS = [
        Binding("1", "show_tab('songs_tab')", "Songs"),
        Binding("2", "show_tab('settings_tab')", "Settings"),
        Binding("r", "reload", "Reload songs"),
    ]
    CSS = """
    #menu {
        margin-bottom: 1;
    }

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

    .stepper {
        width: 32;
        height: 3;
        content-align: center middle;
        border: tall $border-blurred;
    }

    .stepper:focus { border: tall $border; }

    .keybind { width: 32; }

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

    #details { margin-bottom: 1; }

    #chart_error { width: 80%; color: $error; text-align: center; }
    """

    def cover_color(self, path: Path) -> Color:
        r, g, b = Image.open(path).convert("RGB").resize((1, 1)).getpixel((0, 0))
        color = Color(r, g, b)
        if color.brightness < 0.4:
            color = color.lighten(0.3)
        return color

    def __init__(self):
        super().__init__()
        self.load_songs()

    def load_songs(self) -> None:
        # bundled songs first, then any the user dropped into their songs folder
        self.song_paths = sorted((PACKAGE_DIR / "beatmaps").glob("*.json")) + sorted((USER_DIR / "beatmaps").glob("*.json"))
        self.songlist = []
        for path in self.song_paths:
            song = {"path": str(path), "best": self.app.scores.get(score_key(path)), "cover_path": None, "error": None}
            self.songlist.append(song)
            try:
                chart = load_chart(path)
            except ChartError as error:
                song.update({"error": str(error), "title": path.name, "artist": "Broken chart", "playable": False})
                song["display"] = "[dim][italic]" + path.name + "[/italic] (broken chart)[/dim]"
                continue
            song_assets = assets_dir(path)
            playable = (song_assets / chart["song_path"]).is_file()
            display = "[italic]" + chart["title"] + "[/italic] - [bold]" + chart["artist"] + "[/bold]"
            if not playable:
                display = "[dim]" + display + " (audio missing)[/dim]"
            if chart.get("cover_path") is not None and (song_assets / chart["cover_path"]).is_file():
                song["cover_path"] = song_assets / chart["cover_path"]
                song["color"] = self.cover_color(song["cover_path"])
            notes = [note for note in chart["notes"] if note["time"] >= chart["start_at"]]
            length = notes[-1]["time"] - chart["start_at"] if notes else 0
            song.update({"display": display, "playable": playable, "song_path": chart["song_path"], "title": chart["title"], "artist": chart["artist"], "bpm": chart["bpm"], "notes": len(notes), "length": length})

    def details(self, song: dict) -> str:
        if song["notes"] == 0:
            return f"{song['bpm']:g} BPM · no notes yet (press [bold]e[/bold] to record some)"
        nps = song["notes"] / max(song["length"], 1)
        difficulty = next((name for cutoff, name in DIFFICULTIES if nps < cutoff), "Insane")
        return f"{format_length(song['length'])} · {song['bpm']:g} BPM · {song['notes']} notes · {nps:.1f} nps ([bold]{difficulty}[/bold])"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        song = self.songlist[event.option_index]
        if song["error"] is not None:
            self.app.notify(song["error"], title=f"Can't load {Path(song['path']).name}", severity="error")
            return
        if not song["playable"]:
            self.app.notify(f"Put {song['song_path']} in {USER_DIR / 'assets'} to play this song.", title="Audio missing", severity="error")
            return
        self.app.play_chart(song["path"])

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

        error = self.query_one("#chart_error", Static)
        error.display = song["error"] is not None
        self.query_one("#details", Static).display = self.query_one("#best", Static).display = song["error"] is None
        if song["error"] is not None:
            error.update(Text(song["error"]))
            return

        self.query_one("#details", Static).update(self.details(song))
        best = song["best"]
        if best is None:
            self.query_one("#best", Static).update("[dim]Not played yet[/dim]")
        else:
            self.query_one("#best", Static).update(f"Best: [bold]{grade(best['accuracy'])}[/bold] · {best['score']} · {best['accuracy']:.1%}")

    def on_mount(self) -> None:
        # tabs are switched with 1/2, so the tab bar doesn't need to be a focus stop
        self.query_one(Tabs).can_focus = False
        songlist = self.query_one("#songlist", OptionList)
        # re-select the song that was just played
        paths = [song["path"] for song in self.songlist]
        if self.app.last_chart in paths:
            songlist.highlighted = paths.index(self.app.last_chart)
        songlist.focus()

    def action_reload(self) -> None:
        songlist = self.query_one("#songlist", OptionList)
        current = self.songlist[songlist.highlighted]["path"] if songlist.highlighted is not None else None
        self.load_songs()
        songlist.clear_options()
        songlist.add_options([song["display"] for song in self.songlist])
        paths = [song["path"] for song in self.songlist]
        if self.songlist:
            songlist.highlighted = paths.index(current) if current in paths else 0
        broken = sum(song["error"] is not None for song in self.songlist)
        self.app.notify(f"Found {len(self.songlist)} songs" + (f", {broken} with broken charts." if broken else "."), title="Songs reloaded")

    def action_record(self) -> None:
        songlist = self.query_one("#songlist", OptionList)
        if songlist.highlighted is None:
            return
        song = self.songlist[songlist.highlighted]
        if Path(song["path"]).is_relative_to(PACKAGE_DIR):
            self.app.notify(f"Bundled songs can't be edited. Copy the chart and its audio into {USER_DIR} to record your own.", title="Can't record", severity="warning")
            return
        if song["error"] is None and not song["playable"]:
            self.app.notify(f"Put {song['song_path']} in {USER_DIR / 'assets'} first.", title="Audio missing", severity="error")
            return
        self.app.record_chart(song["path"])

    def action_show_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "songs_tab":
            self.query_one("#songlist").focus()
        else:
            self.query_one("#theme_setting").focus()

    def on_stepper_changed(self, event: Stepper.Changed) -> None:
        if event.stepper.id == "theme_setting":
            self.app.theme = event.value
        elif event.stepper.id in ("speed_setting", "offset_setting", "no_fail_setting"):
            self.app.settings[event.stepper.id.removesuffix("_setting")] = event.value
            save_settings(self.app.settings)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "calibrate":
            self.app.push_screen(CalibrationScreen(), self.on_calibrated)

    def on_calibrated(self, offset: int | None) -> None:
        if offset is None:
            return
        self.app.settings["offset"] = offset
        save_settings(self.app.settings)
        self.query_one("#offset_setting", Stepper).set_value(offset)
        self.app.notify(f"Audio offset set to {offset} ms.", title="Calibrated")

    def rebind_lane(self, button: KeyBindButton, key: str) -> None:
        keys = self.app.settings["lane_keys"]
        if key in keys and keys.index(key) != button.lane:
            self.app.notify(f"{key_label(key)} is already bound to lane {keys.index(key) + 1}.", severity="warning")
            return
        keys[button.lane] = key
        button.key = key
        save_settings(self.app.settings)

    def compose(self) -> ComposeResult:
            with TabbedContent():
                with TabPane("Songs", id="songs_tab"):
                    with Horizontal(id="menu"):
                        yield SongList(*[d.get("display") for d in self.songlist], id="songlist")
                        with Vertical(id="preview"):
                            yield Static(id="cover")
                            yield Static(id="details")
                            yield Static(id="best")
                            yield Static(id="chart_error")
                with TabPane("Settings", id="settings_tab"):
                    with SettingsPane(id="settings", can_focus=False):
                        with Horizontal(classes="setting"):
                            yield Label("Theme", classes="setting-name")
                            yield Stepper(sorted(self.app.available_themes), self.app.theme, wrap=True, id="theme_setting")
                        with Horizontal(classes="setting"):
                            yield Label("Scroll speed", classes="setting-name")
                            speeds = [SPEED_MIN + i * SPEED_STEP for i in range(int((SPEED_MAX - SPEED_MIN) / SPEED_STEP) + 1)]
                            yield Stepper(speeds, self.app.settings["speed"], format=lambda v: f"{v:.1f}", id="speed_setting")
                        with Horizontal(classes="setting"):
                            yield Label("Audio offset", classes="setting-name")
                            yield Stepper(list(range(OFFSET_MIN, OFFSET_MAX + 1, OFFSET_STEP)), self.app.settings["offset"], format=lambda v: f"{v:+d} ms", id="offset_setting")
                        with Horizontal(classes="setting"):
                            yield Label("", classes="setting-name")
                            yield Button("Calibrate offset", id="calibrate", classes="keybind")
                        with Horizontal(classes="setting"):
                            yield Label("No fail", classes="setting-name")
                            yield Stepper([False, True], self.app.settings["no_fail"], format=lambda v: "On" if v else "Off", id="no_fail_setting")
                        for lane, key in enumerate(self.app.settings["lane_keys"]):
                            with Horizontal(classes="setting"):
                                yield Label(f"Lane {lane + 1} key", classes="setting-name")
                                yield KeyBindButton(lane, key)
                        yield Label(f"Custom songs folder: {USER_DIR}\n(charts go in beatmaps/, audio + covers in assets/)", id="songs_folder")
            yield Footer()

class ResultsScreen(Screen):
    BINDINGS = [
        Binding("escape", "menu", "Menu", group=Binding.Group("Menu")),
        Binding("enter", "menu", "Menu", group=Binding.Group("Menu")),
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
    def __init__(self, chart_path: str, title: str, artist: str, score: int, max_combo: int, counts: dict, failed: bool = False) -> None:
        super().__init__()
        self.chart_path = chart_path
        self.title = title
        self.artist = artist
        self.score = score
        self.max_combo = max_combo
        self.counts = counts
        self.failed = failed
        self.accuracy = accuracy(counts)
        self.save_best()

    def save_best(self) -> None:
        """Each best is tracked separately, so a high score run doesn't overwrite a better grade."""
        key = score_key(self.chart_path)
        old = self.app.scores.get(key)
        # failed runs don't count towards bests
        if self.failed:
            self.best = old
            self.new_score = self.new_grade = False
            return
        self.new_score = old is None or self.score > old["score"]
        self.new_grade = old is None or grade(self.accuracy) != grade(old["accuracy"]) and self.accuracy > old["accuracy"]
        if old is None:
            self.best = {"score": self.score, "accuracy": self.accuracy, "max_combo": self.max_combo}
        else:
            self.best = {
                "score": max(self.score, old["score"]),
                "accuracy": max(self.accuracy, old["accuracy"]),
                "max_combo": max(self.max_combo, old["max_combo"]),
            }
        self.app.scores[key] = self.best
        save_scores(self.app.scores)

    def on_mount(self) -> None:
        table = self.query_one("#stats", DataTable)
        table.add_columns("stat", "value")
        best = self.best or {"score": "-", "accuracy": None}
        table.add_rows([
            ("Perfect", str(self.counts["perfect"])),
            ("Great", str(self.counts["great"])),
            ("Good", str(self.counts["good"])),
            ("Miss", str(self.counts["miss"])),
            ("Max Combo", str(self.max_combo)),
            ("Accuracy", f"{self.accuracy:.1%}"),
            ("Best Score", str(best["score"]) + (" [bold green]NEW![/bold green]" if self.new_score else "")),
            ("Best Grade", (grade(best["accuracy"]) if best["accuracy"] is not None else "-") + (" [bold green]NEW![/bold green]" if self.new_grade else "")),
        ])

    def action_retry(self) -> None:
        self.app.play_chart(self.chart_path)

    def action_menu(self) -> None:
        self.app.switch_screen(MenuScreen())

    def compose(self) -> ComposeResult:
        with Horizontal(id="results"):
            with Vertical(id="score_container"):
                yield Static(figlet_format("F" if self.failed else grade(self.accuracy), font="ansi_regular"))
                yield Digits(str(self.score), id="score")
            with Vertical(id="stats_container"):
                song = "[italic]" + self.title + "[/italic] - [bold]" + self.artist + "[/bold]"
                if self.failed:
                    song += "  [bold red]FAILED[/bold red]"
                yield Static(song, id="song")
                table = DataTable(id="stats", show_header=False, zebra_stripes=True, cursor_type="none")
                # display only, so it shouldn't take focus (or swallow enter)
                table.can_focus = False
                yield table
        yield Footer()


class Game(App):
    last_chart = None

    def on_mount(self) -> None:
        ensure_user_dirs()
        self.settings = load_settings()
        self.scores = load_scores()
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

    def open_chart(self, chart_path: str) -> dict | None:
        """Loads a chart for playing or recording, or explains why it can't be."""
        try:
            chart = load_chart(chart_path)
        except ChartError as error:
            self.notify(str(error), title=f"Can't load {Path(chart_path).name}", severity="error")
            return None
        if not (assets_dir(chart_path) / chart["song_path"]).is_file():
            self.notify(f"Put {chart['song_path']} in {assets_dir(chart_path)} to play this song.", title="Audio missing", severity="error")
            return None
        return chart

    def play_chart(self, chart_path: str) -> None:
        chart = self.open_chart(chart_path)
        self.switch_screen(MenuScreen() if chart is None else GameScreen(chart_path, chart))

    def record_chart(self, chart_path: str) -> None:
        chart = self.open_chart(chart_path)
        self.switch_screen(MenuScreen() if chart is None else RecordScreen(chart_path, chart))


def main() -> None:
    game = Game()

    game.run()

if __name__ == "__main__":
    main()
