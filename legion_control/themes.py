"""UI colour themes and colour presets."""

# accent: buttons, highlights, the card header line; on_accent: text drawn on top of the accent
THEMES = {
    "Miku":        {"accent": "#39c5bb", "on_accent": "#000000"},
    "Teto":        {"accent": "#d03a58", "on_accent": "#ffffff"},
    "Neru":        {"accent": "#d9c400", "on_accent": "#000000"},
    "Phrolova":    {"accent": "#c2183a", "on_accent": "#ffffff"},
    "Shorekeeper": {"accent": "#6a8cff", "on_accent": "#ffffff"},
    "Encore":      {"accent": "#ff8fb8", "on_accent": "#000000"},
    "MaoMao":      {"accent": "#3f8f70", "on_accent": "#ffffff"},
}
DEFAULT_THEME = "Miku"

# Keyboard colour presets (name, hex): the vocaloids plus the Resonators/MaoMao used elsewhere
PRESETS = [
    ("Miku", "39c5bb"), ("Teto", "d03a58"), ("Neru", "e4d935"), ("Gumi", "7dbf3b"),
    ("Phrolova", "c2183a"), ("Shorekeeper", "6a8cff"), ("Encore", "ff8fb8"), ("MaoMao", "3f8f70"),
]

# Neutral UI colours shared by every theme
BG = "#121212"
CARD = "#1b1b1b"
CARD_BORDER = "#262626"
FIELD = "#2a2a2a"
FIELD_HOVER = "#353535"
TEXT = "#e6e6e6"
TEXT_SEC = "#9a9a9a"
TEXT_DIM = "#6a6a6a"
WARN = "#ffcc00"
BAD = "#ff4d4d"


def theme(name):
    return THEMES.get(name, THEMES[DEFAULT_THEME])
