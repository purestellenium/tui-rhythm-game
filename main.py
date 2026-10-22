from textual.app import App, ComposeResult
from textual.widget import Widget
from time import perf_counter

# game settings
speed = 30.0

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

    def tick(self) -> None:
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
            if note["time"] + (height - hit_line + 1) / speed < now:
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


class Game(App):

    BINDINGS = []
    CSS = """

    """

    def compose(self) -> ComposeResult:
        yield Canvas()


if __name__ == "__main__":
    game = Game()

    game.run()