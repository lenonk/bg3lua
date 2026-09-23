#!/usr/bin/env python3
r"""Checks what the console does with the game's own output.

Mods write their log lines with escape sequences in them -- Mod Configuration
Menu uses 24-bit SGR colours -- and those lines arrive while the user may be
mid-edit at the prompt. Two things went wrong on screen because of it:

    server>     542/'

A stray run of text like that is the tail of a sequence the terminal never
finished reading, or the wrapped remainder of a line the old single-line
clear could not reach. So: colour is kept, everything else that moves the
cursor or erases is dropped, an unterminated sequence takes its tail with it,
and the clear covers however many rows the prompt and the edited line
occupy.

Needs neither a terminal nor the game.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "..", "bg3lua")


def load():
    spec = importlib.util.spec_from_loader(
        "bg3lua_mod", importlib.machinery.SourceFileLoader("bg3lua_mod", SOURCE))
    module = importlib.util.module_from_spec(spec)
    # The script only runs its REPL under __main__, so importing is safe.
    spec.loader.exec_module(module)
    return module


def main():
    bg = load()
    failures = []

    def check(name, got, want):
        if got == want:
            print(f"ok   {name}")
        else:
            print(f"FAIL {name}\n     got  {got!r}\n     want {want!r}")
            failures.append(name)

    colour = "\x1b[38;2;0;255;255m"
    reset = "\x1b[0m"

    check("a mod's colour survives, and is closed off",
          bg.sanitise_output(f"{colour}[MCM]: loaded"),
          f"{colour}[MCM]: loaded{reset}")

    check("a colour the mod closed itself is left alone",
          bg.sanitise_output(f"{colour}[MCM]: loaded{reset}"),
          f"{colour}[MCM]: loaded{reset}")

    check("a cursor move is dropped",
          bg.sanitise_output("before\x1b[2Aafter"), "beforeafter")

    check("an erase is dropped",
          bg.sanitise_output("before\x1b[2Kafter"), "beforeafter")

    check("a bare carriage return is dropped",
          bg.sanitise_output("progress 1\rprogress 2"),
          "progress 1progress 2")

    check("a sequence cut off at the end takes its tail with it",
          bg.sanitise_output("done\x1b[38;2;0;255"), "done")

    check("a window-title sequence is dropped",
          bg.sanitise_output("a\x1b]0;title\x07b"), "ab")

    check("a backspace is dropped",
          bg.sanitise_output("ab\x08c"), "abc")

    check("newlines and tabs are kept",
          bg.sanitise_output("a\tb\nc"), "a\tb\nc")

    # Widths: what the terminal advances by, ignoring anything invisible.
    check("colour does not count towards the width",
          bg.visible_width(f"{colour}server> {reset}"), len("server> "))

    check("readline's own markers do not count towards the width",
          bg.visible_width(f"{bg.RL_IGNORE_START}{colour}{bg.RL_IGNORE_END}x"),
          1)

    # Clearing: one row per wrap, plus the row the cursor is on. The terminal
    # size is whatever the checking environment has, so drive it directly.
    columns = 80
    try:
        columns = os.get_terminal_size(sys.stdout.fileno()).columns
    except Exception:
        pass

    short = bg.clear_prompt_rows("server> abc")
    check("a line that fits clears one row", short, "\r\x1b[2K")

    wrapped = bg.clear_prompt_rows("x" * (columns * 2 + 1))
    check("a line wrapped twice clears three rows",
          wrapped, "\r\x1b[2K" + "\x1b[A\x1b[2K" * 2)

    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
