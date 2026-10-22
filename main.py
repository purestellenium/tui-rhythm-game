from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from time import perf_counter

# game settings
speed = 16.0 * 3
LANE_KEYS = {"d": 0, "f": 1, "j": 2, "k": 3}

# chart settings
notes = [
    {"time": 1.0, "lane": 0}, {"time": 1.5, "lane": 1}, {"time": 2.0, "lane": 2}, {"time": 2.5, "lane": 3},
    {"time": 3.0, "lane": 3}, {"time": 3.5, "lane": 2}, {"time": 4.0, "lane": 1}, {"time": 4.5, "lane": 0},

    {"time": 5.0, "lane": 0}, {"time": 5.0, "lane": 3},
    {"time": 5.5, "lane": 1}, {"time": 5.5, "lane": 2},
    {"time": 6.0, "lane": 0}, {"time": 6.0, "lane": 3},
    {"time": 6.5, "lane": 1}, {"time": 6.5, "lane": 2},

    {"time": 7.0, "lane": 0}, {"time": 7.25, "lane": 1}, {"time": 7.5, "lane": 2}, {"time": 7.75, "lane": 3},
    {"time": 8.0, "lane": 2}, {"time": 8.25, "lane": 1}, {"time": 8.5, "lane": 0},

    {"time": 9.0, "lane": 1}, {"time": 9.25, "lane": 2}, {"time": 9.5, "lane": 1}, {"time": 9.75, "lane": 2},

    {"time": 10.5, "lane": 0}, {"time": 10.5, "lane": 1}, {"time": 10.5, "lane": 2}, {"time": 10.5, "lane": 3},
]

class Canvas(Widget):
    start = 0.0
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

    def elapsed(self) -> float:
        return perf_counter() - self.start

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
        closest = min([d for d in notes if d.get("lane") == lane and d.get("state") != "hit"], key=lambda t: abs(t["time"] - now), default=None)
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