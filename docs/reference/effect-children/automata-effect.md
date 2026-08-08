# `automataEffect`

Status: `Confirmed`

Anonymous automata attractor component inside an `effect`.

## Syntax

```fx
automataEffect
    -name <string>
    -group <string>
```

## Valid examples

```fx
effect PoliceHeliAnchor
    automataEffect -name PoliceHelicopterPursuit
end
```

```fx
effect TrafficAnchor
    automataEffect -group Traffic
end
```

```fx
effect FerryAnchor
    automataEffect -group Watercraft
end
```

## Notes

- at least one of `-name` or `-group` is required
- missing both throws:
  `Need at least -name or -group for anonymous attractor effect`
- `-name` and `-group` are not equivalent
- `-name` starts or binds a specific named automata attractor/controller template at the effect transform
- `-group` registers the effect transform as an anchor for an automata-group name
- `-group` is resolved through the automata script system's `GetAutomataGroup(...)` lookup, not `GetOccupantGroup(...)`
- the automata-group namespace is distinct from the plain occupant-group namespace
- internally, an automata-group name still resolves to a `cSC4OccupantGroupTemplate*`, so the feature is built on occupant-group templates under the hood
- once resolved, the controller manager adds or removes the controller templates attached to that resolved group template
- on start, the effect creates a dummy occupant, places it in the world, and uses that occupant as the attractor anchor
- on stop, the effect unregisters the named/group attractor and removes the dummy occupant
- `SetFloatParams` and `SetVoidParams` are stubbed in this binary, so there are no confirmed extra runtime parameters beyond `-name` and `-group`
- if both `-name` and `-group` are present, the parser prefers `-name` and only falls back to `-group` when `-name` is absent
