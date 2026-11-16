import json
from pathlib import Path


class Lookup:
    def __init__(self, path):
        self.entries = {tuple(turns): gold for turns, gold in json.loads(Path(path).read_text())}
        self.turns = []

    def step(self, text):
        self.turns.append(text)
        return self.entries.get(tuple(self.turns))
