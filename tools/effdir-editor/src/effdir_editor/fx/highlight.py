"""Tokenizer and keyword vocabulary for highlighting emitted fx text.

Deliberately free of any UI dependency so it can be unit-tested and so
the vocabulary lives next to the emitter that produces it: highlighting
a keyword this toolchain cannot emit would imply support that does not
exist. `ui/fx_preview.py` is one consumer; a future exporter (HTML,
terminal) can reuse the same token stream.
"""

from __future__ import annotations

import re
from typing import Iterator, NamedTuple

# Block-opening keywords: top-level definitions (docs/reference/top-level/)
# plus the nested blocks the emitter produces, and the `end` that closes
# them.
BLOCK_KEYWORDS = frozenset(
    {
        "particles",
        "decal",
        "shake",
        "light",
        "dynamicParticle",
        "sequenceEffect",
        "effect",
        "select",
        "systemSequence",
        "force",
        "warp",
        "randomWalk",
        "collision",
        "model",
        "end",
    }
)

# Child commands and pool subcommands the emitter can produce
# (docs/reference/effect-children/, docs/reference/particles/).
COMMAND_KEYWORDS = frozenset(
    {
        "particleEffect",
        "decalEffect",
        "dynamicParticleEffect",
        "sequence",
        "visualEffect",
        "brushEffect",
        "automataEffect",
        "scrubberEffect",
        "soundEffect",
        "cameraEffect",
        "shakeEffect",
        "flashEffect",
        "tintEffect",
        "chainEffect",
        "timedEffect",
        "effectBase",
        "life",
        "emit",
        "maintain",
        "color",
        "alpha",
        "size",
        "aspect",
        "rotate",
        "stretch",
        "texture",
        "terrainRepel",
        "amplitude",
        "frequency",
        "shakeAspect",
        "table",
        "strength",
        "length",
        "mass",
        "friction",
        "play",
        "wait",
        "effectID",
        "effectGroup",
        "instance",
        "messageTrigger",
        "brushID",
        "soundID",
        "cameraParams",
    }
)

# Token kinds, ordered by how the preview styles them.
COMMENT = "comment"
STRING = "string"
SWITCH = "switch"
NUMBER = "number"
BLOCK = "block"
COMMAND = "command"


class Token(NamedTuple):
    kind: str
    start: int  # character offset into the scanned text
    text: str


_TOKEN_RE = re.compile(
    r"""
      (?P<comment>\#<.*?\#>)
    | (?P<string>"[^"]*")
    | (?P<switch>(?<![\w"])-[A-Za-z_]\w*)
    | (?P<number>(?<![\w.])-?(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?))
    | (?P<word>[A-Za-z_]\w*)
    """,
    re.VERBOSE | re.DOTALL,
)


def tokenize(text: str) -> Iterator[Token]:
    """Yield styling tokens. Plain identifiers (effect and pool names)
    yield nothing: they take the default style, so only tokens that carry
    syntactic meaning are emitted."""

    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        token = match.group()
        if kind == "word":
            if token in BLOCK_KEYWORDS:
                kind = BLOCK
            elif token in COMMAND_KEYWORDS:
                kind = COMMAND
            else:
                continue
        yield Token(kind=kind, start=match.start(), text=token)
