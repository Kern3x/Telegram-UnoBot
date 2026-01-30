from .kb_classes import CommandsKeyboard, GameKeyboard


class Keyboards:
    def __init__(self) -> None:
        self.commands = CommandsKeyboard()
        self.game = GameKeyboard()