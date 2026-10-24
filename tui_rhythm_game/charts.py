from pathlib import Path
import json

LANES = 4

class ChartError(Exception):
    """A beatmap that can't be played. The message says what to fix."""

def assets_dir(chart_path) -> Path:
    """Charts live in <root>/beatmaps/, so their audio + covers live in <root>/assets/."""
    return Path(chart_path).parent.parent / "assets"

def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def load_chart(chart_path) -> dict:
    """Reads and checks a beatmap, filling in defaults and each note's time in seconds."""
    try:
        with open(chart_path, 'r') as file:
            chart = json.load(file)
    except OSError as error:
        raise ChartError(f"Couldn't read the file ({error.strerror}).")
    except ValueError as error:
        raise ChartError(f"Invalid JSON: {error}")
    if not isinstance(chart, dict):
        raise ChartError("The chart should be a JSON object.")

    if not is_number(chart.get("bpm")) or chart["bpm"] <= 0:
        raise ChartError('"bpm" should be a positive number.')
    for field in ("offset", "start_at"):
        if not is_number(chart.setdefault(field, 0.0)):
            raise ChartError(f'"{field}" should be a number of seconds.')
    if not isinstance(chart.get("song_path"), str):
        raise ChartError('"song_path" should be the audio file\'s name in assets/.')
    for field in ("title", "artist", "cover_path"):
        if chart.get(field) is not None and not isinstance(chart[field], str):
            raise ChartError(f'"{field}" should be a string.')
    chart.setdefault("title", "Untitled")
    chart.setdefault("artist", "Unknown Artist")

    notes = chart.setdefault("notes", [])
    if not isinstance(notes, list):
        raise ChartError('"notes" should be a list.')
    for i, note in enumerate(notes):
        if not isinstance(note, dict) or not is_number(note.get("beat")):
            raise ChartError(f'Note {i + 1} needs a numeric "beat".')
        if type(note.get("lane")) is not int or not 0 <= note["lane"] < LANES:
            raise ChartError(f'Note {i + 1} needs a "lane" from 0 to {LANES - 1}.')

    # the game walks notes in order, so hand-written charts don't have to be sorted
    chart["notes"] = sorted(notes, key=lambda note: note["beat"])
    for note in chart["notes"]:
        note["time"] = chart["offset"] + note["beat"] * 60 / chart["bpm"]
    return chart

def snap_taps(taps: list, chart: dict, division: int) -> list:
    """Turns recorded taps (in seconds) into notes on the nearest 1/division beat."""
    notes = set()
    for tap in taps:
        beat = (tap["time"] - chart["offset"]) * chart["bpm"] / 60
        notes.add((round(round(beat * division) / division, 4), tap["lane"]))
    return [{"beat": beat, "lane": lane} for beat, lane in sorted(notes)]

def save_notes(chart_path, notes: list, keep_existing: bool) -> int:
    """Writes notes into the chart file, leaving its other fields alone. Returns the new note count."""
    with open(chart_path, 'r') as file:
        chart = json.load(file)
    if keep_existing:
        existing = {(note["beat"], note["lane"]) for note in chart.get("notes", [])}
        notes = [{"beat": beat, "lane": lane} for beat, lane in sorted(existing | {(note["beat"], note["lane"]) for note in notes})]
    chart["notes"] = notes
    with open(chart_path, 'w') as file:
        json.dump(chart, file, indent=1)
    return len(notes)
