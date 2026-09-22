#!/usr/bin/env python3
r"""Checks the prompt width readline computes against the real one.

The coloured prompt was handed to input() with its ANSI escapes unbracketed.
readline counts every byte of a prompt when working out which column the input
starts in, so it measured 21 columns where only 8 are visible. The first
redraw of a recalled line looked right, being a full one; every incremental
redraw after it began 13 columns too far right, leaving the tail of the
previous line on screen:

    server> _D(e.Bound.Bo e.SummonContainer

That leftover run is exactly 21 characters wide, which is what identified it.

Escapes have to sit between \001 and \002 (RL_PROMPT_START_IGNORE and
RL_PROMPT_END_IGNORE), which readline skips when measuring. This checks that
what readline will measure matches what the terminal will actually advance by
-- the invariant that was broken -- and that the plain form emit() writes to
stdout itself carries no markers, since there they are just control
characters.

Needs neither a terminal nor the game.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "..", "bg3lua")

src = io.open(SOURCE, encoding="utf-8").read()

# The definitions are all that is needed; the __name__ guard keeps main() and
# argparse out of it.
ns = {"__name__": "check_prompt"}
exec(compile(src, SOURCE, "exec"), ns)

prompt_forms = ns["prompt_forms"]


def readline_width(prompt):
    """What readline believes the prompt's visible width to be."""
    visible = re.sub("\001[^\002]*\002", "", prompt)
    assert "\001" not in visible and "\002" not in visible, "unbalanced markers"
    return len(visible)


def true_width(prompt):
    """The width the terminal actually advances the cursor by."""
    stripped = prompt.replace("\001", "").replace("\002", "")
    return len(re.sub(r"\x1b\[[0-9;]*m", "", stripped))


failures = 0

# Force the coloured branch; the uncoloured one was never broken.
ns["color_enabled"] = lambda stream: True

for name in ("server", "client"):
    editable, plain = prompt_forms(name)

    measured = readline_width(editable)
    actual = true_width(editable)
    if measured != actual:
        print(f"FAIL {name}: readline measures {measured}, the terminal "
              f"advances {actual}")
        failures += 1
    else:
        print(f"ok   {name}: readline and the terminal agree on {measured} "
              f"columns")

    expected = len(f"{name}> ")
    if actual != expected:
        print(f"FAIL {name}: visible prompt is {actual} columns, expected "
              f"{expected}")
        failures += 1

    # emit() writes this one to stdout directly.
    if "\001" in plain or "\002" in plain:
        print(f"FAIL {name}: the plain form carries readline markers")
        failures += 1
    else:
        print(f"ok   {name}: the plain form has no readline markers")

    if true_width(plain) != actual:
        print(f"FAIL {name}: the two forms differ in visible width")
        failures += 1

# The original bug kept as a regression, so this check cannot quietly stop
# describing something real.
broken = "\x1b[34m\x1b[1mserver> \x1b[0m"
if readline_width(broken) != 21 or true_width(broken) != 8:
    print("FAIL the original bug no longer reproduces as described; this "
          "check has drifted from what it documents")
    failures += 1
else:
    print("ok   an unbracketed prompt still measures 21 against 8 visible")

if failures:
    print(f"{failures} failure(s)")
sys.exit(1 if failures else 0)
