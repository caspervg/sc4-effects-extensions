# `chainEffect`

Status: `Parser/storage only`

`chainEffect` writes the description's legacy string field. In the examined
Mac binary it is normalized and stored in the effects collection, but no
runtime consumer was found that starts, links, or otherwise acts on the
named effect.

## Syntax

```fx
chainEffect <effectName>
```

## Notes

- the basic syntax is recovered
- the value is stored at `cSC4EffectDescription +0x2c`
- `cSC4EffectsCollection::AddEffectDescription` (`0x003e4B2E`) copies and
  lowercases it
- no runtime consumer was found in the observed effects-manager path
