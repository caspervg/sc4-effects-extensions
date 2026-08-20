# Comments

Status: `Confirmed`

## Supported comment form

The only confirmed comment syntax is the block form:

```fx
#<
    ignored text
#>
```

`#<` and `#>` must be on different lines. This is not a style preference:
a comment that opens and closes on one line silently destroys the rest of
the file.

## Behavior

`nSCRes::cFileParser::DoParseFile` (Mac `0x0041db38`) scans line by line:

1. if the line contains `#<`, erase from there to the end of the line;
2. then search the line for `#>`;
3. if `#>` is not found, set comment mode and skip the line entirely;
4. if it is found, erase everything up to and including it, clear comment
   mode, and parse whatever remains of the line.

Step 1 runs before step 2, so a `#>` that follows `#<` on the same line has
already been erased and can never be found. The parser latches into comment
mode and every later line is either skipped (comment mode, no `#>`) or
erased to end of line (contains `#<`). Nothing after that point is ever
parsed, and no error is reported -- the file just loads as if it were empty.

The same applies to a trailing comment after code: `effect demo_fx #< note #>`
loses the code as well as the comment, because step 3 skips the whole line.

Consequences:

- comments may span multiple lines
- `#<` must be the only thing on its line
- a closing `#>` only works on a line with no earlier `#<`
- code may continue on the same line after that closing `#>`

Example:

```fx
#<
    disabled block
#>
effect demo_fx
    visualEffect existing_fx
end
```

## Not confirmed

These comment forms should not currently be assumed to work:

- `//`
- `/* ... */`
