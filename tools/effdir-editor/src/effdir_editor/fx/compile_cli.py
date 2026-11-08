"""`effdir-compile`: `.fx` source to a packed EFFDIR entry in a DBPF package."""

from __future__ import annotations

import argparse
import os
import sys

from ..container.dbpf import Tgi, create_archive_and_save, replace_entry_and_save
from .compiler import compile_to_bytes
from .parser import FxError

_EFFDIR_TYPE = 0xEA5118B0
_EFFDIR_GROUP = 0xEA5118B1


def _parse_instance(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError(f"instance {text} is outside 0..0xFFFFFFFF")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="effdir-compile", description="Compile a SimCity 4 .fx effect file to a packed EFFDIR entry in a DBPF package.")
    parser.add_argument("input", help="the .fx source file")
    parser.add_argument("-o", "--output", required=True, help="package to create, or an existing package to add the entry to (its other entries are kept)")
    parser.add_argument("--instance", required=True, type=_parse_instance, help="instance ID of the entry, for example 0x7ABC0001")
    parser.add_argument("--compress", action="store_true", help="store the entry QFS-compressed")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "rb") as stream:
            source = stream.read().decode("latin-1")
    except OSError as error:
        print(f"effdir-compile: {error}", file=sys.stderr)
        return 2

    try:
        data = compile_to_bytes(source, file=os.path.basename(args.input), include_dir=os.path.dirname(os.path.abspath(args.input)))
    except FxError as error:
        print(str(error), file=sys.stderr)
        return 1

    tgi = Tgi(_EFFDIR_TYPE, _EFFDIR_GROUP, args.instance)
    if os.path.exists(args.output):
        warnings = replace_entry_and_save(args.output, args.output, tgi, data, compress=args.compress)
    else:
        warnings = create_archive_and_save(args.output, tgi, data, compress=args.compress)
    for warning in warnings:
        print(f"effdir-compile: {warning}", file=sys.stderr)
    print(f"{args.output}: wrote {tgi} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
