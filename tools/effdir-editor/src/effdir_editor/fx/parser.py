"""`.fx` source text -> a tree of commands.

The Lark grammar owns the file structure: comments are stripped first
(line-based, exactly like `nSCRes::cFileParser::DoParseFile`), then
Lark tokenizes arguments and matches blocks. Lark is the only third-party
dependency, and the grammar deliberately stays close to how the game reads a
line (`nSCRes::SplitIntoArguments`, Mac `0x0041C218`):

- whitespace separates arguments, and a quoted run (`"..."` or `'...'`)
  keeps its whitespace and may sit anywhere inside an argument,
- an argument that starts with `[`, `(`, or `{` runs to the matching close
  and loses the outer brackets,
- `#` starts a line comment even inside a quoted argument, because the game
  finds it before it splits the line.

Numeric arguments are evaluated separately by `evaluate`.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from lark import Lark, Transformer, UnexpectedInput, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken

_BLOCK_COMMANDS = (
    "effect",
    "particles",
    "dynamicParticle",
    "decal",
    "shake",
    "light",
    "sequence",
    "effectGroup",
    "effectsResource",
    "select",
    "particleSequence",
    "namespace",
)

_GRAMMAR = r"""
start: _NEWLINE? item*
?item: block | define | command
block: BLOCK_WORD arg* _NEWLINE item* _END _NEWLINE
define: _DEFINE arg* _NEWLINE item* _ENDDEF _NEWLINE
command: ARG arg* _NEWLINE
?arg: ARG | BRACKETED

BLOCK_WORD.2: /(?:""" + "|".join(_BLOCK_COMMANDS) + r""")(?=[ \t\r\n]|$)/
_END.2: /end(?=[ \t\r\n]|$)/
_DEFINE.2: /define(?=[ \t\r\n]|$)/
_ENDDEF.2: /enddef(?=[ \t\r\n]|$)/
ARG: /(?:[^\s"'\[({]|"[^"\n]*"|'[^'\n]*')(?:[^\s"']|"[^"\n]*"|'[^'\n]*')*/
BRACKETED: /\((?:[^()\n]|\([^()\n]*\))*\)|\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]|\{(?:[^{}\n]|\{[^{}\n]*\})*\}/
_NEWLINE: /(\r?\n[ \t]*)+/
%ignore /[ \t]+/
"""

_QUOTED_PART = re.compile(r"""\"([^\"\n]*)\"|'([^'\n]*)'""")


class FxError(ValueError):
    """Bad `.fx` input, reported with a source position when one is known."""

    def __init__(self, message: str, *, file: str = "", line: int = 0) -> None:
        self.message = message
        self.file = file
        self.line = line
        super().__init__(message)

    def __str__(self) -> str:
        location = self.file or "<fx>"
        if self.line:
            location += f":{self.line}"
        return f"{location}: {self.message}"


@dataclass
class Command:
    """One command or block, with `body` None for a plain command."""

    name: str
    args: List[str]
    line: int
    body: Optional[List["Command"]] = field(default=None)
    file: str = ""


def _unquote(token: str) -> str:
    return _QUOTED_PART.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), token)


@v_args(inline=True)
class _ToCommands(Transformer):
    def start(self, *items):
        return list(items)

    def command(self, name, *args):
        return Command(_unquote(str(name)), [self._arg(a) for a in args], name.line)

    def block(self, name, *rest):
        return self._nested(name, rest)

    def define(self, *rest):
        # `_DEFINE` is filtered out of `rest`, so the first argument
        # supplies the source line.
        return self._nested(None, rest, name="define")

    @staticmethod
    def _arg(token) -> str:
        text = str(token)
        return text[1:-1] if token.type == "BRACKETED" else _unquote(text)

    def _nested(self, keyword, rest, name: Optional[str] = None) -> Command:
        args, body = [], []
        for item in rest:
            (body if isinstance(item, Command) else args).append(item)
        line = keyword.line if keyword is not None else (args[0].line if args else 0)
        return Command(name or str(keyword), [self._arg(a) for a in args], line, body)


_FILE_PARSER = Lark(_GRAMMAR, parser="lalr", start="start", maybe_placeholders=False)
_TRANSFORMER = _ToCommands()


def strip_comments(text: str) -> str:
    """Apply the game's comment rules while keeping every line number.

    `DoParseFile` erases from `#<` to the end of the line first and only
    then looks for `#>`, so `#<` and `#>` on one line never closes. After
    that, `SplitIntoArguments` stops at the first `#`.
    """

    out: List[str] = []
    in_comment = False
    for line in text.splitlines():
        opened = line.find("#<")
        if opened != -1:
            line = line[:opened]
        if opened != -1 or in_comment:
            closed = line.find("#>")
            if closed == -1:
                in_comment = True
                out.append("")
                continue
            line = line[closed + 2 :]
            in_comment = False
        hash_at = line.find("#")
        out.append(line[:hash_at] if hash_at != -1 else line)
    return "\n".join(out) + "\n"


Origin = Tuple[str, int]
_INCLUDE_DEPTH_LIMIT = 32
_LINE_TOKEN = re.compile(r"""(?:[^\s"'\[({]|"[^"\n]*"|'[^'\n]*')(?:[^\s"']|"[^"\n]*"|'[^'\n]*')*""")


def expand_includes(text: str, file: str, directory: str, depth: int = 0) -> Tuple[str, List[Origin]]:
    """Replace `include` and `sinclude` lines with the named file's lines.

    `cFileParser::DoParseFile` (Mac `0x0041DB38`) handles both keywords per
    line before command dispatch, with a separate comment state per file and
    paths relative to the including file. Both keywords run the same path,
    so a missing file is an error for `sinclude` too in this build. Returns
    the expanded text and the `(file, line)` origin of each of its lines.
    """

    lines: List[str] = []
    origins: List[Origin] = []
    stripped = strip_comments(text).split("\n")[:-1]
    for number, line in enumerate(stripped, 1):
        tokens = _LINE_TOKEN.findall(line)
        if not tokens or tokens[0] not in ("include", "sinclude"):
            lines.append(line)
            origins.append((file, number))
            continue
        if len(tokens) != 2:
            raise FxError(f'"{tokens[0]}" takes a single argument', file=file, line=number)
        if depth >= _INCLUDE_DEPTH_LIMIT:
            raise FxError("include files nest too deeply", file=file, line=number)
        name = _unquote(tokens[1])
        path = name if os.path.isabs(name) else os.path.join(directory, name)
        try:
            with open(path, "rb") as stream:
                included = stream.read().decode("latin-1")
        except OSError as error:
            raise FxError(f"Couldn't open file '{name}'", file=file, line=number) from error
        inner_text, inner_origins = expand_includes(included, name, os.path.dirname(path), depth + 1)
        lines.extend(inner_text.split("\n")[:-1])
        origins.extend(inner_origins)
    return "\n".join(lines) + "\n", origins


def _apply_origins(commands: List[Command], origins: Sequence[Origin]) -> None:
    for command in commands:
        if 0 < command.line <= len(origins):
            command.file, command.line = origins[command.line - 1]
        if command.body:
            _apply_origins(command.body, origins)


def parse_file(text: str, *, file: str = "", origins: Optional[Sequence[Origin]] = None) -> List[Command]:
    """Parse `.fx` text into a command tree, or raise `FxError`.

    `origins` maps each line of an expanded source back to where it came
    from, so positions stay right across `include` files.
    """

    source = strip_comments(text)

    def where(line: int) -> Origin:
        if origins is not None and 0 < line <= len(origins):
            return origins[line - 1]
        return file, line

    try:
        commands = _TRANSFORMER.transform(_FILE_PARSER.parse(source))
    except UnexpectedEOF as error:
        raise FxError("unexpected end of file: a block is missing its `end`", file=file) from error
    except UnexpectedToken as error:
        at_file, at_line = where(error.line or 0)
        raise FxError(_describe_token(error), file=at_file, line=at_line) from error
    except UnexpectedCharacters as error:
        at_file, at_line = where(error.line)
        raise FxError(f"cannot read input at column {error.column}: {error.char!r}", file=at_file, line=at_line) from error
    except UnexpectedInput as error:  # pragma: no cover - Lark's remaining kinds
        raise FxError(str(error), file=file, line=getattr(error, "line", 0)) from error
    if origins is not None:
        _apply_origins(commands, origins)
    return commands


def _describe_token(error: UnexpectedToken) -> str:
    if error.token.type == "$END":
        return "unexpected end of file: a block is missing its `end`"
    if error.token.type == "_END":
        return "found `end` without an open block"
    if error.token.type == "_ENDDEF":
        return "found `enddef` without an open definition"
    return f"unexpected input {str(error.token)!r}"


# --- numeric expressions ----------------------------------------------------

_EXPR_GRAMMAR = r"""
?start: sum
?sum: product (ADD_OP product)*        -> binary
?product: power (MUL_OP power)*        -> binary
?power: unary ("^" power)?
?unary: ("+"|"-") unary -> signed
      | atom
?atom: NUMBER                          -> number
     | NAME "(" sum ")"                -> call
     | NAME                            -> constant
     | "(" sum ")"
ADD_OP: "+" | "-"
MUL_OP: "*" | "/" | "%"
NUMBER: /0[xX][0-9a-fA-F]+|(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?/
NAME: /[A-Za-z_][A-Za-z0-9_]*/
%ignore /[ \t]+/
"""

_FUNCTIONS = {
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "abs": abs,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sind": lambda x: math.sin(math.radians(x)),
    "cosd": lambda x: math.cos(math.radians(x)),
    "tand": lambda x: math.tan(math.radians(x)),
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


@v_args(inline=True)
class _Evaluate(Transformer):
    def number(self, token):
        text = str(token)
        return float(int(text, 16)) if text[:2].lower() == "0x" else float(text)

    def binary(self, value, *rest):
        for op, operand in zip(rest[::2], rest[1::2]):
            if op == "+":
                value += operand
            elif op == "-":
                value -= operand
            elif op == "*":
                value *= operand
            elif op == "/":
                value /= operand
            else:
                value -= operand * math.floor(value / operand)
        return value

    def power(self, base, exponent=None):
        return base if exponent is None else base**exponent

    def signed(self, value):
        return -value

    def constant(self, name):
        if str(name) not in _CONSTANTS:
            raise FxError(f"unknown constant {str(name)!r}")
        return _CONSTANTS[str(name)]

    def call(self, name, value):
        if str(name) not in _FUNCTIONS:
            raise FxError(f"unknown function {str(name)!r}")
        return float(_FUNCTIONS[str(name)](value))


_EXPR_PARSER = Lark(_EXPR_GRAMMAR, parser="lalr", transformer=_Evaluate())
_PLAIN_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")


def evaluate(text: str) -> float:
    """Evaluate one numeric argument with the game's expression rules
    (`ParseExpression`, `EvalExpression`, `EvalTerm`, `EvalFactor`), with
    a fast path for the ordinary plain numbers."""

    if _PLAIN_NUMBER.match(text):
        return float(text)
    try:
        return _EXPR_PARSER.parse(text)
    except FxError:
        raise
    except Exception as error:
        raise FxError(f"bad numeric expression {text!r}") from error
