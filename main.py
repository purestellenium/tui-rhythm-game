from textual.app import App, ComposeResult
from textual.widget import Widget
from time import perf_counter

notes = [{"time": 1.0, "lane": 0}, {"time": 1.5, "lane": 1}, {"time": 2.0, "lane": 2}, {"time": 2.5, "lane": 3}, {"time": 3.0, "lane": 0}, {"time": 3.5, "lane": 1}, {"time": 4.0, "lane": 2}, {"time": 4.5, "lane": 3}, {"time": 5.0, "lane": 0}, {"time": 5.5, "lane": 1}, {"time": 6.0, "lane": 2}, {"time": 6.5, "lane": 3}]


class Canvas(Widget):
    game_start = 0;

    def tick(self) -> None:
        self.refresh()

    def on_mount(self) -> None:
        self.start = perf_counter()
        self.ticker = self.set_interval(1 / 60, self.tick)

    def elapsed(self) -> float:
        return perf_counter() - self.start

    def render(self) -> str:
        return str(self.elapsed())

class Game(App):
    BINDINGS = []
    CSS = """

    """

    def compose(self) -> ComposeResult:
        yield Canvas()


if __name__ == "__main__":
    game = Game()

    game.run()