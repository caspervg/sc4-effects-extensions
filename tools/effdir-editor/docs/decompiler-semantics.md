# FX decompiler semantics and source ambiguities

EFFDIR records retain the final parser state, not the commands or their order.
This page records the command behavior recovered from the symbolized 32-bit Mac
binary and the canonical spellings chosen by the decompiler. Addresses refer
to that binary.

## Effect `startMessage`

`cGroupEffectCommand::Parse` (`0x0078510A`) accepts one to three values and
writes only the supplied words. `cSC4EffectDescription` (`0x0075CBFE`)
initializes the first word to zero but does not initialize the second or third.
The frequent binary value `0 0xCCCCCCCC 0xCCCCCCCC` is therefore the MSVC debug
heap-fill pattern, not three intentional message IDs and not a null pointer.

The decompiler removes trailing `0xCCCCCCCC` words and suppresses the remaining
default `0`. Other values, including interior sentinels, are preserved.

The three words do not have identical semantics. The runtime path is:

1. `cSC4VisualEffect::SetDescription` (`0x00418CB2`) copies descriptor words
   `+0x20/+0x24/+0x28` into the live visual effect at `+0x118/+0x11c/+0x120`.
2. `cSC4VisualEffect::Start` (`0x004191F0`) checks that word 1 is nonzero,
   allocates a `cRZMessage2Standard`, and passes word 1 to `SetType`.
3. Words 2 and 3 are passed to `SetData1` and `SetData2`; the visual effect is
   installed as the sender, and the message is posted through `spMS2`.

Thus word 1 is specifically an SC4 message type ID, while words 2 and 3 are
opaque integer payloads. The decompiler follows SC4 convention by formatting
only the type as hexadecimal and leaving payloads decimal. For example:

```text
effect tugg_test_water -startMessage 0xac400a31 0 0
effect tugropeconnection -startMessage 0xcc0d905f 0 0
```

The parser uses `nSCRes::ParseUint`, so these hexadecimal spellings compile
back to the same 32-bit values.

These messages are emitted when the visual effect starts; they do not cause the
visual effect to start. `cSC4VisualEffect::Start` starts the child components
first and then posts the configured message. Two concrete consumers confirm the
direction and show why the visual effect is installed as the sender:

| Message type | Emitting effect | Subscriber and behavior |
| --- | --- | --- |
| `0xac400a31` | `tugg_test_water` | `cSC4Watercraft::Init` (`0x00382D44`) subscribes and `cSC4Watercraft::DoMessage` (`0x00386FA5`) obtains the sending visual effect, reads its transform, and asks the watercraft manager for a boat at that position. Qualifying boats are linked for the tug/rope interaction. `Shutdown` (`0x00385746`) unsubscribes. |
| `0xcc0d905f` | `tugropeconnection` | `cSC4CitySituationManager::Init` (`0x004A2C10`) subscribes and `DoMessage` (`0x004A87A9`) retains the sending visual effect when an active situation enables mode `8`. `GetActivePosition` (`0x0049EC0F`) then uses that effect's transform as the situation position. `DoAnimationTick` (`0x004A8581`) releases it when the effect is no longer active, and `EndSituation` (`0x004A67B8`) also clears it. |

Neither handler reads `Data1` or `Data2` for these message types. Their `0 0`
payloads are therefore ordinary unused payload values; the sender and its
transform carry the useful information.

## Emission modes

The parsers at `0x0078667C`, `0x00785E28`, `0x00785F28`, and `0x0078867E`
share the curve at descriptor `+0x088`:

- ordinary `rate`/`emit -rate` does not set a mode bit;
- `inject`, `rate -inject`, and `emit -inject` set leading-bitset bit 1 and
  store a single value;
- `maintain` sets leading-bitset bit 2 and stores a single value.

Thus bit 1 is specifically inject mode, not a generic emit/inject bit. The
original synonymous spelling is lost; the decompiler uses `emit -inject`.

## Force, gravity, wind, and reset

`cParticleForceCommand::Parse` (`0x0078710C`) accumulates both commands into
the same descriptor `Vec3`:

- `-gravity g` adds `0 -g 0`;
- `-wind direction [magnitude]` normalizes the direction and adds either the
  unit vector or that vector multiplied by the optional magnitude;
- `-reset` zeroes this vector and clears the tractor-point vector, but leaves
  no reset marker in the descriptor.

Command order and gravity-versus-wind provenance cannot be recovered. Any
nonzero stored vector is reproduced exactly as one normalized `-wind` with an
explicit magnitude.

The same parser accepts positional `-terrainRepel` values. The dedicated
`cParticleTerrainRepelCommand::Parse` (`0x0077FFD4`) writes the same fields and
bit while offering named `-scout`, `-vertical`, and `-killHeight` switches.
The decompiler uses the dedicated form.

## Tractor points

The force parser stores absolute positions, explicit tangent vectors, segment
start times, and segment end times. `-tractorRel` adds the preceding absolute
position only after deriving any scalar-form tangent. Consequently neither
relative-versus-absolute spelling nor scalar-derived-versus-explicit tangent
provenance survives.

The decompiler uses absolute `-tractor` with an explicit tangent. Its optional
time is reconstructed as `end - start`, not the stored start time. A sequence
whose stored start times do not match parser chaining is reported unsupported.

## Warp wiggles

`cParticleWarpCommand::Parse` (`0x007880EC`) stores both `-wiggle` and
`-wiggleDir` as the same record: amount, direction `Vec3`, and auxiliary
`Vec3`. For the four-argument `-wiggle` form, the radius/phase pair becomes
approximately:

```text
aux.x = radius * cos(phase * 2*pi)
aux.y = 0
aux.z = -radius * sin(phase * 2*pi)
```

Radius and a canonical phase can be derived for compatible records, but the
original spelling cannot, and phases 0 and 1 are identical after conversion.
The decompiler therefore uses exact `-wiggleDir` records and omits its optional
zero auxiliary vector.

## Source shapes and `dice`

`cParticleSourceCommand::Parse` (`0x0077F0D6`) collapses point, square, quad,
cube, and box shapes into one axis-aligned bounding box. Their original keyword
is unrecoverable, but every stored box is exactly representable:

```text
halfExtent = (maximum - minimum) / 2
center     = (maximum + minimum) / 2
source -box "halfExtent" "center"
```

The center argument is omitted when zero. `source -dice` is different: it
zeroes the bounds and writes its scalar to descriptor `+0x1d0`. The adjacent
`+0x1d4` is the storage shared by model `-modelSpeed` and
`-modelSpeedStatic`; third-bitset bit 6 distinguishes those two forms.

## Draw and alignment enum domains

There are two draw tables, and they are not interchangeable.

Decals use `kDecalDrawTypes` (`0x00ABAF60`):

| Value | Name |
| ---: | --- |
| 0 | `decal` |
| 1 | `additive` |
| 2 | `modulate` |
| 3 | `decalInvertDepth` |
| 4 | `decalNoOverlap` |

Particles use the shared draw parser (`0x004018F0`) over `kParticleDrawTypes`
(`0x00ABAFE0`):

| Value | Name |
| ---: | --- |
| 0 | `decal` |
| 1 | `decalInvertDepth` |
| 2 | `decalIgnoreDepth` |
| 3 | `depthDecal` |
| 4 | `depthDecalMasked` |
| 5 | `additive` |
| 6 | `additiveIgnoreDepth` |
| 7 | `modulate` |

Either enum is always a `-draw` switch on the `texture`/`model` command that
carries it, for decals as much as for particles: `cDecalTextureCommand::Parse`
(`0x00785890`) reads both, and the game rejects a bare `draw <mode>` line with
`unknown command draw`. Feeding a particle name to a decal (or the reverse)
throws `Unknown enum '%s'`.

The alignment parser (`0x0078AA74`, table `0x00ABAFA0`) defines:

| Value | Name |
| ---: | --- |
| 0 | `camera` |
| 1 | `ground` |
| 2 | `dirX` |
| 3 | `dirY` |
| 4 | `dirZ` |

Alignment `-damp` is an independent scalar. `-bank` and `-windBank` share the
same two floats; only `-windBank` sets third-bitset bit 7, so that distinction
is recoverable.

## Effect-child LOD and probability

`cSC4EffectsParser::ParseDescRecOptions` (`0x00401D2C`) stores two LOD bytes.
They are not two copies of one value:

- `-lod n` stores `lod = n` and `lod_range = n + 1`;
- `-lodRange min max` stores `lod = min` and `lod_range = max + 1`;
- omission leaves the constructor values `1` and `6`.

The decompiler therefore prefers the shorter `-lod` form when the bytes are
adjacent, and otherwise reconstructs `-lodRange lod (lod_range - 1)`.

Inside a `select` block, `-prob p` is rounded to a 16-bit fraction. Vanilla
correlations (`0.2 -> 13107`, `0.5 -> 32768`, `1 -> 65535`) establish the
inverse `p = stored / 65535`. A stored zero means the select block's implicit
even split and is omitted.

## Effect-child blocks and component types

`cGroupSystemSequenceCommand::Parse` (`0x0078B43A`) sets parser state for the
duration of a `systemSequence ... end` block. Child creation at `0x0078D6C4`
copies that state to DescriptionRecord flag bit 1. Consecutive records with
that bit are therefore emitted inside a reconstructed `systemSequence` block.

Component type 2 is not an opaque indexed pool. In SimCity_1.dat all 591 such
records carry names that resolve as effects, their index field is consistently
zero, and the runtime treats the component as a nested visual effect. It is
emitted as the name-based `visualEffect NAME` command and is followed by
transitive effect-closure export.

Component type 6 is an indexed sequence child. The parser keywords are
distinct: `cSequenceEffectCommand::Parse` (`0x00784724`) opens the named
top-level `sequenceEffect NAME ... end` definition, while
`cGroupSequenceCommand::Parse` (`0x0078B980`) emits the effect-child command
`sequence NAME`.

## Brush and sound identifiers

Brush and sound source names are not stored in their component records. The
records retain only the resolved 32-bit resource key. This is still fully
representable because the language itself defines the lookup maps:

```text
brushID brush_0 0x01234567
soundID sound_0 0x89abcdef
```

`cBrushIDCommand::Parse` (`0x0077ED72`) and `cSoundIDCommand::Parse`
(`0x0077EC72`) lowercase the alias and insert the numeric value into the maps
later queried by `cGroupBrushCommand::Parse` (`0x0078C690`) and
`cGroupSoundCommand::Parse` (`0x0078CC8A`). The author's original alias is
lost, so the decompiler derives a descriptive alias from the first named effect
that uses the key, for example `ufolaser_sound` or
`erodefx_terrain_brush`. Multiple distinct keys first used by the same effect
receive `_2`, `_3`, etc.; equal keys still share one declaration. Orphaned keys
fall back to `brush_N`/`sound_N`. These names describe observed usage, not a
recovered audio/brush asset name. This is canonicalization, not lost behavior.

The lookup yields only a resource key, not a previously built component.
Consequently every `brushEffect` invocation repeats its stored brush options.

Particle, decal, and dynamic-particle render assets work the same way, and
need the same treatment: `texture` and `model` resolve a symbolic name through
the `textureID`/`modelID` maps and throw `No such texture: '%s'` /
`No such model: '%s'` for anything else, so a raw `texture 0x0aa55ea7` will not
load. Nothing here is derived from usage, since the key is all the record
holds: each distinct key gets one deterministic alias (`tex_0aa55ea7`,
`mdl_0aa55ea7`) declared once, ahead of the pools that reference it.

Automata names differ: `AttractorDescription` stores its own string and the
`-name` versus `-group` selector. `DescriptionRecord.name` is normally empty
for this component type, so the decompiler uses the string from the attractor
record directly.

## Global camera parameters

The optional block after the effect-name map is a serialized
`cSC4CameraParams`, not opaque trailing metadata. The stream operators at
`0x003FC326`/`0x003FC2B8` read and write a marker, a counted vector of zoom
distances, then four floats: parallax base, parallax range, size, and
side-swipe. `cCameraParamsCommand::Parse` (`0x0078600E`) is their source path.

One positional zoom value expands to five values by repeated multiplication by
`0.5`. Therefore vanilla's stored values
`5000 2500 1250 625 312.5 100 1 4 10` canonically decompile to:

```text
cameraParams 5000 -sideSwipe 10
```

The second stored parallax float is a nonnegative range; source syntax takes
the base and endpoint, so it is reconstructed as `base, base + range`.

## Effect-child rotations

The shared child parser accepts `-rotateX`, `-rotateY`, `-rotateZ`,
`-rotateXYZ`, and `-rotateZXY`, multiplies each angle by 2*pi (so angles are
fractions of a full turn, not degrees), and applies the
matrix rotations in command order. The matrix methods at `0x00660230`,
`0x0062D1F6`, and `0x0065FF22` post-multiply, so `-rotateXYZ x y z` stores
`Rx(x) * Ry(y) * Rz(z)`.

The decompiler inverts a finite rotation matrix to that canonical XYZ form,
rebuilds it, and emits the angles only when every matrix element agrees within
floating-point tolerance. Shear, scale, reflection, and otherwise incompatible
matrices remain unsupported rather than being guessed.

## Decal life playback

`cDecalLifeCommand::Parse` (`0x0078017C`) maps playback switches exactly:

| Source switch | Stored result |
| --- | --- |
| none | repeat mode `0` |
| `-loop` | repeat mode `1` |
| `-single` | repeat mode `2` |
| `-sustain` | repeat mode `3` |
| `-static` | flag bit 6 plus repeat mode `1` |

If `-static` is combined with a later mode switch, bit 6 remains set and the
later switch replaces the mode byte. Both pieces are emitted when necessary.
The reader's runtime normalization of stored mode 0 to static/single behavior
does not alter the preserved wire bytes.

## Scrubber maps and demolition actions

`cGroupScrubberCommand::Parse` (`0x0078BC26`) proves the complete map argument
layout. `-blob index value halfExtent [spread]` writes the same half-extent to
both axes; `-rect index value halfX halfY [spread]` writes them separately.
Equal extents are emitted canonically as `-blob`, unequal extents as `-rect`.

The packed action word uses its low byte for `-demolishEffectID` and upper bits
for the rubble action:

| Upper bits | Canonical meaning |
| ---: | --- |
| `0x0000` | no rubble action |
| `0x0300` | `-createBurntRubble` |
| `0x1300` | `-createRubble`, or `-explode` when the low byte is its default `2` |

The command parser's default low byte is `1`; `-explode` changes it to `2`.
Other explicit IDs overwrite that byte and can be combined with the recovered
rubble switch.

## Compiler lineage and shared `killOutsideCity`

Particle `terrain_name` at `+0x160` behaves as compiler lineage/name metadata:
vanilla values resemble source particle identifiers, but no parser setter or
runtime consumer has been found. The particle descriptor is already flattened,
so the decompiler ignores this provenance field without a coverage warning.

Source and collision `-killOutsideCity` set the same particle flag bit 11.
The decompiler emits it once on the canonical `source` command; repeating it in
`collide` would not preserve any additional state or behavior.

## Coverage-note policy

Compilation discards source spelling even when it preserves behavior: examples
include `rate` versus `emit -rate`, `-dir` versus `-velocity`, source shape
keywords that collapse to the same bounds, gravity plus wind that collapses to
one force vector, and relative tractor points that become absolute. These are
documented canonicalization choices, not decompilation gaps, and no longer
produce per-record coverage messages. Coverage is reserved for stored state the
emitted source cannot reproduce, invalid enum domains, and genuinely unknown
runtime fields.

## Compiling `.fx` back to `EFFDIR`

The compiler (`fx/parser.py`, `fx/compiler.py`) mirrors the game's command
parsers. Its acceptance test decompiles vanilla `SimCity_1.dat`, compiles the
text, and compares every collection. The result, on the 1,094,484-byte vanilla
resource:

| Collection | Records matching |
| --- | --- |
| particles, decals, shakes, lights, dynamic particles | all |
| brushes, attractors, scrubbers, sequences, sounds, cameras | all |
| effect descriptions, effect name map, effect key map, message triggers | all |

The compiled resource is byte-identical to vanilla: every collection matches
and `write_resource` of the compiled model equals the original 1,094,484
bytes. The two rules below are what closed the last gap.

### Findings from building the compiler

These corrections come from comparing the compiled output with vanilla and
from the Mac `cSC4EffectsParser` parsers:

- Particle collision is registered as `collide`, not `collision`.
- Effect flags are switches (`effect e -viewRelative`), and `life` is
  `base [vary]`, with an omitted `-preroll` storing the base.
- `-speed`, `randomWalk -delay`, and `randomWalk -strength` store base minus
  and plus variation. `-turn`, `-delay` on `emit`, and `-trigger` store their
  two values directly.
- `force -screw` and `warp -screw` both store the value times the double
  constant `0.02`, and `force -gravity g` stores `(0, -g, 0)` exactly.
- Only one `-tractor` or `-wiggle` is read per command, so each point needs
  its own line. `-wiggleDir amount a b` stores `a` in the second record vector
  and `b` in the first.
- `-rotateX`, `-rotateY`, `-rotateZ`, and `-rotateXYZ` take fractions of a
  turn, multiplied by 2*pi by the parser. They are not degrees.
- `maintain` accepts only `-delay`. The other timing switches live on `emit`.
- `source -model`, `-city`, and the other shape switches are an else-if chain,
  so a line can only name one. Two model bits need two `source` commands.
- `camera` takes any number of positional zooms. One value expands to five by
  halving, and more than one is stored as given.
- Particle `effectBase` writes the field earlier named `terrain_name`.
- `cSC4EffectsCollection` stores effects in an SGI `hash_multimap` keyed on
  the lowercased name, so the on-disk name map order is that table's iteration
  order: hash `h = 5*h + c`, initial buckets from `next_prime(100)`, prime
  growth, inserts at the bucket head (after an equal key), and growth reverses
  chains. This reproduces all 1154 vanilla entries. Name-map order in
  third-party resources such as NAM's differs and is harmless to the reader.
- Shake and light parser defaults differ from their constructors. The shake
  block starts at length `5`, fade `1`, aspect `1`, amplitude `[1]`, and
  frequency `[60]`. An empty light strength or color falls back to `[1]`
  and `kColorBlue`.
- A `select` block adds `~n` to its last child's probability, where `n` is the
  number of explicit children. It counts instead of summing, so vanilla's
  probabilities in a select do not total `65535`.
- Anonymous children start with `ignoreLength` set for attractor, scrubber,
  and camera children, and for sound children with zero length. `-respectLength`
  clears it.

A record that nothing references (an orphaned sound, scrubber, or camera) and
an effect whose children were created after a later record both come from an
effect that was defined twice. The decompiler reproduces that with an empty
*ghost* `effect` block at the record's position, or a ghost carrying the
orphaned children, followed by the real definition. Both are valid source,
since the parser keeps one description per name and priority and appends
anonymous children as it parses.

### Transform `revision` counts assignments

`legacy_transform.revision` is the transform's own byte counter, not a parser
counter. The parser bumps it on a scratch record, but `vector<cDescriptionRec>`
push_back copy-constructs into the scratch vector, and the copy constructor
zeroes it (Mac `cS3DTransform` at `0x0066039A`). Only `cS3DTransform::operator=`
(`0x0062BA46`) increments it, without copying the source's value, so the byte
counts assignments since the slot was last constructed.

`AddEffectDescription` assigns over the existing slot when an effect is
redefined (same name and priority): children below the old size are assigned
(revision plus one), children past the old size are copy-constructed (zero),
and a definition with more children than the slot's capacity reallocates and
zeroes all of them. The effect vector itself doubles when full (capacity 1, 2,
4, ... 2048), and reallocating it copy-constructs every effect, which zeroes
every child and shrinks each child vector to fit.

The compiler replays this in `_assign_children` and `_grow_effect_vector`. The
decompiler reads a nonzero revision as that many redefinitions after the last
growth of the effect vector (index 1024 for vanilla) and emits ghost
definitions to get there, with named filler children so no pool gains records.
Each ghost is a valid `effect` block that the game's parser reads the same way.
This matches all 62 vanilla children in 21 effects, which all carry a uniform
value per effect, as equal-sized redefinitions produce.

### Normalization and the x87 state

The Windows parsers normalize a vector with the inverse length times each
component (`-alpha` `0x0059B680`, `-dir` and `-velocity` `0x0059C280`, `-wind`
`0x0059A820`). The instruction streams keep the inverse and products in x87
registers, and the Mac build divides by the length instead. Vanilla values
fixed which arithmetic is right:

| Particle | Stored value | Model that reaches it |
| --- | --- | --- |
| 85 | velocity center Y `0.99999994` | single-precision inverse, for example `-dir "0 1.7 0"` |
| 457 | alpha direction `0.9238796 0 -0.38268349` | single-precision inverse with squares summed in parser order |

An extended or double inverse and the Mac division reach neither value. The
CRT sets 53-bit precision (`__setdefaultprecision`), so the parser ran with the
FPU in 24-bit mode, which is inferred from these records and is the state
Direct3D setup usually leaves. `float32.normalized` models it: every `fmul`,
`fadd`, `fsqrt`, and `fdiv` rounds to single, and the squares add in the
parser's order. This is verified against vanilla and the disassembly, and the
FPU state itself is inferred.

### `include` and `loadResource`

`cFileParser::DoParseFile` treats `include` and `sinclude` the same way, at the
line level, before command dispatch, with its own comment state per file and
paths relative to the including file. A missing file raises `Couldn't open
file` for both in this build, even though the later ArgScript makes `sinclude`
silent. The compiler expands both and keeps file and line positions.

`loadResource` is rejected by the compiler. The game merges the loaded
resource into the collection being saved (`AddToCollection`, `0x003E4120`), and
a resource stores no pool names, so compiling it would copy the other resource
into the output and still not let source text reference its particles.
