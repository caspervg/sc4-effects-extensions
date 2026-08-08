# Packed EFFDIR wire format

Status: `Partial`

This is the serializer recovered from the SimCity 4 executable with Ghidra.
It is intentionally not presented as a proven mapping of the SC4 Wiki's
numbered EFFDIR sections. The wiki, `or_dat`, and `scdbpf` are useful leads,
but are not evidence for EFFDIR field meaning here.

## Container identity

DBPF MCP identifies the vanilla resource as:

```text
Type     EA5118B0
Group    EA5118B1
Instance 00000001
Kind     EFFDIR
Stored   compressed
Size     111721 bytes
```

The game code uses the same type/group when resolving `loadResource` and
`effectsResource`; see [resource binding](../top-level/resource-binding.md).

## Verified stream rules

- little-endian byte order
- the stream begins with two `uint16` values: major version, minor version
- the game's writer emits `4, 2`
- the reader accepts major version `3` or `4`
- vector counts are `uint32`
- strings use the game's stream string operator; the packed EFFDIR
  `std::string` path is a length-prefixed `cRZString` byte payload with no
  character-code conversion in the operator
- `float` values are IEEE-754 single precision
- scalar byte/word/dword reads are selected by the stream vtable, not by the
  wiki's `DWORD` labels

The serializer's stream calls establish this primitive mapping:

| Stream vtable offset | Verified operation |
| ---: | --- |
| `+0x14` | byte-sized value |
| `+0x1C` | `uint16`/`int16` value |
| `+0x24` | `uint32` value |
| `+0x30` | `float32` value |
| `+0x3C` | string stream operation |

`+0x20` occurs in one effect-description record. Ghidra shows it as a
four-byte scalar operation; its signedness and semantic type remain unknown.

DBPF MCP exposes the vanilla payload and compression metadata, but does not
currently provide an EFFDIR/QFS semantic decoder. Do not use a provisional
container decompression pass as evidence for EFFDIR counts or field meaning;
the version and vector order below come from the executable serializer.

## Verified top-level wire spine

`cSC4EffectsResource::Write` at `0x003DE3DA` and `Read` at `0x003DDA9C`
serialize this sequence:

| Order | Wire data | Executable type / interpretation |
| --- | --- | --- |
| 1 | `u16 major`, `u16 minor` | resource version |
| 2 | `u32 count`, records | `cSC4ParticlesDescription` |
| 3 | `u16 marker = 1` | group marker written by the resource serializer |
| 4 | `u32 count`, records | `cSC4DecalDescription` |
| 5 | `u16 marker = 0` | group marker |
| 6 | `u32 count`, records | `cSC4ShakeDescription` |
| 7 | `u16 marker = 0` | group marker |
| 8 | `u32 count`, records | `cSC4LightDescription` |
| 9 | six `u32` counts plus records | brush, attractor, scrubber, sequence, sound, camera component vectors |
| 10 | `u16 marker = 1` | group marker |
| 11 | `u32 count`, records | `cSC4DynamicParticleDescription`; read only when major version is `4` |
| 12 | `u16 marker = 2` | group marker |
| 13 | `u32 count`, records | `cSC4EffectDescription` |
| 14 | repeated `string`, `u32` pairs | effect-name lookup map |
| 15 | `string "end"`, `u32 0xFFFFFFFF` | lookup-map terminator |
| 16 | `u8 hasTrailingFloats`, optional vector | resource trailing metadata; optional `vector<float>` |
| 17 | `u32 count`, records | effect-key map: `string`, `u32 group`, `u32 instance` |
| 18 | `u32 0` | reserved/terminating scalar |
| 19 | `u32 count`, records | `cSC4MessageTriggerDescription` |

The marker words are part of the observed serializer contract. They must not
be treated as the Wiki's section terminators without testing another game
resource or a write/read round trip.

## Version-1 reader paths

The resource reader has separate paths for the observed version-selector value
`1`. These are reader paths, not evidence that the editor may silently use the
current writer for an older resource.

### Version-1 particles

`cSC4ParticlesDescription::ReadVersion1` at `0x003F66BA` reads the same
serialized member sequence as the current `operator>>` at `0x003F61AA` in the
traced executable: the three bitsets, the scalar/vector members, all six
curve vectors, the nested wiggle/tractor/timed records, the resource fields,
and the final model/explosion fields. The separate function is therefore a
version-gated compatibility entry point, but no distinct particle wire layout
has been demonstrated yet.

The editor should still record the version path in resource metadata and test
it independently. It must not infer a missing field merely because the game
uses a separate reader function.

### Version-1 effect descriptions

`cSC4EffectDescription::ReadVersion1` at `0x003FC72C` is genuinely different:

```text
bitset<9>
u32 priority
vector<DescriptionRec>
vector<EventRec>
string effect_name
```

It does not consume the three current-layout start-message scalars at object
offsets `+0x20`, `+0x24`, and `+0x28`; it initializes at least `+0x20` to zero
in memory. The current reader at `0x003FC790` consumes those three `u32`
values after the effect name. Consequently, a version-1 reader must use a
shorter effect record and the parser must not drift into the following record.

No distinct `WriteVersion1` function is identified in the current program.
Until a matching writer or controlled round trip is found, version-1 editing
should support lossless reading and unchanged writing only, or reject a
canonical rewrite that would require inventing the old writer contract.

## Component records

The component vector order is fixed by `cSC4EffectsResource::Read/Write`:

1. `cSC4BrushDescription`, allocated as `0x34` bytes
2. `cSC4AttractorDescription`, allocated as `0x14` bytes
3. `cSC4ScrubberDescription`, allocated as `0x50` bytes
4. `cSC4SequenceDescription`, allocated as `0x1C` bytes
5. `cSC4SoundDescription`, allocated as `0x1C` bytes
6. `cSC4CameraDescription`, allocated as `0x18` bytes

Allocation size is an in-memory size, not a claim that the wire record has
the same size. The following are wire order, not fixed offsets: strings and
vectors make the wire records variable-length. `member +0xNN` is the
corresponding executable object member, useful for correlating the reader and
writer but not for seeking in the file.

| Type | Verified wire order |
| --- | --- |
| Brush | `u16 marker(Write=0)`, `u32@+0x0c`, `f32@+0x10`, `f32@+0x14`, `u8@+0x18`, `u32@+0x1c`, `cS3DVector2@+0x20`, `cS3DVector2@+0x28`, `f32@+0x30` |
| Attractor | `u16 marker(Write=0)`, `string@+0x0c`, `u32@+0x10` |
| Scrubber | `u16 marker(Write=1)`, `u32@+0x0c`, `u32@+0x10`, `u32@+0x14`, `u32@+0x18`, `f32@+0x1c`, `f32@+0x20`, `u32@+0x24`, conditional `u32@+0x28`, `u32@+0x2c`, `u32@+0x30`, `u32@+0x34`, `u32@+0x38`, `f32@+0x3c`, `cS3DVector2@+0x40`, `f32@+0x48`, `f32@+0x4c` |
| Sequence | `u16 marker(Write=1)`, `vector<SequenceItem>@+0x0c`, `bitset<3>@+0x18`; each item is `cS3DVector2` followed by `string` |
| Sound | `u16 marker(Write=0)`, `bitset<1>@+0x0c`, `u32@+0x10`, `f32@+0x14`, `f32@+0x18` |
| Camera | `u16 marker(Write=0)`, `bitset<4>@+0x0c`, `u8@+0x10`, `u8@+0x11`, `f32@+0x14` |

The scrubber reader only consumes the two fields at `+0x28` and `+0x2c` if
the marker is nonzero; its writer emits them unconditionally. This is a real
version/compatibility quirk, not a reason to assume that every marker is a
section number.

The nested `cS3DVector2` and `cS3DVector3` records are respectively two and
three `f32` values. The brush nested records therefore are not anonymous
scalars; both are verified vector-2 values.

The scalar meanings are not assigned in this document where Ghidra only
shows an anonymous member. The text-format pages provide the safest semantic
names for editor presentation, but the binary decoder should retain the raw
value and wire type until each mapping is independently cross-checked.

## Particle descriptor

`cSC4ParticlesDescription::operator>>` at `0x003F61AA` is the largest
descriptor. Its fields are listed in wire order below. The `member +0xNN`
annotations are executable object offsets; they are not wire offsets.

```text
bitset<32>@+0x000, bitset<8>@+0x004, bitset<11>@+0x008
cS3DVector2@+0x00c, f32@+0x014, u32@+0x018, f32@+0x01c
cS3DVector2@+0x020, cS3DVector2@+0x028, cS3DBoundingBox@+0x030
cS3DVector2@+0x048, cS3DBoundingBox@+0x050
f32@+0x068, f32@+0x06c, f32@+0x070, f32@+0x074, f32@+0x078
cS3DVector3@+0x07c
vector<f32>@+0x088, vector<cS3DVector3>@+0x094
vector<f32>@+0x0a0, vector<f32>@+0x0ac
vector<f32>@+0x0b8, vector<f32>@+0x0c4
u32@+0x0d0, u8@+0x0d4, u8@+0x0d5, f32@+0x0d8, f32@+0x0dc
cS3DVector3@+0x0e0, f32@+0x0ec, f32@+0x0f0
cS3DVector3@+0x0f4, f32@+0x100, f32@+0x104
vector<Wiggle>@+0x108, f32@+0x114, cS3DVector2@+0x118
cS3DVector3@+0x120, vector<f32>@+0x12c
f32@+0x138, f32@+0x13c, f32@+0x140, f32@+0x144
f32@+0x148, f32@+0x14c, f32@+0x150, f32@+0x154
cS3DVector2@+0x158, string@+0x160, u16@+0x164, u16@+0x166
f32@+0x168, cS3DVector2@+0x16c, cS3DVector2@+0x174
f32@+0x17c, f32@+0x180, cS3DVector3@+0x184
f32@+0x190, f32@+0x194, f32@+0x198, vector<f32>@+0x19c
f32@+0x1a8, u32@+0x1ac, vector<TractorPoint>@+0x1b0
f32@+0x1bc, vector<TimedEffect>@+0x1c4
f32@+0x1d0, f32@+0x1d4, vector<u32>@+0x1d8
f32@+0x1e4, f32@+0x1e8, vector<f32>@+0x1ec, f32@+0x1f8
```

Nested records are also verified:

| Nested record | Wire members |
| --- | --- |
| `Wiggle` | `f32`, `cS3DVector3`, `cS3DVector3` (`28` bytes of fixed scalar payload) |
| `TractorPoint` | `cS3DVector3`, `cS3DVector3`, `f32`, `f32` (`32` bytes) |
| `TimedEffect` | `string`, `f32` |

The three leading bitsets are serialized as one `u32` each. The bit widths
(`32`, `8`, and `11`) are verified; their individual meanings are not.
Constructor defaults are executable observations, not semantic assignments.
For example, the writer/constructor initializes the float vector at `+0x088`
with `25`, the vector at `+0x094` with white, several scalar defaults to
`1`, and the height-range values around `+0x158` to `-1000000000`, `-10000`,
and `10000`. These resemble parts of the Wiki description but do not prove
the Wiki labels.

## Other top-level descriptors

These records are decoded from their paired read/write operators. As above,
the order is wire order and `member +0xNN` is only an in-memory correlation.

### Decal

`cSC4DecalDescription` (`Read 0x0076270E`, `Write 0x0076289E`):

```text
bitset<7>, u32, u8, u8, f32,
vector<f32>, vector<f32>, vector<f32>, vector<cS3DVector3>, vector<f32>,
f32, f32, f32, f32, cS3DVector2
```

The reader normalizes the second byte to `2` and sets a bit when that byte is
zero. That post-read behavior should be preserved by an editor rather than
silently treated as a fixed wire default.

### Shake and light

```text
cSC4ShakeDescription:
  f32, f32, vector<f32>, vector<f32>, f32, u8

cSC4LightDescription:
  vector<cS3DVector3>, vector<f32>, f32
```

The shake vector members occur at object offsets `+0x08` and `+0x14`; the
final byte is at `+0x24`. The light reader/writer pair is at `0x003FC6EC`
and its symmetric writer; it is not a Wiki “section 4” assertion.

### Dynamic particle

`cSC4DynamicParticleDescription` is present only for major version `4`:

```text
bitset<7>@+0x08, string@+0x0c,
u32@+0x28, vector<u32>@+0x2c,
f32@+0x10, f32@+0x14, f32@+0x18,
f32@+0x1c, f32@+0x20, f32@+0x24
```

The read operator is `0x004B8ADA` and the paired writer is `0x004B8A2E`.
Both place the model key and model-key vector before the six floats; the
non-monotonic member offsets above are therefore also the exact wire order.
The first bitset is serialized through the 7-bit bitset operator and occupies
one `u32` on the wire. The constructor at `0x004B89B2` initializes mass
(`+0x10`) to `1.0`; the remaining scalar members start at zero.

## Effect descriptions

`cSC4EffectDescription` (`Read 0x003FC790`, `Write 0x003FC4DA`) has this
verified shape:

```text
bitset<9>@+0x00, u32@+0x04,
vector<DescriptionRec>@+0x08, vector<EventRec>@+0x14,
string@+0x2c, u32@+0x20, u32@+0x24, u32@+0x28
```

The object layout is non-monotonic because the two vectors and string are
non-scalar C++ members. The wire order is exactly the order shown, not the
ascending member-offset order.

`DescriptionRec` (`Read 0x003FC5A4`) is:

```text
string@+0x00, u8@+0x04, bitset<2>@+0x08,
legacy-transform,
u8@+0x44, u8@+0x45, u16@+0x46, u16@+0x48,
f32@+0x4c, f32@+0x50, f32@+0x54, f32@+0x58,
u16@+0x5c, u16@+0x5e, u32 resolved-description-index@+0x60
```

`legacy-transform` is not an opaque 40-byte blob. `S3DTransformLegacyLoad`
at `0x0009844A` consumes, in order:

```text
3 x Vec3 (row-major cS3DMatrix3 rows)
1 x Vec3 (translation)
1 x f32  (uniform scale)
1 x u32  (transform revision; object retains the low byte)
```

The bitset is serialized as a `u32`. The legacy loader (`0x0009844A`) derives
the in-memory matrix/translation/scale presence flags, then replaces the
transform's one-byte revision counter with the low byte of the final wire
word. `cS3DTransform::operator=` (`0x0062BA46`) increments that counter on
mutation. The editor exposes three editable matrix rows, translation, scale,
and revision instead of one opaque matrix tuple.

`EventRec` (`Read 0x003FC69E`) is:

```text
bitset<4>, string, f32, u32
```

The four event bits are fully correlated between the group-effect text
commands and `cSC4EffectsManager::StartAncilliary` (`0x00405030`):

| Bit | Text producer | Runtime meaning |
|---:|---|---|
| 0 | `shakeEffect` | dispatch the resolved shake descriptor |
| 1 | shake default or flash `-epicentre`/`-epicenter` | use the effect origin as an epicenter |
| 2 | `flashEffect` | dispatch the resolved light descriptor as a screen flash |
| 3 | `tintEffect` | dispatch the resolved light descriptor as a lighting tint |

For an epicentered flash, the `f32` is the falloff radius (the parser default
is `1000.0`). The final `u32` is the resolved shake/light descriptor index;
the string retains the source definition name. Shake and tint do not consume
the `f32` in the traced runtime path.

The effect-description reader dispatches to the version-1 record layout when
the second version word is `1`; the current major-4 resource uses the full
operator above. The particle version-1 reader is a separate compatibility
entry point, but its traced wire sequence matches the current particle
operator. The effect version-1 layout must therefore not be conflated with the
current effect layout.

## Message trigger descriptor

`cSC4MessageTriggerDescription` is the final top-level vector. Its complete
record is simply:

```text
u32, string
```

The reader is `0x003FC288`; the writer emits the same two members through the
generic `u32` and string stream operators.

These are wire-shape observations from the Ghidra operators; semantic names
for anonymous members remain open reverse-engineering work.

## Parser cross-reference (not binary semantics)

Per the reverse-engineering boundary for this format, the text parser is not
used to assign binary semantics. The cross-reference below records only which
source spelling writes which member. It is useful provenance for later tests,
but is not evidence of what the game does with the value at runtime. Fields
not independently explained by consumers, calculations, or controlled
resource pairs remain raw and unknown.

For particle commands, `cSC4EffectsParser +0x120` is the working particle
descriptor. The particle offsets below are translated from that base; this is
why parser workspace offsets must not be mistaken for object offsets.

### Effect records

`cGroupEffectCommand::Parse` at `0x0078510A` directly maps these members of
`cSC4EffectDescription`:

| Member | Text property | Evidence |
| --- | --- | --- |
| bitset bit 0 | `viewRelative` | direct bit set |
| bitset bit 1 | `noAutoStop` | direct bit set |
| bitset bit 2 | `hardStop` | direct bit set |
| bitset bit 3 | `rigid` | direct bit set |
| bitset bit 4 | `noPropagate` | direct bit set |
| bitset bit 5 | `applyCursor` | direct bit set |
| bitset bit 6 | `ignoreOrientation` | direct bit set |
| bitset bit 7 | `noLODStop` | direct bit set |
| bitset bit 8 | `manualRestart` | direct bit set |
| `+0x04` | `priority` | direct scalar assignment |
| `+0x20`, `+0x24`, `+0x28` | `startMessage` arguments 1–3 | direct scalar assignments |

The description string at `+0x2c` is not assigned by this handler, and its
meaning is intentionally unknown. Description and event vectors are filled by
child commands, not by this top-level parser.

`cMessageTriggerCommand::Parse` at `0x007857BC` writes the final top-level
record as `message id` followed by `effect name`; this mapping comes from its
two non-switch text arguments.

### Component records

These mappings come from the component parse handlers and use the serialized
object offsets already listed above.

| Record/member | Text property or option | Parser evidence |
| --- | --- | --- |
| Brush `+0x0c` | `-name` resource key | `cGroupBrushCommand::Parse`, `0x0078C690` |
| Brush `+0x10` | `-rate`; also `-apply` value | same |
| Brush `+0x14` | `-length` | same |
| Brush `+0x18` | apply mode set by `-apply` | same; byte only |
| Brush `+0x1c` | `-zoom` minus one | same |
| Brush `+0x20/+0x24` | `-strength` minimum/maximum | same |
| Brush `+0x28/+0x2c` | `-width` minimum/maximum | same |
| Brush `+0x30` | `-level` | same |
| Attractor `+0x0c` | `-name` or `-group` string | `cGroupAttractorCommand::Parse`, `0x0078BA44` |
| Attractor `+0x10` | name/group selector (`-group` sets `1`) | same |
| Scrubber `+0x10` | no text assignment or runtime consumer found (`value_10 (unused?)`) | constructor `0x003E13F4`; reader/writer preserve it |
| Scrubber `+0x14` | `-demolish` | `cGroupScrubberCommand::Parse`, `0x0078BC26` |
| Scrubber `+0x24` | `-burn` | same |
| Scrubber `+0x28` | `-toxic` | same |
| Scrubber `+0x2c` | `-extinguishFire` | same |
| Scrubber bitset bits 0–3 | `noNetworks`, `noFlora`, `dezone`, `single` | same |
| Scrubber bitset bits 4–6 | `pauseSim`, `pauseSimHidden`, `pauseClock` | same |
| Scrubber `+0x4c` | pause duration | same |
| Scrubber `+0x30/+0x34` | `-message` arguments 1–2 | same |
| Scrubber `+0x38` | `-blob`/`-rect` effect-map index (1–8) | same; consumed by `cSC4ScrubberEffect::AddBlobToMap`, `0x003E16F2` |
| Scrubber `+0x3c` | value added to the selected effect map | same; `cSC4EffectMaps::AddRectToMap`, `0x0041A97C` |
| Scrubber `+0x40/+0x44` | rectangle half-extents | parser and `cSC4ScrubberEffect::SetTransforms`, `0x003E109C` |
| Scrubber `+0x48` | rounded map expansion/falloff count | `AddBlobToMap` and `AddRectToMap` |
| Scrubber `+0x18` | demolition action/effect packed value | same; exact sub-bit semantics open |
| Scrubber `+0x1c/+0x20` | `-minDemolishSize`/`-maxDemolishSize` | same |
| Sequence bitset bits 0–2 | `loop`, `noOverlap`, `hardStart` | `cSequenceEffectCommand::Parse`, `0x00784724` |
| Sequence item vector | `wait` and `play` timing values | `cSequenceWaitCommand::Parse`, `0x00784B26`; `cSequencePlayCommand::Parse`, `0x00784C08` |
| Sequence item string | `play` effect name | same |
| Sound bitset bit 0 (`+0x0c`) | no setter or runtime test found (`bit 0 (unused?)`) | `bitset<1>` stream overload `0x00768594`; reader `0x003E026E` |
| Sound `+0x10` | `-name` resource key | `cGroupSoundCommand::Parse`, `0x0078CC8A`; passed to the sound system by `Start`, `0x003E0154` |
| Sound `+0x14` | inverse `-locationUpdateRate` | same |
| Sound `+0x18` | `-length` | same |
| Camera bitset bits 0–3 | `zoom`, `rotation`, `target`, `slave` | `cGroupCameraCommand::Parse`, `0x0078B6B8`; all tested by `cSC4CameraEffect::Start`, `0x003DFBDA` |
| Camera `+0x10` | zero-based zoom value | parser and `Start`; see parser discrepancy below |
| Camera `+0x11` | runtime rotation value | `Start` passes it to `cSC4CameraControl::SetRotation` |
| Camera `+0x14` | `attachRadius` | same |

The scrubber action field is not reduced to guessed bit names: the parser
combines `explode`, `createRubble`, `createBurntRubble`, and
`demolishEffectID`, so the packed value must be retained as both raw bits and
the known source options.

The scrubber constructor (`0x003E13F4`) initializes map value `+0x3c` to
`16.0`; the editor uses that value for new records. The sound constructor
(`0x003DFE90`) similarly establishes `0.5` as the default stored update
interval at `+0x14`. Sound flag bit 0 is still preserved and editable: the
`unused?` label is negative evidence for this Mac build, not a reserved-bit
claim.

The Mac camera text parser has an internal inconsistency visible in the
instructions at `0x0078B91E`: `rotation` sets flag bit 1 but stores its `0..3`
argument in byte `+0x10`. Runtime `Start` instead reads rotation from `+0x11`,
while using `+0x10` for zoom. Binary records therefore retain separate
`zoom` and `rotation` bytes according to their runtime consumers; the editor
does not model the parser's apparent erroneous write as union storage.

### Effect child records

`cSC4EffectsParser::ParseDescRecOptions` at `0x00401D2C` directly assigns:

| DescriptionRec member | Text property | Notes |
| --- | --- | --- |
| `+0x08` bit 0 | `ignoreLength` / `respectLength` | `ignoreLength` sets it; `respectLength` clears it |
| `+0x08` bit 1 | enclosing `systemSequence` block | set by `cGroupParticlesCommand::Parse`, `0x0078D6C4`; consumed by the model-particle chain path at `0x00406246` |
| transform matrix at `+0x10` | `rotateX`, `rotateY`, `rotateZ`, `rotateXYZ`, `rotateZXY` | row-major 3×3 rotation matrix; angles are multiplied by `2π` |
| `+0x34/+0x38/+0x3c` | `offset` | vector components |
| `+0x40` | `scale` | transform flag is also updated |
| `+0x44/+0x45` | `lod` / `lodRange` | low/high bytes; parser default is 1/6 |
| `+0x46/+0x48` | particle `shells` count and stagger delay | `cGroupParticlesCommand::Parse`, `0x0078D6C4`; runtime creates `count` instances and applies `delay × shell index` at `0x00406246` |
| `+0x4c/+0x50` | `emitScale` minimum/maximum | one value supplies both |
| `+0x54/+0x58` | `sizeScale` minimum/maximum | one value supplies both |
| `+0x5c` | enclosing `select` group ID | assigned by `AddDescription`/`AddAnonDescription`; consumed by `UpdateVisualEffect`, `0x0040658E` |
| `+0x5e` | `prob` | stored through the parser's 16-bit encoding |
| `+0x60` | resolved component-description index | anonymous records receive it immediately; named records begin at `-1` and collection resolution fills it before runtime |

`cGroupDynamicParticleCommand::Parse` at `0x00784148` creates this record,
assigns its child name string, initializes the `+0x04` byte to `0x10` for
this command path, and invokes the option parser. The byte is therefore
parser-observed, but its complete enum is not yet established. The
`cDescriptionRec` constructor (`0x0077AE3A`) confirms defaults of `1` shell,
`16` shell delay, no selection group/probability, and description index `-1`.

### Particle records: direct command assignments

The three leading serialized values are the descriptor's complete flag
storage. `cSC4ParticlesDescriptionBase` constructs object offsets `+0x00`,
`+0x04`, and `+0x08` as zero (`0x003F54DA`); the current writer
(`0x003F5BD8`) emits them first and the current reader (`0x003F61AA`) reads
them first, as `bitset<32>`, `bitset<8>`, and `bitset<11>`. The text parser's
working descriptor begins at `cSC4EffectsParser +0x120`, so parser accesses at
`+0x120/+0x124/+0x128` are the same three object members, not three unrelated
parser flags.

The complete parser-observed bit map is:

| Word | Bit | Text command/option that sets it |
| --- | ---: | --- |
| leading (`+0x00`, 32 bits) | 0 | `light` draw option |
| | 1 | `emit` or `inject` (shared mode bit) |
| | 2 | `maintain` |
| | 3 | emission `sustain` |
| | 4 | `noCull` draw option |
| | 5 | emission `base` |
| | 6 | source `model` |
| | 7 | source `modelBase` |
| | 8 | collision command present |
| | 9 | collision `sticky` |
| | 10 | `terrainRepel` |
| | 11 | collision/source `killOutsideCity` |
| | 12 | source `city` |
| | 13 | source `cityWindySide` (also sets bit 12) |
| | 14 | source `pinToTerrain` |
| | 15 | source `pinToWater` |
| | 16 | source height filter: `terrainOnly`, `waterOnly`, `seaOnly`, `lakeOnly`, `belowHeight`, `aboveHeight`, or `heightRange` |
| | 17 | source `seaOnly` (with bit 16) |
| | 18 | source `lakeOnly` (with bit 16) |
| | 19 | emission `scale` |
| | 20 | emission `areaScale` |
| | 21 | emission `volumeScale` |
| | 22 | source `scaleParticles` |
| | 23 | random-walk command present |
| | 24 | random-walk `wait` |
| | 25 | random-walk `preferSea` |
| | 26 | force `alphaAttractor` |
| | 27 | force `motherDuck` |
| | 28 | force `tractor` or `tractorRel` |
| | 29 | texture `hflip` |
| | 30 | texture `vflip` |
| | 31 | timed child effect present |
| second (`+0x04`, 8 bits) | 0 | collision `destroyBuildings` |
| | 1-7 | no setter or runtime test found (`bit N (unused?)` in the editor) |
| third (`+0x08`, 11 bits) | 0 | model command present |
| | 1 | model `fakePerspective` |
| | 2 | model `applyLighting` |
| | 3 | model `moveEntireSlave` |
| | 4 | model `slaveApplyAlpha`/`applyAlpha`, and force `alphaAttractor` (shared bit) |
| | 5 | model `sustain` |
| | 6 | model `modelSpeed` |
| | 7 | alignment `windBank` |
| | 8 | warp `wiggleVerts`, `uv`, or `alpha` (shared bit) |
| | 9 | source `resetIncoming` |
| | 10 | model `noCullFaces` |

This table corrects three tempting but false presence correlations. `inject`
sets leading bit 1, not bit 3; bit 3 is `sustain`. Random-walk `preferDir`
writes `+0x184` but does not set bits 24 or 25. Plain `wiggle`/`wiggleDir`
and generic alignment do not set third bits 8 and 7; those bits are specific
to the options listed above.

Runtime cross-references support the word identities and the active meanings:
the `cSC4ParticlesEffect` methods test the leading word throughout emission,
source, collision, random-walk, force, and rendering paths. In particular,
`UpdateParticlePhysicsExtra` (`0x00417DC8`) tests second-word bit 0 before the
building-destruction path. Across the traced particle runtime methods, no test
of second-word bits 1-7 was found. This is strong evidence that bit 0 is the
only active middle-word flag in this build, while `unused?` remains a qualified
editor label rather than a claim that those serialized positions can never be
used by another build.

The following are source-to-member correlations only. They are intentionally
phrased using command names where no independent binary semantic has been
established.

| Particle member | Text parser assignment | Parser evidence |
| --- | --- | --- |
| leading bitset bit 10 | terrain-repel command present | `cParticleTerrainRepelCommand::Parse`, `0x0077FFD4` |
| `+0x0c/+0x10` | `life` minimum/maximum | `cParticleLifeCommand::Parse`, `0x0077E104` |
| `+0x1c` | `preroll` | same |
| `+0x68` | `size` `vary` value | `cParticleSizeCommand::Parse`, `0x00786304` |
| `+0x6c` | `aspect` `vary` value | `cParticleAspectCommand::Parse`, `0x00786416` |
| `+0x70` | `rotate` `vary` value | `cParticleRotateCommand::Parse`, `0x00786516` |
| `+0x74` | `rotate` `offset` value | same |
| `+0x88` vector | `emit` rate, `maintain`, or `inject` value | `0x0078667C`, `0x00785E28`, `0x00785F28` |
| leading bitset bits 1–3 | shared `emit`/`inject`, `maintain`, `sustain` | emit/maintain/inject handlers |
| `+0xac` vector | size-over-time command values | command dispatch; exact normalization still open |
| `+0xb8` vector | aspect-over-time command values | same |
| `+0xc4` vector | rotate-over-time command values | same |
| `+0xd0` | texture resource key | `cParticleTextureCommand::Parse`, `0x00785C30` |
| leading bitset bits 29–30 | `hflip`, `vflip` | same |
| `+0x13c/+0x140` | first two terrain-repel values | `cParticleTerrainRepelCommand::Parse` |
| `+0x144` | `scout` | same |
| `+0x148` | `vertical` | same |
| `+0x14c` | `killHeight` | same |
| `+0x16c/+0x170` | random-walk `delay` minimum/maximum | `cParticleRandomWalkCommand::Parse`, `0x0077FC62` |
| `+0x174/+0x178` | random-walk `strength` minimum/maximum | same |
| `+0x17c/+0x180` | random-walk `turn` minimum/maximum | same |
| leading bitset bits 23–25 | random-walk present, `wait`, `preferSea` | same |
| `+0x184` | random-walk `preferDir` | same |
| `+0x1c4` vector | timed child effect data | `cParticleTimedEffectCommand::Parse`, `0x00784FA6` |
| leading bitset bit 31 | timed child effect present | same |

Further command handlers fill the previously anonymous particle members:

| Particle member | Text parser correlation | Parser evidence |
| --- | --- | --- |
| `+0x78` | alpha `vary` value | `cParticleAlphaCommand::Parse`, `0x0078A3BC` |
| `+0x94` vector | color curve values | `cParticleColorCommand::Parse`, `0x0078A538` |
| `+0x7c` | color `vary` vector | same |
| `+0xa0` vector | alpha curve values | `cParticleAlphaCommand::Parse` |
| leading bitset bit 8 | collision command present | `cParticleCollisionCommand::Parse`, `0x0078A790` |
| leading bitset bit 9 | collision `sticky` | same |
| leading bitset bit 11 | collision/source `killOutsideCity` | same; shared bit is not assigned a single meaning |
| `+0x138` | collision `bounce` | same |
| `+0x150` | collision `effect`/`death` value | same; the two source options share the member |
| `+0x154` | collision `deathByWater` | same |
| second bitset bit 0 | collision `destroyBuildings` | same |
| `+0xd5` | alignment enum | `cParticleAlignmentCommand::Parse`, `0x0078AA74` |
| `+0x190` | alignment `damp` | same |
| `+0x194/+0x198` | alignment `bank`/`windBank` range | same |
| third bitset bit 7 | alignment `windBank` mode | same |
| `+0xd0` | model resource key | `cParticleModelCommand::Parse`, `0x0078AC9E` |
| `+0xd4` | model draw-option byte; parser writes `3` | same; enum not established |
| `+0x1d4` | `modelSpeed`/`modelSpeedStatic` | same |
| `+0x1d8` vector | multiple model resource keys | same |
| third bitset bits 1–6, 10 | model options: `fakePerspective`, `applyLighting`, `moveEntireSlave`, `slaveApplyAlpha`, `sustain`, model speed, `noCullFaces` | same |
| `+0xe0` vector | accumulated `gravity`/`wind` force | `cParticleForceCommand::Parse`, `0x0078710C` |
| `+0xec` | `global_wind` | same |
| `+0xf0` | `bomb` scalar | same |
| `+0xf4` vector | `bomb` direction | same |
| `+0x100` | `drag` | same |
| `+0x104` | `screw` | same |
| `+0x19c` vector | attractor/automata curve values | same; several options share this storage |
| `+0x1a8` | attractor/automata strength or rate value | same; exact runtime role remains open |
| `+0x1b0` vector | `tractor`/`tractorRel` points | same |
| `+0x1bc` | `tractorResetSpeed` | same |
| leading bitset bit 28 | tractor command present | same |
| `+0x1e4` | `explosion` scalar | same |
| `+0x1e8` | `explosionFront` secondary scalar | same |
| `+0x1ec` vector | explosion curve values | same |
| `+0x1f8` | `explosionFront` value | same |
| `+0x108` vector | `wiggle`/`wiggleDir` records | `cParticleWarpCommand::Parse`, `0x007880EC` |
| third bitset bit 8 | `wiggleVerts`, `uv`, and alpha warp mode | same; shared mode bit |
| `+0x114` | `uv` scalar | same |
| `+0x118` | `uv` vector | same |
| `+0x120` | `alpha` warp direction | same |
| `+0x12c` vector | alpha warp curve values | same |
| `+0x50` bounding box | particle source region | `cParticleSourceCommand::Parse`, `0x0077F0D6` |
| `+0x158` vector | source `belowHeight`/`aboveHeight`/`heightRange` | same; source options share the range |
| leading bitset bits 12–13 | source `city`/`cityWindySide` | same |
| leading bitset bits 14–18 | `pinToTerrain`, `pinToWater`, terrain/water restriction, `seaOnly`, `lakeOnly` | same |
| leading bitset bit 22 | `scaleParticles` | same |
| third bitset bit 9 | `resetIncoming` | same |
| `+0x14/+0x18` | emission `loop`/`single` values | `cParticleEmitCommand::Parse`, `0x0078667C` |
| `+0x20/+0x24` | emission `delay` range | same |
| `+0x28/+0x2c` | emission `trigger`/`retrigger` range | same |
| `+0x30` bounding box | emission `velocity` region | same |
| `+0x48/+0x4c` | emission speed minimum/maximum | same |
| leading bitset bits 19–21 | emission `scale`, `areaScale`, `volumeScale` | same |
| `+0xd8` | draw `sortOffset` | `(anonymous namespace)::ParseDrawOptions`, `0x004018F0` |
| `+0xdc` | particle `stretch` divisor | `cParticleStretchCommand::Parse`, `0x0077DEAA`; consumed by `cSC4ParticlesEffect::InitEffectsParticle`, `0x004182A4` |
| `+0x1ac` | force `automata` occupant/type id | `cParticleForceCommand::Parse`, `0x0078710C`; consumed by `cSC4ParticlesEffect::UpdateAttractor`, `0x0041583E` |

Additional particle constraints from the traced handlers:

- leading bitset-0 bits 6 and 7 select `model` and `modelBase` source modes;
  bits 12 and 13 select `city` and `cityWindySide`. The source handler also
  distinguishes `point`, `square`, `quad`, `cube`, `box`, and `dice` forms and
  writes the source-region members accordingly (`cParticleSourceCommand::Parse`,
  `0x0077F0D6`);
- `+0xd0` is a mode-dependent resource key: texture and model commands share
  this storage, so it is not two independent keys;
- the model command sets third-bitset bit 0 for model presence, bit 2 for
  lighting, bit 3 for moving an entire slave, bit 4 for applying alpha, bit 5
  for sustain, bit 6 for model-speed presence, and bit 10 for no-cull-faces.
  `modelSpeed` and `modelSpeedStatic` use the same model-speed storage
  (`cParticleModelCommand::Parse`, `0x0078AC9E`);
- the collision parser supplies a default bounce of `0.3` when omitted,
  clamps `death` and `deathByWater` through `[0,1]`, and stores `effect` and
  `death` in the same scalar at `+0x150` (`cParticleCollisionCommand::Parse`,
  `0x0078A790`);
- the text parser multiplies size-curve inputs by `50` before storing the
  `+0xac` curve (`cParticleSizeCommand::Parse`, `0x00786304`). This is a
  parser-unit transform, not proof of the engine's semantic unit.

These observations explain the complete three-word particle flag map plus more
of the descriptor's mode sharing and normalization. Bounding boxes and several
shared curve/force members remain raw until runtime consumers are traced.

Only three scalar particle placeholders remain: `u16 +0x164`, `u16 +0x166`,
and `f32 +0x168`. The constructor (`0x003F54DA`) initializes them to `0`, `1`,
and `1.0`; assignment and binary read/write paths copy or serialize them, but
no text-parser setter or read in the traced `cSC4ParticlesEffect` runtime
methods was found. The editor consequently keeps the stable offset names and
shows `value_164 (unused?)`, `value_166 (unused?)`, and
`value_168 (unused?)`. This is deliberately qualified negative evidence, not
permission to discard their wire values.

### Major-4 dynamic-particle descriptor

The major-4 `cSC4DynamicParticleDescription` has a smaller, separate
working object. The traced parser writes these members:

| Member | Text parser correlation | Parser evidence |
| --- | --- | --- |
| `+0x0c` string | `base` command name | `cDynamicParticleEffectBaseCommand::Parse`, `0x0078A0AC` |
| `+0x10` | `mass` | `cDynamicParticleMassCommand::Parse`, `0x00789DA6` |
| `+0x18/+0x1c` | friction minimum/maximum | `cDynamicParticleFrictionCommand::Parse`, `0x00789C74` |
| `+0x20` | friction `angular` value | same |
| `+0x28` | one model resource key | `cDynamicParticleModelCommand::Parse`, `0x00789E54` |
| `+0x2c` vector | multiple model resource keys | same |

`cDynamicParticleEffectCommand::RegisterCommands` at `0x007834EA` confirms
that the only nested command families are `effectBase`, `model`, `mass`, and
`friction`. Its top-level parser at `0x0078A162` constructs a fresh descriptor
(thereby applying the `1.0` mass default), optionally inherits a named base
descriptor, and resolves its name.

The seven-bit word at `+0x08` is serialized and copied by descriptor
assignment, but none of the four direct parser handlers assigns it. The
runtime descriptor consumers `cSC4DynamicParticleEffect::SetDescription`
(`0x004B91A8`) and `Start` (`0x004BA6B0`) use the base name, model keys, mass,
and friction values without reading `+0x08`. Package evidence agrees: all
three dynamic-particle records in the vanilla
`EA5118B0-EA5118B1-00000001` resource have a zero flag word (`p_vehicle`,
`p_train`, and `p_train_toxic`). Therefore bits 0-6 are best classified as
serialized but unconsumed/reserved-looking in this build, not as named
options. The editor preserves them and intentionally presents qualified
`bit N (unused?)` labels. The floats at `+0x14` and `+0x24` have the same
zero-in-vanilla and unconsumed status and are shown as `value_14 (unused?)`
and `value_24 (unused?)`.

### Decal descriptor

The decal child handlers also resolve most of the anonymous vector members.
The following offsets use the decal working-object base at parser offset
`+0x370`, which matches the serialized object layout:

| Member | Text parser correlation | Parser evidence |
| --- | --- | --- |
| `+0x04` | texture resource key | `cDecalTextureCommand::Parse`, `0x00785890` |
| `+0x08` | `draw` enum | same |
| `+0x00` bits 1, 2, 3, 5 | `light`, `water`, `repeat`, `ring` | same |
| `+0x5c` | texture `offset` vector | same |
| `+0x58` | texture `repeat` value | same |
| `+0x0c` | `life` value | `cDecalLifeCommand::Parse`, `0x0078017C` |
| `+0x00` bit 6 | decal `static` | same |
| `+0x09` | `static`/`loop`/`single`/`sustain` mode: 1/1/2/3 | same |
| `+0x10` vector | rotate command values | `cDecalRotateCommand::Parse`, `0x007889A0` |
| `+0x1c` vector | size command values | `cDecalSizeCommand::Parse`, `0x007887CC` |
| `+0x28` vector | alpha command values | `cDecalAlphaCommand::Parse`, `0x0078977C` |
| `+0x34` vector | color command values | `cDecalColorCommand::Parse`, `0x007898F8` |
| `+0x40` vector | aspect command values | `cDecalAspectCommand::Parse`, `0x00788910` |
| `+0x4c` | alpha `vary` value | same |
| `+0x50` | size `vary` value | same |
| `+0x54` | rotate `vary` value | same |
| `+0x00` bit 4 | size `cityScale` | `cDecalSizeCommand::Parse` |

The decal constructor initializes a useful new-record template: life `5.0`,
rotate curve `[0.0]`, size curve `[1.0]`, alpha curve `[1.0]`, color curve
`[white]`, aspect curve `[1.0]`, zero variation values, final scalar `1.0`,
and zero offset (`cSC4DecalDescription::cSC4DecalDescription`, `0x007600D2`).
These are constructor defaults, not universal semantic defaults. The reader's
zero-repeat normalization remains significant: a zero second byte becomes `2`
and sets bit 6 (`0x0076270E`).

### Shake descriptor

The shake parser's working object begins at parser offset `+0x3e0`, matching
the six serialized members:

| Member | Text parser correlation | Parser evidence |
| --- | --- | --- |
| `+0x00` | `length` | `cShakeLengthCommand::Parse`, `0x0077DF20` |
| `+0x04` | length `fade` | same |
| `+0x08` vector | `amplitude` values | `cShakeAmplitudeCommand::Parse`, `0x00788AA0` |
| `+0x14` vector | `frequency` values | `cShakeFrequencyCommand::Parse`, `0x00788B30` |
| `+0x20` | `aspect` | `cShakeAspectCommand::Parse`, `0x0077E008` |
| `+0x24` | `baseTable` enum | `cShakeBaseTableCommand::Parse`, `0x0077E07E` |

The length parser clamps fade to length when a larger fade is supplied
(`cShakeLengthCommand::Parse`, `0x0077DF20`). `aspect` is parsed as a float,
whereas `baseTable` is parsed through the executable's
`kShakeBaseTableTypes` enum table; it is not an arbitrary numeric curve. The
constructor starts both amplitude and frequency vectors empty
(`cSC4ShakeDescription::cSC4ShakeDescription`, `0x0075E1F0`).

### Light descriptor

The light working object begins at parser offset `+0x414`:

| Member | Text parser correlation | Parser evidence |
| --- | --- | --- |
| `+0x00` vector | `color` values | `cLightColorCommand::Parse`, `0x00789148` |
| `+0x0c` vector | `strength` values | `cLightStrengthCommand::Parse`, `0x00788C86` |
| `+0x18` | `length` | `cLightLengthCommand::Parse`, `0x0077DB2A` |

The light constructor starts the color and strength vectors empty and sets
length to `2.0` (`cSC4LightDescription::cSC4LightDescription`, `0x00760A72`).
The color handler parses each input as a color vector and the strength handler
parses each input as a float curve (`0x00789148`, `0x00788C86`). These are
variable-length vectors on the wire, not fixed-size color/strength scalars.
The parser also has an explicit byte-range color scaling path; the editor
should preserve that as a command transform rather than bake it into the
binary field's name.

The names `size-over-time` and similar are deliberately tied to the parser
command that fills the vector, not asserted as engine behavior. Several
Particle members still without a direct text assignment are explicitly
qualified in their descriptor sections rather than treating the now-decoded
DescriptionRec transform as opaque.

### Records not yet source-mapped

The shake, light, decal, and major-4 dynamic-particle child commands are now
partially correlated above; their runtime consumers, remaining flags, and
normalization rules are still open. Particle members without a traced command
assignment remain raw. None of these gaps should be filled from the Wiki or
from the existing text-format documentation alone.

## Evidence and next decoder boundary

Primary evidence:

- Ghidra `cSC4EffectsResource::Read`: `0x003DDA9C`
- Ghidra `cSC4EffectsResource::Write`: `0x003DE3DA`
- Ghidra component serializers in the `0x003DF...`–`0x003E2...` range
- DBPF MCP inspection of the vanilla `SimCity_1.dat` entry

The minimum useful editor architecture is therefore:

1. decode DBPF/QFS as a separate container layer;
2. decode this resource spine with bounded readers and preserve unknown
   members byte-for-byte;
3. expose semantic names only for fields confirmed against text parsing,
   runtime behavior, or controlled game-generated write/read pairs.

Do not implement the Wiki's 15-section layout as the binary model until a
second executable/resource pair demonstrates that it is equivalent.
