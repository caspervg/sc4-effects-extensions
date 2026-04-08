# `select`

Status: `Confirmed`

`select` groups nested effect children into a weighted random-choice block.

## Syntax

```fx
select
    visualEffect effect_a -prob 0.5
    visualEffect effect_b -prob 0.25
    visualEffect effect_c
end
```

## Behavior

- valid only inside `effect`
- child entries inside the block may use `-prob <float>`
- explicitly assigned probabilities consume part of the total
- unassigned children divide the remaining total evenly
- any rounding remainder goes to the last child
