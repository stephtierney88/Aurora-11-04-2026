"""Side-effect-free command framing shared by admission and execution.

Commands are separated by semicolons or newlines outside arguments. Quotes,
escapes and nested (), [] and {} are preserved. A # starts a line comment only
outside arguments. Validation covers the whole batch before a handler may run.
"""
from __future__ import annotations

import re


class CommandSyntaxError(ValueError):
    """The request cannot be interpreted as a complete command batch."""


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_:]*%?")


def split_command_batch(text: str) -> tuple[str, ...]:
    if not isinstance(text, str):
        raise CommandSyntaxError("Command input must be a string.")
    commands: list[str] = []
    current: list[str] = []
    stack: list[str] = []
    quote = ""
    escaped = False
    comment = False
    closed_call = False

    def finish() -> None:
        nonlocal closed_call
        command = "".join(current).strip()
        if command:
            name = command.split("(", 1)[0].strip()
            if not _NAME.fullmatch(name):
                raise CommandSyntaxError("Expected a command name followed by optional (arguments).")
            commands.append(command)
        current.clear()
        closed_call = False

    for position, char in enumerate(text):
        if comment:
            if char in "\r\n":
                comment = False
                finish()
            continue
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if not stack and char == "#":
            comment = True
            continue
        if not stack and char in ";\r\n":
            finish()
            continue
        if closed_call and not char.isspace():
            raise CommandSyntaxError(f"Unexpected text after command arguments at character {position + 1}.")
        if char in "\"'":
            if not stack:
                raise CommandSyntaxError("Quotes must appear inside command arguments.")
            quote = char
        elif char in "([{":
            if not stack and (char != "(" or not _NAME.fullmatch("".join(current).strip())):
                raise CommandSyntaxError("Expected a command name before (arguments).")
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[char]:
                raise CommandSyntaxError(f"Unmatched {char!r} at character {position + 1}.")
            closed_call = not stack
        current.append(char)
    if quote or stack:
        raise CommandSyntaxError("Incomplete command: close all quotes and argument brackets before sending.")
    finish()
    return tuple(commands)
