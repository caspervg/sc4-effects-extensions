# FX compiler defaults

EFFDIR stores fully-built descriptors, not the source commands that created
them. Consequently, an omitted command and an explicitly-authored default
command usually produce identical bytes. The decompiler uses the shortest
canonical interpretation and omits a command group when all of its stored
members still match the constructor defaults below.

The particle values come from the symbolized Mac
`cSC4ParticlesDescriptionBase::cSC4ParticlesDescriptionBase` at `0x003F54DA`.
The decal, light, and dynamic-particle values come from constructors at
`0x007600D2`, `0x00760A72`, and `0x004B89B2`. Command-parser defaults are
listed separately because they apply only after that command is present.
The effect values come from `cSC4EffectDescription` at `0x0075CBFE`.

## Particle constructor baseline

| Command group | Stored defaults | Decompiler rule |
| --- | --- | --- |
| `life` | life `2 2`; preroll `0` | Omit the command when both match. |
| `emit` / `rate` / `inject` / `maintain` | rate curve `[30]`; loop interval/count `1/0`; delay `-1 -1`; trigger `-1 -1`; velocity min/max both `0 1 0`; speed `0 0`; mode flags clear | Omit the group when all values and flags match. Emit required default companions when another member differs. |
| `source` | bounds `-1 -1 -1` through `1 1 1`; source flags clear | Default bounds alone do not prove that a source command was authored. |
| `color` | curve `[1 1 1]`; vary `0 0 0` | Omit when both match. `-vary` is one quoted `Vec3` argument with components in `0..1`. |
| `alpha` | curve `[1]`; vary `0` | Omit when both match. |
| `size` | stored curve `[1]`; vary `0` | Omit when both match. Text size values are stored multiplied by `50`. |
| `aspect` | curve `[1]`; vary `0` | Omit when both match. |
| `rotate` | curve `[0]`; vary `0`; offset `0` | Omit when all match. |
| `force` attractor | curve empty; strength `1`; automata id `0`; mode flags clear | Do not infer an attractor from the default strength alone. |
| `force -explosion` | amount `0`; curve `[400]` | Omit when both match. |
| `force -explosionFront` | main `4`; secondary `4` | Omit when both match. |
| `warp -uv` | scale `0`; range `1 0` | Omit when both match. |
| `warp -alpha` | direction `0 1 0`; curve empty | Omit when both match. |
| `collision` storage | bounce `0`; death-by-water `1`; kill height `-1000000000` | Ignore while collision/terrain flags are clear. See parser defaults below when active. |
| `randomWalk` | delay `5 5`; strength `50 50`; turn `0.1 0.2`; preferred direction `0 0 0` | The presence flag still emits `randomWalk`; matching option values are omitted. |
| alignment | damp `0`; bank `0 0` | Omit matching options. |
| model motion | speed/static speed `0`; model list empty | Omit matching options. |

Other particle constructor values are zero or empty unless shown above.
Unknown fields `value_166` and `value_168` default to `1` and `1.0` and are
not reported as unsupported when they retain those values.

## Other descriptor baselines

| Descriptor/command | Constructor defaults omitted by the decompiler |
| --- | --- |
| Decal appearance | life `5`; rotate `[0]`; size `[1]`; alpha `[1]`; color `[1 1 1]`; aspect `[1]`; all variation values `0` |
| Decal texture | repeat `1`; offset `0 0`; flags and resource key clear |
| Light | color/strength curves empty; length `2` |
| Dynamic particle | mass `1`; friction values `0`; model list/key empty |
| Shake | empty amplitude/frequency curves; other values `0`; random table (`0`) |
| Sound child | stored location-update rate `0.5`, corresponding to source `-locationUpdateRate 2`; length `0` |
| Effect child options | LOD `1`; LOD range `6`; shells `1 16`; emit/size scales `1 1`; identity transform |
| Effect | priority `1`; first start-message word `0`; second and third start-message words are not initialized by the constructor |

## Command-parser defaults

These values apply only when the command itself is present:

| Command | Parser default |
| --- | --- |
| `collision` | bounce `0.3`; therefore an active collision with bounce `0.3` omits `-bounce` |
| `color -vary` | exactly one grouped `Vec3`; each component must be in `0..1` |
| `source` | before switches, initializes a flat box `-1 0 -1` through `1 0 1`; this differs from the descriptor constructor's cube |
| `model` | sets draw mode `depthDecal` (`3`) before parsing shared draw options |
| `scrubberEffect` action | low-byte demolition effect ID `1`; `-explode` instead defaults it to `2` and sets upper action bits `0x1300` |
| `cameraParams` | `-parallax 100 101`; `-size 4`; `-sideSwipe 7`; one positional zoom value expands to five values by repeated halving |

For effect-child LOD, the stored range byte is the exclusive upper bound:
`-lod n` writes `n, n+1`, while `-lodRange min max` writes `min, max+1`.
For decal life, omission leaves repeat mode `0`; `-loop`, `-single`, and
`-sustain` write modes `1`, `2`, and `3`, and `-static` additionally sets flag
bit 6.

On MSVC debug builds, the uninitialized second and third effect start-message
words normally contain `0xCCCCCCCC`. The decompiler treats only trailing
instances of that sentinel as absent arguments. It does not generally discard
the value, because an interior `0xCCCCCCCC` can still be explicit data.

Constructor-default suppression is intentionally command-oriented rather
than a whole-record shortcut. If one member changes, the decompiler emits
the complete source command needed to reproduce that group, including any
default-looking curve or scalar that the parser would otherwise clear.
