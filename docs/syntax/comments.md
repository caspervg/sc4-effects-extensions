# Comments

Status: `Confirmed`

## Supported comment form

The only confirmed comment syntax is the block form:

```fx
#<
    ignored text
#>
```

## Behavior

- comments may span multiple lines
- parsing resumes immediately after the closing `#>`
- code may continue on the same line after the comment closes

Example:

```fx
#< disabled block #> effect demo_fx
    visualEffect existing_fx
end
```

## Not confirmed

These comment forms should not currently be assumed to work:

- `//`
- `/* ... */`
