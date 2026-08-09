# EFFDIR editor specification

Status: `Design / Partial`

This document specifies the editor built on the recovered packed EFFDIR
serializer. The executable's read/write operators and the wire layout in
[effdir.md](./effdir.md) are the binary contract. The Wiki, `or_dat`,
`scdbpf`, and the text effects format are reference material, not authority
for the packed format.

## Design goals

The editor must:

- read and write the major-3 and major-4 resource variants;
- preserve fields and bytes whose meaning is not known;
- expose useful command-oriented names without confusing them with proven
  runtime semantics;
- support adding and removing effect descriptions and their child records;
- make a read/write round trip safe before it becomes convenient.

The editor is not a converter to the Wiki's numbered 15-section layout. The
packed resource is an object graph with a fixed serializer order, vectors,
strings, marker words, and several variable-length records.

## Three layers

Keep these layers separate in the implementation.

### 1. Container layer

DBPF locates the resource by complete TGI
`EA5118B0-EA5118B1-00000001`. The container layer must:

1. locate the exact DBPF entry;
2. decompress its payload according to DBPF metadata;
3. pass only the uncompressed EFFDIR bytes to the resource layer;
4. write the updated payload back through the DBPF layer.

EFFDIR parsing must never guess at DBPF compression, and DBPF code must not
interpret EFFDIR counts or records.

### 2. Wire layer

The wire layer owns a bounded little-endian cursor and the recovered stream
operations:

```text
u8, u16, u32, f32, string, vector<T>
```

It reads the top-level sequence exactly as listed in `effdir.md`, including
all marker words. Object member offsets such as particle `+0x1a8` are useful
labels only; they are not file offsets because strings and vectors are
variable-length.

Every decoded member should retain:

```text
wire type
raw value or raw bytes
semantic view, if known
source/evidence level
```

Unknown four-byte values remain four-byte values. They must not be silently
converted to a guessed signed integer, enum, or float.

### 3. Semantic/editor layer

The editor layer presents stable record types—particle, decal, shake, light,
effect description, component records, and lookup maps—and overlays names on
wire members. A semantic overlay must identify its evidence:

```text
wire        = established by read/write operators
parser      = a text command writes this member
runtime     = a consumer/calculation gives it an observed role
inferred    = useful hypothesis, never the default interpretation
```

The UI and API should show this level beside command-derived names. A field
with only `parser` evidence remains editable as a raw value and must not be
described as engine-confirmed.

## Normative wire primitives

All multi-byte values are little-endian. The primitive grammar is:

```text
u8       = one unsigned byte
u16      = two bytes, unsigned
u32      = four bytes, unsigned
f32      = four IEEE-754 binary32 bytes
bitset<N> = the executable's N-bit bitset stream operation
```

The bitset operator currently occupies one `u32` on the wire for the observed
32-, 11-, 9-, 7-, 4-, 2-, and 1-bit logical sets. The editor must preserve the
complete storage word, including bits that have no catalog entry.

The vector grammar is fully specified:

```text
vector<T> = u32 count followed by count serialized T values
```

There is no element-size field and no byte-length field. Examples:

```text
vector<f32>       = u32 count + count × f32
vector<Vec2>      = u32 count + count × (f32, f32)
vector<Vec3>      = u32 count + count × (f32, f32, f32)
vector<Wiggle>    = u32 count + count × (f32, Vec3, Vec3)
vector<Tractor>   = u32 count + count × (Vec3, Vec3, f32, f32)
vector<Timed>     = u32 count + count × (string, f32)
```

`std::vector`'s in-memory pointer/size/capacity representation is never
written to the file. A vector count is validated before allocation and before
each element is consumed. For fixed-size `T`, the cursor checks
`count × sizeof(T)` with overflow protection; for variable-size `T`, parsing
is bounded element by element.

The stream string encoding has two layers. The executable has a UTF-8-capable
framework string subsystem, but the packed EFFDIR `std::string` overload uses a
`cRZString` byte-string adapter and assigns its bytes directly. Thus EFFDIR
wire strings are opaque length-prefixed bytes; UTF-8, ASCII, MacRoman, or
another code page is a convention to be established for a particular source
resource, not a conversion performed by the EFFDIR stream operator. The editor
must retain both decoded text and the original framing/raw bytes.

### String contract

Strings need their own wire type in the schema; they are not interchangeable
with arbitrary text or null-terminated byte arrays. Until the stream operator
at vtable offset `+0x3c` is traced completely, every string is represented as:

```text
WireString {
    decoded: optional string,
    raw_bytes: bytes,
    encoding: "utf8" | "platform_code_page" | "raw_bytes" | "unknown",
    framing: optional StringFraming,
    valid: bool,
    changed: bool
}

StringFraming {
    length_encoding: "7bit_continuation" | "unknown",
    length_width: optional u8,
    length_units: "bytes" | "code_units" | "characters" | "unknown",
    length_signedness: "signed" | "unsigned" | "unknown",
    terminator: "none" | "in_memory_only" | "zero" | "unknown",
    version: optional Version
}
```

The verified binary helper behavior is:

```text
encode_length(n):
    n == 0       -> emit 00
    n > 0        -> emit 7-bit groups from least significant to most
                    significant; set bit 7 on every non-final emitted byte

decode_length:
    read bytes while bit 7 is set, strip bit 7, then fold the groups in
    reverse order with value = (value << 7) | group

serialized_char_string(s):
    emit encode_length(number of payload bytes)
    emit exactly those payload bytes
    emit no serialized NUL terminator
```

This is a variable-width unsigned length, not a fixed `u8`, `u16`, or `u32`.
For example, length `0` is `00`, length `1` is `01`, and length `128` is
`80 01`. The executable's `GetRZCharStr` adds a NUL only to the destination
buffer in memory; that NUL is not part of the file. `GetGZStr`/`SetGZStr`
uses the same length helper and reads/writes the payload in chunks, appending
the bytes to a `cIGZString` object.

The remaining string questions are narrower than the framing question:

- whether the EFFDIR `std::string` overload delegates to the byte-string path
  or the `cIGZString` path in every relevant operator;
- whether any EFFDIR consumer applies case or normalization rules.

For the traced char-string helper, `length_units: bytes` and
`terminator: in_memory_only` are verified. For the packed EFFDIR
`std::string` overload, the wire payload is verified as raw byte data; its
textual interpretation remains a separate question.

Ghidra evidence for this framing is `DecodeStringLength` at `0x00019B44`,
`EncodeStringLength` at `0x00019CE2`, `GetGZStr`/`SetGZStr` at
`0x00019BB8`/`0x00019D3A`, and `GetRZCharStr`/`SetRZCharStr` at
`0x00019C5A`/`0x00019D96`.

### Encoding evidence and editor policy

The distinction between wire bytes and framework text comes from executable
behavior, not from the textual effect parser or the wiki specification:

- `GetCurrentFrameworkCodePage` at `0x00014B8A` returns `8`, and the converter
  treats code page `8` as UTF-8 in this build;
- `ConvertStringEncoding(cIGZString const&, cIGZString&, long)` at
  `0x000160C0` explicitly treats the source `cIGZString` bytes as UTF-8 when
  converting to another code page;
- `ConvertUTF8StringToDestinationFormat(cIGZString&)` at `0x00043AA6` also
  starts from UTF-8 and converts only when the destination framework code page
  differs;
- `ConvertStringEncoding` at `0x00015922` contains explicit UTF-8 decoding and
  encoding paths, plus a UTF-16 path. `-2` selects UTF-8 and `-1` selects the
  locale-derived system code page.

The packed EFFDIR path is different. `operator>>(cIGZIStream&, std::string&)`
at `0x00761A94` constructs a static `cRZString`, calls the stream virtual
string operation at `+0x3c`, and then assigns the `cRZString` contents directly
to the destination `std::string`. It does not call the UTF-8/code-page
conversion functions. The related `CharStringToRZString` and
`RZStringToCharString` helpers at `0x000141D6` and `0x00014226` likewise show
byte-string transfer rather than transcoding.

Therefore EFFDIR is not proven to be UTF-8, and it is not proven to be ASCII-
only either. It stores the bytes supplied to the `std::string`/`cRZString`
path. A platform code page may be the convention used to create those bytes,
but the packed format contains no code-page tag and the reader does not select
one. The separate framework converter implements an old, broad UTF-8-like form
accepting sequences beyond modern Unicode's normal four-byte limit; that is a
capability of the framework, not evidence about EFFDIR wire strings.

The default editor behavior is consequently:

1. treat the EFFDIR payload as raw bytes and preserve it exactly when unchanged;
2. offer strict UTF-8 as a display candidate when it validates, while clearly
   labeling that interpretation as a codec choice rather than wire evidence;
3. allow alternate code-page decoding only as a diagnostic or explicitly
   selected codec;
4. write the selected codec's bytes directly, with a preview of the changed
   byte sequence and an opt-in warning when the codec is not verified.

This establishes raw-byte storage for the packed EFFDIR strings and UTF-8
support only in the separate framework conversion layer. The remaining RE step
is empirical: find a known non-ASCII EFFDIR resource or game-generated pair
and identify which codec produced its bytes.

### Cross-platform portability inference

The vector contract is strong architectural evidence about portability. The
wire representation is `count + serialized elements`; it does not expose the
pointer/size/capacity layout of the Mac executable's GCC `std::vector`. That
is exactly the kind of explicit persistence contract required for the same
EFFDIR resource to be consumed by a Windows build with a different STL
backend.

The shared 7-bit string-length helpers provide similar evidence that the
binary streams were intended to be portable. It is therefore a strong working
hypothesis that the Windows and Mac EFFDIR resources use the same stream
framing and that the various string overloads adapt to one common wire
contract. The exact C++ overload delegation remains an implementation detail,
not a reason to create separate editor encodings without evidence.

For the editor this means:

- model vectors and strings as explicit wire codecs, never as serialized STL
  objects;
- use one string framing codec unless a platform-specific executable trace
  disproves that contract;
- keep the source platform and executable evidence in resource metadata;
- treat a byte-encoding difference, if discovered, as a codec layer change,
  not as a different EFFDIR record layout.

This is a `strong hypothesis`, not yet a direct Windows-binary comparison.
The comparison fixture should be added when a Windows executable or resource
becomes available.

The editor must distinguish at least these usage categories, even if they
currently share one stream operation:

```text
ResourceName       = effect/child/terrain/model lookup name
EffectName         = name used by an effect or message reference
MapKey             = key in an executable lookup map
SequenceName       = effect name inside a sequence item
FreeTextOrUnknown  = string whose consumer is not established
```

These are usage labels, not separate encodings. They help the UI show likely
references and help agents search the right textual documentation, while the
raw stream representation remains authoritative.

String handling requirements:

- preserve the original framing and bytes when a string is unchanged;
- preserve invalid or undecodable bytes instead of replacing them;
- distinguish null/empty/absent when the wire format distinguishes them;
- do not normalize case, path separators, suffixes, or Unicode form unless a
  runtime rule proves that normalization occurs;
- reject a changed string if its encoding/framing is not known, unless the
  caller explicitly selects a verified writer codec;
- report every changed string's old/new byte length because it can move all
  later variable-length fields.

To resolve the remaining string uncertainty, an agent should trace both the
read and write implementations behind `+0x3c`, confirm which overload is used
by the EFFDIR operators, and compare resources containing empty, ASCII,
extended-byte, and long strings. A controlled game-generated read/write pair
upgrades a field binding from `unknown` to `runtime` evidence; until then,
string values are safe to display but are not safe to re-encode through an
unverified codec.

## Resource model

Represent the resource as:

```text
EffDirResource {
    version: { major: u16, minor: u16 },
    particles: [ParticleDescriptor],
    marker_1: u16,
    decals: [DecalDescriptor],
    marker_2: u16,
    shakes: [ShakeDescriptor],
    marker_3: u16,
    lights: [LightDescriptor],
    components: {
        brushes, attractors, scrubbers, sequences, sounds, cameras
    },
    marker_4: u16,
    dynamic_particles: [DynamicParticleDescriptor],
    marker_5: u16,
    effect_descriptions: [EffectDescription],
    effect_name_map: [StringU32Pair],
    trailing_float_metadata: optional vector<f32>,
    effect_key_map: [StringU32U32Record],
    reserved: u32,
    message_triggers: [MessageTrigger],
    preservation: PreservationData
}
```

The names above describe executable record types and serializer positions,
not Wiki sections. Marker values are retained even when they have the usual
values `1`, `0`, `0`, `1`, and `2`.

`PreservationData` must retain at least:

- original version and marker words;
- unknown bitset bits and unknown scalar members;
- unknown vector elements;
- string and trailing metadata representations;
- records skipped by a version gate;
- any input bytes needed for a lossless unchanged-record strategy.

## Typed resource schema

The following schema is normative for the editor model. `Raw<T>` means that
the wire type is known but the semantic meaning is not. `Field<T>` adds the
semantic overlay and provenance metadata without changing the wire value.

```text
Raw<T> = {
    value: T,
    wire_type: string,
    raw_bytes: bytes,
    source_span: { start: u64, end: u64 }
}

Field<T> = {
    raw: Raw<T>,
    label: optional string,
    evidence: "wire" | "parser" | "runtime" | "inferred",
    binding_ids: [string]
}

Vec2 = { x: f32, y: f32 }
Vec3 = { x: f32, y: f32, z: f32 }
Bounds2 = { minimum: Vec2, maximum: Vec2 }
Bounds3 = { minimum: Vec3, maximum: Vec3 }

WireVector<T> = {
    count: u32,
    items: [T],
    source_span: { start: u64, end: u64 }
}

Wiggle = { amount: f32, direction: Vec3, uv: Vec3 }
TractorPoint = { position: Vec3, direction: Vec3, time: f32, amount: f32 }
TimedEffect = { effect_name: WireString, time: f32 }
WireString = {
    decoded: optional string, raw_bytes: bytes,
    encoding: "utf8" | "platform_code_page" | "raw_bytes" | "unknown",
    framing: optional StringFraming, valid: bool, changed: bool
}

RecordPreservation = {
    original_bytes: bytes,
    unknown_members: [RawValue],
    original_order: optional [string]
}

PreservationData = {
    original_payload: bytes,
    unknown_top_level: [RawValue],
    version_gated_records: [RawValue],
    trailing_bytes: bytes,
    diagnostics: [Diagnostic]
}

RawValue = {
    path: string, wire_type: string, value: optional any, raw_bytes: bytes,
    source_span: { start: u64, end: u64 }
}

Diagnostic = {
    severity: "error" | "warning" | "info",
    code: string,
    path: optional string,
    message: string,
    source_span: optional { start: u64, end: u64 }
}
```

### Resource and collection schema

```text
EffDirResource {
    version: Version,
    read_profile: ReadProfile,
    particles: WireVector<ParticleDescriptor>,
    marker_particles_decals: Raw<u16>,
    decals: WireVector<DecalDescriptor>,
    marker_decals_shakes: Raw<u16>,
    shakes: WireVector<ShakeDescriptor>,
    marker_shakes_lights: Raw<u16>,
    lights: WireVector<LightDescriptor>,
    components: ComponentCollections,
    marker_components_dynamic: Raw<u16>,
    dynamic_particles: WireVector<DynamicParticleDescriptor>,
    marker_dynamic_effects: Raw<u16>,
    effect_descriptions: WireVector<EffectDescription>,
    effect_name_map: WireVector<StringU32Pair>,
    trailing_float_metadata: OptionalVector<f32>,
    effect_key_map: WireVector<StringU32U32Record>,
    reserved: Raw<u32>,
    message_triggers: WireVector<MessageTrigger>,
    preservation: PreservationData
}

Version = { major: Raw<u16>, minor: Raw<u16> }
ReadProfile = "current" | "version1"
StringU32Pair = { name: WireString, target: Raw<u32> }
StringU32U32Record = {
    name: WireString, first: Raw<u32>, second: Raw<u32>
}
MessageTrigger = { message_id: Raw<u32>, effect_name: WireString }
OptionalVector<T> = { present: Raw<u8>, value: optional WireVector<T> }
```

### Version-1 read profile

The resource reader has a separate version-1 compatibility path. The decoder
must select it from the observed version selector before parsing any records;
it must not parse a version-1 effect with the current effect tail and hope that
the following count remains aligned.

```text
Version1Profile {
    particle_reader: same wire sequence as ParticleDescriptor,
    effect_description_reader: Version1EffectDescription
}

Version1EffectDescription {
    flags: Raw<bitset<9>>,
    priority: Raw<u32>,
    descriptions: WireVector<DescriptionRecord>,
    events: WireVector<EventRecord>,
    chain_effect: WireString
}
```

The particle version-1 reader is `ReadVersion1` at `0x003F66BA`; its traced
field sequence matches the current particle reader, so it is represented as a
separate read profile without duplicating the particle schema. The effect
version-1 reader is `ReadVersion1` at `0x003FC72C`; unlike the current reader,
it does not consume `start_message_1`, `start_message_2`, or `start_message_3`
after `chain_effect`. The current readers are `0x003F61AA` and `0x003FC790`.

The editor must retain `read_profile` in preservation metadata. Version-1
resources may be inspected and written back unchanged, but canonical edits
must be rejected until a matching version-1 writer or a controlled
read/write-compatible output is verified. The absence of a discovered
`WriteVersion1` function is a diagnostic, not permission to emit the current
effect tail for an old resource.

The map target fields remain explicit integers. The editor must not call them
vector indices until collection-level code or controlled resources proves
that relationship.

The `@+0xNN` member offsets and exact serializer order remain defined by
`effdir.md`; this schema names the corresponding editor nodes. An agent must
not derive file offsets by adding an object member offset to a record's wire
start.

### Component schema

```text
ComponentCollections {
    brushes: WireVector<BrushDescription>,
    attractors: WireVector<AttractorDescription>,
    scrubbers: WireVector<ScrubberDescription>,
    sequences: WireVector<SequenceDescription>,
    sounds: WireVector<SoundDescription>,
    cameras: WireVector<CameraDescription>
}

BrushDescription {
    marker: Raw<u16>, key: Raw<u32>, rate: Raw<f32>, length: Raw<f32>,
    mode: Raw<u8>, zoom: Raw<u32>, strength: Bounds2, width: Bounds2,
    level: Raw<f32>
}

AttractorDescription { marker: Raw<u16>, name: WireString, selector: Raw<u32> }

ScrubberDescription {
    marker: Raw<u16>, value_0c: Raw<u32>, value_10: Raw<u32>,
    value_14: Raw<u32>, action: Raw<u32>, min_size: Raw<f32>,
    max_size: Raw<f32>, value_24: Raw<u32>, conditional_28: optional Raw<u32>,
    value_2c: Raw<u32>, message_1: Raw<u32>, message_2: Raw<u32>,
    shape: Raw<u32>, shape_value_3c: Raw<f32>, shape_bounds: Vec2,
    shape_value_48: Raw<f32>, pause_duration: Raw<f32>
}

SequenceDescription {
    marker: Raw<u16>, items: WireVector<SequenceItem>, value_18: Raw<u32>
}
SequenceItem { timing: Vec2, effect_name: WireString }

SoundDescription {
    marker: Raw<u16>, value_0c: Raw<u32>, resource_key: Raw<u32>,
    location_update_rate: Raw<f32>, length: Raw<f32>
}

CameraDescription {
    marker: Raw<u16>, value_0c: Raw<u32>, value_10: Raw<u8>,
    value_11: Raw<u8>, attach_radius: Raw<f32>
}
```

Component names such as `rate`, `length`, and `resource_key` are current
parser correlations where noted in `effdir.md`; fields deliberately retain
raw fallback names until their evidence level is upgraded.

### Effect and child schema

```text
EffectDescription {
    flags: Raw<bitset<9>>,
    priority: Raw<u32>,
    descriptions: WireVector<DescriptionRecord>,
    events: WireVector<EventRecord>,
    chain_effect: WireString,
    start_message_1: Raw<u32>,
    start_message_2: Raw<u32>,
    start_message_3: Raw<u32>
}

DescriptionRecord {
    name: WireString, mode: Raw<u8>, flags: Raw<bitset<2>>,
    legacy_transform: LegacyTransform,
    lod: Raw<u8>, lod_range: Raw<u8>, value_46: Raw<u16>, value_48: Raw<u16>,
    emit_scale_min: Raw<f32>, emit_scale_max: Raw<f32>,
    size_scale_min: Raw<f32>, size_scale_max: Raw<f32>,
    value_5c: Raw<u16>, probability: Raw<u16>, value_60: Raw<u32>
}

LegacyTransform {
    matrix: [f32; 9], offset: Vec3, scale: f32, mode: Raw<u8>
}

EventRecord { flags: Raw<bitset<4>>, name: WireString, time: Raw<f32>, value: Raw<u32> }
```

### Particle schema

The particle descriptor is kept as a complete fixed-member object even when
only some members have command bindings:

```text
ParticleDescriptor {
    flags_0: Raw<bitset<32>>, flags_1: Raw<bitset<8>>, flags_2: Raw<bitset<11>>,
    life: Vec2, value_18: Raw<u32>, preroll: Raw<f32>,
    value_20: Vec2, value_28: Vec2, source_bounds: Bounds3,
    value_48: Vec2, render_bounds: Bounds3,
    size_vary: Raw<f32>, aspect_vary: Raw<f32>, rotate_vary: Raw<f32>,
    rotate_offset: Raw<f32>, alpha_vary: Raw<f32>, color_vary: Vec3,
    emit_curve: WireVector<f32>, color_curve: WireVector<Vec3>,
    alpha_curve: WireVector<f32>, size_curve: WireVector<f32>,
    aspect_curve: WireVector<f32>, rotate_curve: WireVector<f32>,
    resource_key: Raw<u32>, draw_mode: Raw<u8>, alignment_mode: Raw<u8>,
    value_d8: Raw<f32>, value_dc: Raw<f32>,
    force: Vec3, global_wind: Raw<f32>, bomb: Raw<f32>,
    bomb_direction: Vec3, drag: Raw<f32>, screw: Raw<f32>,
    wiggles: WireVector<Wiggle>, uv_scale: Raw<f32>, uv_range: Vec2,
    alpha_warp_direction: Vec3, alpha_warp_curve: WireVector<f32>,
    value_138: Raw<f32>, terrain_repel: Vec2, scout: Raw<f32>,
    vertical: Raw<f32>, kill_height: Raw<f32>,
    height_range: Vec2, terrain_name: WireString, value_164: Raw<u16>,
    value_166: Raw<u16>, value_168: Raw<f32>, random_walk_delay: Vec2,
    random_walk_strength: Vec2, random_walk_turn: Vec2,
    prefer_direction: Vec3, alignment_damp: Raw<f32>,
    bank_range: Vec2, attractor_curve: WireVector<f32>,
    attractor_strength: Raw<f32>, value_1ac: Raw<u32>,
    tractor_points: WireVector<TractorPoint>, tractor_reset_speed: Raw<f32>,
    timed_effects: WireVector<TimedEffect>, model_speed: Raw<f32>,
    model_speed_static: Raw<f32>, model_keys: WireVector<u32>,
    explosion: Raw<f32>, explosion_front_secondary: Raw<f32>,
    explosion_curve: WireVector<f32>, explosion_front: Raw<f32>,
    preservation: RecordPreservation
}
```

The field names above are intentionally mixed: command-correlated members
have useful names, while unresolved members retain `value_XX`. The binary
decoder must not make the object less complete merely because its UI hides
some raw fields by default.

### Other descriptor schema

```text
DecalDescriptor {
    flags: Raw<bitset<7>>, texture_key: Raw<u32>, draw_mode: Raw<u8>,
    repeat_mode: Raw<u8>, life: Raw<f32>, rotation: WireVector<f32>,
    size: WireVector<f32>, alpha: WireVector<f32>, color: WireVector<Vec3>,
    aspect: WireVector<f32>, alpha_vary: Raw<f32>, size_vary: Raw<f32>,
    rotate_vary: Raw<f32>, texture_offset: Vec2
}

ShakeDescriptor {
    length: Raw<f32>, fade: Raw<f32>, amplitude: WireVector<f32>,
    frequency: WireVector<f32>, aspect: Raw<f32>, base_table: Raw<u8>
}

LightDescriptor {
    color: WireVector<Vec3>, strength: WireVector<f32>, length: Raw<f32>
}

DynamicParticleDescriptor {
    flags: Raw<bitset<7>>, base_name: WireString, mass: Raw<f32>,
    value_14: Raw<f32>, friction_min: Raw<f32>, friction_max: Raw<f32>,
    angular_friction: Raw<f32>, value_24: Raw<f32>, model_key: Raw<u32>,
    model_keys: WireVector<u32>
}
```

The declaration above groups fields semantically; it is not wire order. The
Mac read/write pair (`0x004B8ADA` / `0x004B8A2E`) serializes dynamic particles
as `flags`, `base_name`, `model_key`, `model_keys`, then the six floats from
`mass` through `value_24`.

## Parsing contract

Parsing is fail-closed and bounded:

1. Check that the DBPF layer supplied an uncompressed payload.
2. Read major/minor as `u16`.
3. Read the top-level vectors in executable order.
4. For every count, check the remaining byte budget before allocation.
5. Parse each nested vector and string through the same cursor.
6. Accept major `3` and `4`; preserve an unsupported major as raw data and
   report it instead of guessing a layout.
7. For major `3`, do not consume a dynamic-particle vector. For major `4`,
   consume it at its observed position.
8. Require the cursor to finish at the expected resource end. Extra bytes are
   preserved and reported, not discarded.

The parser should expose diagnostics rather than repairing input silently:

```text
error: truncated record, invalid string/vector bound, impossible count
warning: unexpected marker, unsupported version, non-finite float,
         unknown bit set, trailing bytes, unresolved lookup target
```

Counts should have a configurable hard limit. This protects the editor from
corrupt files without imposing a semantic limit that the executable has not
been shown to impose.

## Command-oriented interpretation

Command values are represented as bindings, not as a second binary layout:

```text
CommandBinding {
    command: "randomWalk.delay",
    record: "particle",
    members: ["+0x16c", "+0x170"],
    presence_bits: [23],
    encoding: "f32 range",
    evidence: "parser",
    conflicts: [],
    notes: "source spelling that writes these members"
}
```

This permits the editor to display `randomWalk.delay` while still exposing
the raw offsets and the presence bit. Bindings must support:

- one command writing several members;
- several commands sharing one member;
- one command setting both a value and a bit;
- enum/byte values whose complete domain is unknown;
- fields with no command binding.

Examples from the current evidence set:

| Wire member | Editor label | Required qualification |
| --- | --- | --- |
| particle `+0x88` vector | `emit` / `maintain` / `inject` value | shared storage; active command and bits decide the presentation |
| particle `+0x150` | collision `effect` / `death` | shared source storage; do not expose as two independent values |
| particle `+0x19c` vector | attractor / automata curve | shared storage; command provenance required |
| particle `+0xd4` byte | model draw option | parser writes `3`, enum domain unresolved |
| particle leading bits | command-presence/options | only named bits receive overlays; all other bits remain raw |
| decal `+0x08` | draw option | enum values are not complete yet |

The command catalog should be data-driven, but the first implementation only
needs the bindings already documented in `effdir.md`. Do not build a large
generic expression system before a real editing use case requires it.

## Text-reference workflow for agents

Agents working on the editor should consult the textual reference pages, but
must follow this evidence workflow:

1. Start with the wire member and offset in `effdir.md`.
2. Search the relevant command page under `reference/particles/`,
   `reference/effect-children/`, or `reference/top-level/`.
3. Treat command names, accepted arguments, defaults, and transformations as
   candidate bindings only.
4. Locate the corresponding parser handler in the RE notes or Ghidra and
   verify the assignment to the working object.
5. Record the binding with `evidence: parser`, including the parser address and
   translated object offset.
6. Trace a runtime consumer or compare controlled game-generated resources
   before changing the evidence to `runtime`.

If the text page and binary trace disagree, preserve both claims as separate
annotations, keep the raw field authoritative, and emit a conflict warning.
Text documentation is a discovery index for agents—not permission to invent
wire fields or collapse shared storage into separate properties.

The command catalog itself should use this schema:

```text
CommandBinding {
    id: string,
    command_path: string,
    syntax_sources: [DocumentRef],
    record_type: string,
    member_paths: [string],
    presence_bits: [BitRef],
    encoding: Encoding,
    transforms: [Transform],
    shared_storage_group: optional string,
    conflicts: [string],
    evidence: Evidence,
    parser_refs: [CodeRef],
    runtime_refs: [CodeRef],
    notes: string
}

DocumentRef = { path: string, anchor: optional string }
BitRef = { member_path: string, bit: u8 }
CodeRef = { address: string, role: "parser" | "reader" | "writer" | "consumer" }
Evidence = "wire" | "parser" | "runtime" | "inferred"
Encoding = "u8" | "u16" | "u32" | "f32" | "Vec2" | "Vec3" |
           "range" | "enum" | "curve" | "resource_key" | "string" | "raw"
Transform = { description: string, reversible: bool, implementation: string }
```

The catalog is metadata and may be loaded by both the UI and headless agent
tools. It must never be required to parse or rewrite an unknown resource.

## Editing operations

### Change an existing value

An edit targets a record and a wire member, then optionally applies its
command binding:

```text
set particle[17].+0x150 = raw_u32(0x00000002)
set particle[17].collision.deathByWater = true
```

The second form may set a known presence bit and the bound member, but must
surface any shared-storage conflict. The raw form is always available.

### Add a particle or other descriptor

Append a descriptor with constructor-equivalent defaults from the executable
model, then let the caller set required resource keys, names, and command
values. Defaults are convenience values, not semantic claims. Unknown fields
are initialized to the recovered constructor defaults when known; otherwise
they are marked unset and the writer uses the exact documented default policy.

Before writing, validate that all nested vectors and strings are internally
complete. Do not invent a Wiki section number for the new record.

### Add an effect description

An effect description consists of the executable `EffectDescription` record,
its description/event child vectors, and the separate top-level lookup/key
maps. Adding one is a transaction:

1. allocate a new description record at the end of its vector;
2. allocate or validate the child description/event records;
3. allocate its effect-name lookup entry with an explicit `u32` target;
4. allocate any effect-key map entry separately;
5. validate that all names and targets are unique or intentionally replaced;
6. write the complete resource only after the transaction validates.

The editor must not assume that a string in one map implicitly creates a
description, resource key, or child record. Until collection-level target
allocation is independently confirmed, expose the map target as an explicit
editable integer and require the caller to choose it. This avoids silently
creating a broken cross-reference.

### Remove a record

Removal updates the owning vector and reports every map or child reference
that becomes unresolved. Automatic reindexing is allowed only when the map
targets are proven to be vector indices; otherwise preserve target values and
require explicit repair.

## UI specification

The UI is a client of the semantic/editor layer, not a second parser. It may
use DBPF-MCP as one adapter, but the editor core must also work with a local
file adapter or a future standalone application.

### Workspace layout

The minimum useful workspace has four coordinated views:

```text
┌ Package/resource tree ─┬ Record editor ───────────────┐
│ DBPF → EFFDIR          │ semantic fields and commands  │
│ effects → children     │ raw offset/type/value        │
├────────────────────────┼──────────────────────────────┤
│ Diagnostics / references│ Hex + wire cursor           │
│ errors, conflicts, refs │ selected field source span   │
└────────────────────────┴──────────────────────────────┘
```

The UI should support:

- browsing the resource tree without assuming Wiki section numbers;
- switching between semantic and raw views for every field;
- showing evidence badges (`wire`, `parser`, `runtime`, `inferred`);
- showing the command documentation and parser/runtime references for a
  selected field;
- editing vector counts and elements explicitly;
- viewing shared-storage conflicts before changing a value;
- adding/removing records through transactional forms;
- viewing unresolved map targets and affected references;
- previewing the serialized diff before writing the DBPF package.

### Field presentation

Each field editor should show:

```text
label:       randomWalk.delay
path:        particles[17].+0x16c / +0x170
wire type:   Vec2 (two f32)
value:       [5.0, 5.0]
presence:    flags_0 bit 23 = set
evidence:    parser
source:      reference/particles/random-walk.md; parser 0x0077FC62
warning:     runtime meaning not independently verified
```

Unknown values use a raw editor with hexadecimal and typed previews; changing
the preview type must not change the stored wire type. An enum editor is only
allowed when its domain is cataloged; otherwise it is a numeric field with
known observed values.

### UI state and transactions

The UI maintains:

```text
EditorSession {
    source: ResourceHandle,
    original: EffDirResource,
    working: EffDirResource,
    change_set: [Change],
    diagnostics: [Diagnostic],
    selected_path: optional string,
    dirty: bool
}

Change {
    path: string,
    before: RawValue,
    after: RawValue,
    reason: "user" | "binding" | "allocation" | "repair",
    warnings: [string]
}
```

Adding an effect, changing a shared command value, or reindexing a collection
is a transaction. The UI must show a preview and refuse commit when the
resulting resource has truncation, invalid bounds, or unresolved required
references. Undo operates on changesets, not on individual widget state.

### Adapter boundary

Use a small adapter interface so MCP is optional:

```text
EffDirSource {
    inspect(handle) -> ResourceMetadata
    read(handle) -> bytes
    write(handle, bytes, WriteOptions) -> WriteResult
    backup(handle) -> BackupHandle
}
```

The EFFDIR core consumes bytes and returns bytes plus diagnostics. A
DBPF-MCP adapter implements `inspect/read/write`; a local adapter can operate
on extracted payloads or packages. MCP tools should expose the same resource
and diagnostic model rather than inventing an MCP-only semantic representation.

### Core/editor API

The UI and agents should share a small, transport-neutral API:

```text
open(source: ResourceHandle) -> EditorSession
inspect(session) -> ResourceSummary
list_nodes(session, path) -> [NodeSummary]
get_node(session, path) -> Node
set_raw(session, path, RawValue) -> ChangeSet
set_command(session, command_path, CommandValue) -> ChangeSet
add_record(session, collection_path, RecordTemplate) -> ChangeSet
remove_record(session, record_path) -> ChangeSet
add_effect(session, EffectTemplate) -> ChangeSet
validate(session) -> [Diagnostic]
preview_write(session, WriteOptions) -> WritePreview
commit(session, WriteOptions) -> CommitResult
undo(session) -> ChangeSet
redo(session) -> ChangeSet
```

`NodeSummary` includes path, record type, label, evidence, dirty state, and
reference count. `WritePreview` includes changed byte spans, changed record
paths, diagnostics, output size, and whether unknown bytes were preserved.
The API must support headless use so an agent can perform the same operations
as the UI and inspect the same diagnostics.

```text
ResourceHandle = { package_path: string, tgi: string }
ResourceSummary = {
    tgi: string, version: Version, counts: map<string, u32>, dirty: bool
}
NodeSummary = {
    path: string, record_type: string, label: optional string,
    evidence: Evidence, dirty: bool, reference_count: u32
}
Node = { summary: NodeSummary, value: any, raw: RawValue, bindings: [CommandBinding] }
WriteOptions = { mode: "lossless" | "canonical", target_version: optional Version }
WritePreview = {
    changed_spans: [{ start: u64, end: u64 }],
    changed_paths: [string], output_size: u64,
    unknown_bytes_preserved: bool, diagnostics: [Diagnostic]
}
CommitResult = { output: ResourceHandle, backup: optional string, diagnostics: [Diagnostic] }
CommandValue = { command_path: string, arguments: map<string, any> }
RecordTemplate = { record_type: string, values: map<string, any> }
EffectTemplate = {
    name: WireString, description: EffectDescription,
    map_targets: optional { effect_name_target: u32, key_target: optional u32 }
}
ChangeSet = { changes: [Change], diagnostics: [Diagnostic] }
```

### Agent-facing workflow

An agent implementing a feature should be able to follow this sequence:

```text
open → inspect → locate node → read raw + semantic metadata
     → consult text reference → verify binding evidence
     → apply transaction → validate → preview diff → commit
```

The agent must not edit a resource by searching for a guessed byte pattern.
It should address a model path, and the wire writer should calculate the
resulting variable-length offsets.

## Writing contract

The writer follows the executable order, not object-offset order:

- write the original version unless the caller explicitly selects another
  supported version;
- write all marker words in their recorded positions;
- write vector counts immediately before their elements;
- write major-4 dynamic particles only for major `4`;
- use the recorded `read_profile` when writing; do not emit the current effect
  tail for a version-1 resource;
- preserve unknown bit bits and scalar values;
- write strings and optional metadata through the same stream rules as the
  reader;
- reject unresolved required references rather than emitting a guessed target.

Provide two modes:

```text
lossless  = preserve untouched unknown data and original ordering where possible
canonical = emit the recovered executable ordering from the semantic model
```

Both modes use the same wire schema. Canonical mode is not permission to
normalize marker values, enum values, float NaNs, or map targets without an
explicit rule.

For `read_profile: version1`, lossless unchanged output is supported by the
recovered read contract. Canonical edits remain a diagnostic/error until the
version-1 writer contract is verified.

## Validation and tests

The minimum test set is:

1. Parse every available vanilla sample without diagnostics that indicate
   truncation or cursor drift.
2. Read/write an unchanged sample and compare the decoded resource model plus
   preserved unknown data.
3. Mutate one fixed-size scalar and verify that only the expected serialized
   value changes, allowing for offset shifts after variable-length edits.
4. Add and remove a particle, child record, and effect description, then
   reparse and validate counts and references.
5. Exercise major `3` and major `4` gating independently.
6. Exercise the version-1 particle/effect readers separately and verify that
   the shorter version-1 effect record leaves the following count aligned.
7. Test unexpected markers, unknown bits, unsupported versions, malformed
   counts, truncated strings, and trailing bytes.
8. Where possible, compare the editor output with a game-generated write/read
   pair. This is the path for upgrading a binding from `parser` to `runtime`.

The editor should emit a machine-readable diagnostic report containing record
path, member offset, wire type, raw value, semantic label, evidence level, and
whether the value was preserved, changed, or synthesized.

## Implementation order

1. bounded cursor and primitive/vector/string stream operations;
2. top-level resource and record model;
3. raw-preserving read/write round trip;
4. particle and other descriptor command-binding catalog;
5. safe add/remove/edit transactions;
6. runtime-backed semantic upgrades and convenience UI.

Do not start with a semantic-only model. A lossless wire model is the part
that makes future reverse engineering safe.
