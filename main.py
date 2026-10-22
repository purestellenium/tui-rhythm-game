from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from time import perf_counter
from just_playback import Playback
import json

# game settings
speed = 16.0 * 3
LANE_KEYS = {"d": 0, "f": 1, "j": 2, "k": 3}

# load chart settings
with open('crystallized.json', 'r') as file:
    chart = json.load(file)

notes = chart["notes"]
bpm = chart["bpm"]
offset = chart["offset"]
start_at = chart["start_at"]

# convert beatmap to seconds

for note in notes:
    note["time"] = offset + note["beat"] * 60 / bpm

class Canvas(Widget):
    music = None
    can_focus = True
    misses = 0

    def tick(self) -> None:
        now = self.elapsed()
        for note in notes:
            if note["time"] + 1.5 / speed + 0.12 >= now:
                break
            if note.get("state") is not None:
                continue
            note["state"] = "missed"
            self.misses += 1
        self.refresh()

    def on_mount(self) -> None:
        self.start = perf_counter()
        self.ticker = self.set_interval(1 / 60, self.tick)
        self.music = Playback()
        self.music.load_file("crystallized.mp3")
        self.music.play()
        self.music.seek(start_at)

    def elapsed(self) -> float:
        if self.music is None:
            return 0.0
        return self.music.curr_pos

    def render(self) -> str:
        """Draws the game canvas based off of the current tick."""
        now = self.elapsed()
        lane_width = self.size.width // 4 - 1
        width = lane_width * 4 + 4
        height = self.size.height
        hit_line = self.size.height - 3

        # build the grid
        grid = [["-"] * width if i == hit_line else [" "] * width for i in range(height)]

        # populate the grid
        for note in notes:
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
        return "\n".join("".join(r) for r in grid)

    def on_key(self, event) -> None:
        now = self.elapsed()
        lane = LANE_KEYS.get(event.key)
        if notes == [] or lane is None:
            return
        closest = min([d for d in notes if d.get("lane") == lane and d.get("state") is None], key=lambda t: abs(t["time"] - now), default=None)
        if not closest:
            return
        if abs(closest["time"] - now) <= (1.5 / speed) + 0.12:
            closest["state"] = "hit"
        


class Game(App):
    CSS = """
    #hud { dock: top; height: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Canvas()
        yield Static(id="hud")


if __name__ == "__main__":
    game = Game()

    game.run()