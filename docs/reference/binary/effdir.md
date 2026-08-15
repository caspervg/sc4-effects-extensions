# EFFDIR

Status: `Partial`

EFFDIR is the packed effect resource for SimCity 4. The standard Maxis
resource is in `SimCity_1.dat`. It has this resource key:

| Part | Value |
| --- | --- |
| Type | `0xEA5118B0` |
| Group | `0xEA5118B1` |
| Instance | `0x00000001` |

The game can load other EFFDIR resources. The Type and Group stay fixed. The
Instance identifies the resource.

This page describes the SimCity 4 binary format. It does not describe the
different formats that later Maxis games use.

## Specification

The old specification divided the file into 15 numbered sections. This page
keeps those numbers because many existing notes use them. The file does not
store the numbers as section identifiers. Most sections are C++ vectors in a
fixed order. Each vector starts with a `u32` record count.

The information on this page has four levels:

| Level | Meaning |
| --- | --- |
| **Wire** | The game reader and writer confirm the type and order. |
| **Parser** | The effects text parser confirms which command writes the field. |
| **Runtime** | Game code confirms the field use. |
| **Unknown** | The file stores the field. We do not know its purpose. |

Do not assign a meaning to an unknown field only because one Maxis resource
has a constant value in that field.

When a table gives only a text option, we confirmed only the parser mapping.
The option name does not prove the runtime behavior.

### Basic data types

All numeric values use little-endian byte order.

| Name | Size | Description |
| --- | ---: | --- |
| `u8` | 1 byte | Unsigned integer. |
| `u16` | 2 bytes | Unsigned integer. |
| `u32` | 4 bytes | Unsigned integer. |
| `f32` | 4 bytes | IEEE-754 single-precision float. |
| `bitset<N>` | 4 bytes | A `u32` stores the bits. The record uses the low `N` bits. Preserve all bits. |
| `Vec2` | 8 bytes | Two `f32` values. |
| `Vec3` | 12 bytes | Three `f32` values. |
| `Bounds3` | 24 bytes | Two `Vec3` values: minimum and maximum. |
| `string` | Variable | A `u32` gives the byte count. The string bytes follow it. The wire has no terminator. |
| `vector<T>` | Variable | A `u32` count, followed by that number of `T` records. |

EFFDIR strings are byte strings. The stream operator does not convert the
character encoding. ASCII text is safe. A tool must preserve unchanged bytes.
UTF-8 is a display and editing policy, not a proven rule of the file format.

The word `marker` on this page means a stored `u16`. Some markers separate
top-level groups. Some markers are at the start of a component record. A
marker is not a section terminator unless this page explicitly says that it
is a terminator.

### Top-level order

| Old section | Actual collection or field | Prefix or separator |
| ---: | --- | --- |
| Header | Version | Two `u16` values |
| 1 | Particle descriptions | `u32 count` |
| - | Particle/decal marker | `u16`, writer value `1` |
| 2 | Decal descriptions | `u32 count` |
| - | Decal/shake marker | `u16`, writer value `0` |
| 3 | Shake descriptions | `u32 count` |
| - | Shake/light marker | `u16`, writer value `0` |
| 4 | Light descriptions | `u32 count` |
| 5 | Brush descriptions | `u32 count` |
| 6 | Attractor descriptions | `u32 count` |
| 7 | Scrubber descriptions | `u32 count` |
| 8 | Sequence descriptions | `u32 count` |
| 9 | Sound descriptions | `u32 count` |
| 10 | Camera descriptions | `u32 count` |
| - | Component/dynamic-particle marker | `u16`, writer value `1` |
| 11 | Dynamic-particle descriptions | `u32 count`; only in major version 4 |
| - | Dynamic-particle/effect marker | `u16`, writer value `2` |
| 12 | Effect descriptions | `u32 count` |
| 13 | Effect-name map | No count; terminated by a special pair |
| 13.5 | Optional fixed metadata | `u8 present` and an optional fixed payload |
| 14 | Effect-key map | `u32 count` |
| - | Key-map/message-trigger marker | `u16`, writer value `0` |
| 15 | Message triggers | `u32 count` |

## Header

The header gives the resource version.

| Order | Type | Property | Description |
| ---: | --- | --- | --- |
| 1 | `u16` | Major version | The game reader accepts `3` or `4`. Major version 3 has no Section 11. |
| 2 | `u16` | Minor version | Minor version `1` selects an older Section 12 record. The current writer emits `2`. |

SimCity 4 uses version `3.1`. Rush Hour and Deluxe use version `4.2`. A tool
must keep the original version unless the user explicitly converts the
resource.

The version 1 particle reader has the same known wire order as the current
particle reader. The version 1 effect reader is shorter. See Section 12.

## Section 1 - Particle Descriptions

The old name for this section was "Terrain Independent FSHs and S3Ds." The
actual record is `cSC4ParticlesDescription`. It controls sprite particles,
model particles, emission, motion, collision, and particle child effects.

Section 1 starts with a `u32` record count. Each record has the following
fields in the exact wire order.

### Particle records: direct command assignments

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `bitset<32>` | `flags_0` | Main particle option flags. See Behavior 1 Bits. |
| 2 | `bitset<8>` | `flags_1` | Extra collision flags. See Behavior 2 Bits. |
| 3 | `bitset<11>` | `flags_2` | Model, alignment, warp, and source flags. See Behavior 3 Bits. |
| 4 | `Vec2` | `life` | Minimum and maximum particle life. |
| 5 | `f32` | `emit_loop_interval` | Interval for emission `loop` or `single`. |
| 6 | `u32` | `emit_loop_count` | Loop count. `single` writes `1`. |
| 7 | `f32` | `preroll` | Value from the particle `life -preroll` option. We did not confirm its runtime effect. |
| 8 | `Vec2` | `emit_delay` | Minimum and maximum emission delay. |
| 9 | `Vec2` | `emit_trigger` | Minimum and maximum trigger or retrigger value. |
| 10 | `Bounds3` | `emit_velocity_bounds` | Minimum and maximum initial velocity vector. |
| 11 | `Vec2` | `emit_speed` | Minimum and maximum initial speed. |
| 12 | `Bounds3` | `source_bounds` | Source region for point, square, cube, box, and related source modes. |
| 13 | `f32` | `size_vary` | Random size variation. |
| 14 | `f32` | `aspect_vary` | Random aspect variation. |
| 15 | `f32` | `rotate_vary` | Random rotation variation. |
| 16 | `f32` | `rotate_offset` | Initial rotation offset. |
| 17 | `f32` | `alpha_vary` | Random alpha variation. |
| 18 | `Vec3` | `color_vary` | Random variation of the three color components. |
| 19 | `vector<f32>` | `emit_curve` | Shared storage for `emit`, `maintain`, or `inject`. The active flags select the mode. |
| 20 | `vector<Vec3>` | `color_curve` | Particle color samples over life. |
| 21 | `vector<f32>` | `alpha_curve` | Particle alpha samples over life. |
| 22 | `vector<f32>` | `size_curve` | Particle size samples over life. The text parser multiplies input values by `50`. |
| 23 | `vector<f32>` | `aspect_curve` | Particle aspect samples over life. |
| 24 | `vector<f32>` | `rotate_curve` | Particle rotation samples over life. |
| 25 | `u32` | `resource_key` | Texture or model resource identifier. Both modes share this field. |
| 26 | `u8` | `draw_mode` | One-byte particle mode. Model parsing writes `3`. We do not know all values or the runtime purpose. `draw_mode` is an editor label. |
| 27 | `u8` | `alignment_mode` | Particle alignment enum. |
| 28 | `f32` | `sort_offset` | Draw sort offset for texture or model particles. |
| 29 | `f32` | `stretch` | Travel-direction stretch divisor. Runtime code consumes this value. |
| 30 | `Vec3` | `force` | Accumulated gravity and wind force. |
| 31 | `f32` | `global_wind` | Global wind contribution. |
| 32 | `f32` | `bomb` | Scalar from the force `-bomb` option. We did not confirm its full runtime effect. |
| 33 | `Vec3` | `bomb_direction` | Vector from the force `-bomb` option. We did not confirm its full runtime effect. |
| 34 | `f32` | `drag` | Motion drag. |
| 35 | `f32` | `screw` | Screw or spiral force. |
| 36 | `vector<Wiggle>` | `wiggles` | Wiggle and wiggle-direction operations. See the nested-record table. |
| 37 | `f32` | `uv_scale` | Scalar from the warp `uv` option. |
| 38 | `Vec2` | `uv_range` | Two values from the warp `uv` option. |
| 39 | `Vec3` | `alpha_warp_direction` | Direction for alpha warp. |
| 40 | `vector<f32>` | `alpha_warp_curve` | Alpha-warp curve samples. |
| 41 | `f32` | `bounce` | Collision bounce. The parser default is `0.3`. |
| 42 | `Vec2` | `terrain_repel` | First two `terrainRepel` values. |
| 43 | `f32` | `scout` | `terrainRepel scout` value. |
| 44 | `f32` | `vertical` | `terrainRepel vertical` value. |
| 45 | `f32` | `kill_height` | `terrainRepel killHeight` value. |
| 46 | `f32` | `collision_effect_or_death` | Shared storage for collision `effect` and `death`. These are not independent properties. |
| 47 | `f32` | `death_by_water` | Collision `deathByWater` value. |
| 48 | `Vec2` | `height_range` | Shared minimum and maximum range for `belowHeight`, `aboveHeight`, and `heightRange`. |
| 49 | `string` | `terrain_name` | **Unknown.** The game reader confirms the wire string. We did not find a parser setter or runtime reader. The name is an editor label. |
| 50 | `u16` | `value_164` | **Unknown.** We did not find a parser setter or runtime reader. Preserve this field. |
| 51 | `u16` | `value_166` | **Unknown.** We did not find a parser setter or runtime reader. The constructor sets `1`. |
| 52 | `f32` | `value_168` | **Unknown.** We did not find a parser setter or runtime reader. The constructor sets `1.0`. |
| 53 | `Vec2` | `random_walk_delay` | Minimum and maximum random-walk delay. |
| 54 | `Vec2` | `random_walk_strength` | Minimum and maximum random-walk strength. |
| 55 | `Vec2` | `random_walk_turn` | Minimum and maximum random-walk turn value. |
| 56 | `Vec3` | `prefer_direction` | Preferred random-walk direction. This field does not set `wait` or `preferSea`. |
| 57 | `f32` | `alignment_damp` | Alignment damping. |
| 58 | `Vec2` | `bank_range` | Alignment `bank` or `windBank` range. |
| 59 | `vector<f32>` | `attractor_curve` | Shared curve for attractor and automata force options. |
| 60 | `f32` | `attractor_strength` | Shared strength or rate for attractor and automata force options. The exact role depends on the option. |
| 61 | `u32` | `automata_id` | Automaton occupant or type identifier used by the force runtime. |
| 62 | `vector<TractorPoint>` | `tractor_points` | Points for `tractor` or `tractorRel`. See the nested-record table. |
| 63 | `f32` | `tractor_reset_speed` | Reset or catch-up speed limit. Runtime uses it when a particle moves too far from the path. |
| 64 | `vector<TimedEffect>` | `timed_effects` | Names and times of child effects that start during particle life. |
| 65 | `f32` | `model_speed` | **Unknown.** This field is before the model-speed field. We did not find an independent parser or runtime use. |
| 66 | `f32` | `model_speed_static` | Shared storage for text options `modelSpeed` and `modelSpeedStatic`. Preserve the preceding field as a separate wire value. |
| 67 | `vector<u32>` | `model_keys` | Resource identifiers for random model selection. |
| 68 | `f32` | `explosion` | Scalar from the force `explosion` option. |
| 69 | `f32` | `explosion_front_secondary` | Secondary scalar from `explosionFront`. |
| 70 | `vector<f32>` | `explosion_curve` | Explosion curve samples. |
| 71 | `f32` | `explosion_front` | Main `explosionFront` value. |

Nested records have these fixed layouts:

| Record | Wire layout | Description |
| --- | --- | --- |
| `Wiggle` | `f32`, `Vec3`, `Vec3` | One 28-byte warp record. `wiggle` and `wiggleDir` fill the fields differently. Do not give one fixed meaning to all components. |
| `TractorPoint` | `Vec3 position`, `Vec3 tangent`, `f32 start_time`, `f32 end_time` | One 32-byte tractor path record. Runtime code uses Hermite interpolation for position and velocity. |
| `TimedEffect` | `string effect_name`, `f32 time` | Starts the named child effect at the stored time. |

Curve vectors store sample values. The wire data does not store a time value
for each sample. Runtime code samples several curves with normalized particle
life. If the table does not give a unit, we do not know the exact unit.

### Behavior 1 Bits (`flags_0`)

Bit numbers in this page start at zero.

| Bit | Text option or runtime use |
| ---: | --- |
| 0 | `light` draw option |
| 1 | `emit` or `inject`; shared mode bit |
| 2 | `maintain` |
| 3 | emission `sustain` |
| 4 | `noCull` draw option |
| 5 | emission `base` |
| 6 | source `model` |
| 7 | source `modelBase` |
| 8 | collision command is present |
| 9 | collision `sticky` |
| 10 | `terrainRepel` is present |
| 11 | collision or source `killOutsideCity`; shared bit |
| 12 | source `city` |
| 13 | source `cityWindySide`; also sets bit 12 |
| 14 | source `pinToTerrain` |
| 15 | source `pinToWater` |
| 16 | a source height or water filter is present |
| 17 | source `seaOnly`; also uses bit 16 |
| 18 | source `lakeOnly`; also uses bit 16 |
| 19 | emission `scale` |
| 20 | emission `areaScale` |
| 21 | emission `volumeScale` |
| 22 | source `scaleParticles` |
| 23 | `randomWalk` is present |
| 24 | random-walk `wait` |
| 25 | random-walk `preferSea` |
| 26 | force `alphaAttractor` |
| 27 | force `motherDuck` |
| 28 | force `tractor` or `tractorRel` |
| 29 | texture `hflip` |
| 30 | texture `vflip` |
| 31 | a timed child effect is present |

### Behavior 2 Bits (`flags_1`)

| Bit | Text option or runtime use |
| ---: | --- |
| 0 | collision `destroyBuildings` |
| 1 to 7 | **Unknown.** We did not find a parser setter or runtime test in the shipped builds. Preserve these bits. |

### Behavior 3 Bits (`flags_2`)

| Bit | Text option or runtime use |
| ---: | --- |
| 0 | a model command is present |
| 1 | model `fakePerspective` |
| 2 | model `applyLighting` |
| 3 | model `moveEntireSlave` |
| 4 | model `slaveApplyAlpha` or `applyAlpha`, and force `alphaAttractor`; shared bit |
| 5 | model `sustain` |
| 6 | model speed is present |
| 7 | alignment `windBank` |
| 8 | warp `wiggleVerts`, `uv`, or `alpha`; shared mode bit |
| 9 | source `resetIncoming` |
| 10 | model `noCullFaces` |

After all particle records, the file stores the `u16` particle/decal marker.
The current game writer writes `1`.

## Section 2 - Decal Descriptions

The old name for this section was "Terrain Dependent FSHs." The actual
record is `cSC4DecalDescription`. It draws an animated terrain or water
overlay.

### Decal descriptor

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `bitset<7>` | `flags` | Decal modes. See the flag table. |
| 2 | `u32` | `texture_key` | Texture resource identifier. Runtime code creates the overlay from this value. |
| 3 | `u8` | `draw_mode` | Draw value that runtime passes to the overlay manager. We do not know all numeric values. |
| 4 | `u8` | `repeat_mode` | `1` loops. `2` stops at the end. `3` sustains at the end. The game reader changes a stored `0`. |
| 5 | `f32` | `life` | Decal life. Runtime code uses its reciprocal as the playback rate. |
| 6 | `vector<f32>` | `rotation` | Rotation samples over normalized life. |
| 7 | `vector<f32>` | `size` | Size samples over normalized life. |
| 8 | `vector<f32>` | `alpha` | Alpha samples over normalized life. |
| 9 | `vector<Vec3>` | `color` | Color samples over normalized life. |
| 10 | `vector<f32>` | `aspect` | Aspect samples over normalized life. |
| 11 | `f32` | `alpha_vary` | Random alpha variation. |
| 12 | `f32` | `size_vary` | Random size variation. |
| 13 | `f32` | `rotate_vary` | Random rotation variation. |
| 14 | `f32` | `texture_repeat` | Repeat-geometry size value used when flag bit 3 is set. |
| 15 | `Vec2` | `texture_offset` | Offset copied into overlay geometry. |

| Flag bit | Meaning |
| ---: | --- |
| 0 | **Unknown.** Core decal runtime code does not test this bit. |
| 1 | Use the lit overlay path. |
| 2 | Use the water overlay manager. |
| 3 | Use repeated geometry. |
| 4 | Use city-scale geometry. |
| 5 | Create ring geometry. |
| 6 | Use the static-overlay path. |

The reader has a compatibility rule. If the stored `repeat_mode` is `0`, the
game uses mode `2` and sets flag bit 6 in memory. A lossless editor must keep
the stored `0` and the original flags unless the user changes them.

After all decal records, the file stores the `u16` decal/shake marker. The
current game writer writes `0`.

## Section 3 - Screen Shake

This collection contains `cSC4ShakeDescription` records.

### Shake descriptor

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `f32` | `length` | Total shake length. Runtime code normalizes elapsed time by this value. |
| 2 | `f32` | `fade` | Stop-tail length. A zero value stops immediately. A nonzero value lets the final part of the amplitude curve run. |
| 3 | `vector<f32>` | `amplitude` | Amplitude samples over normalized time. |
| 4 | `vector<f32>` | `frequency` | Frequency samples over normalized time. |
| 5 | `f32` | `aspect` | Scales the two screen axes in opposite directions. |
| 6 | `u8` | `base_table` | `0` selects a fixed random two-axis table. `1` selects a sine table on one axis. We did not confirm other values. |

The text parser clamps `fade` to `length`. Runtime code reduces an epicentered
shake by distance and zoom. The shake event path does not use the Section 12
event float. We did not confirm the radius source.

After all shake records, the file stores the `u16` shake/light marker. The
current game writer writes `0`.

## Section 4 - Saturation and Lightness

This collection contains `cSC4LightDescription` records. A Section 12 event
can use one record as a screen flash or as a lighting tint.

### Light descriptor

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `vector<Vec3>` | `color` | Color samples over normalized time. |
| 2 | `vector<f32>` | `strength` | Strength samples over normalized time. A negative flash strength selects subtractive rendering. |
| 3 | `f32` | `length` | Total duration. Runtime code normalizes elapsed time by this value. |

The light record has no fade field. The text spelling `light length -fade`
writes to the shake work area because of a parser defect. That fade value is
not in the binary light record.

## Section 5 - Brush Descriptions

The old name was "Brush (Cursor) Exemplars (Terrain Modelling)." This
collection contains `cSC4BrushDescription` records. Each record starts with
its own `u16` marker. The current writer writes `0`.

### Component records

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record marker. Writer value `0`. We do not know its independent purpose. |
| 2 | `u32` | `key` | Resource identifier from brush `-name`. |
| 3 | `f32` | `rate` | Brush `-rate` value. The `-apply` form can also write this storage. |
| 4 | `f32` | `length` | Brush `-length` value. |
| 5 | `u8` | `mode` | Apply mode from `-apply`. We do not know all values. |
| 6 | `u32` | `zoom` | Stored zoom is the text zoom minus one. |
| 7 | `Vec2` | `strength` | Minimum and maximum brush strength. |
| 8 | `Vec2` | `width` | Minimum and maximum brush width. |
| 9 | `f32` | `level` | Brush `-level` value. |

## Section 6 - Attractor Descriptions

The old name was "LUA Occupant Groups, Generators, and Attractors." This
collection contains `cSC4AttractorDescription` records.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record marker. Writer value `0`. We do not know its independent purpose. |
| 2 | `string` | `name` | Name from `-name` or occupant group from `-group`. |
| 3 | `u8` | `selector` | `0` is the `-name` form. `1` is the `-group` form. We did not confirm other values. |

The selector is one byte. It is not a `u32`.

## Section 7 - Scrubber Descriptions

The old name was "Destructive Effect Properties." This collection contains
`cSC4ScrubberDescription` records. Scrubbers can demolish or burn objects,
send messages, change effect maps, and pause the simulation.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record layout marker. Writer value `1`. If nonzero, fields 17 and 18 are present. |
| 2 | `bitset<7>` | `flags` | Scrubber option flags. See the flag table. |
| 3 | `u32` | `value_10` | **Unknown.** We did not find a parser setter or runtime reader. |
| 4 | `u32` | `demolish` | Value from `-demolish`. |
| 5 | `u32` | `action` | Packed demolition action/effect value. `explode`, `createRubble`, `createBurntRubble`, and `demolishEffectID` share this field. We do not know all sub-bits. |
| 6 | `f32` | `min_size` | Minimum demolition size. |
| 7 | `f32` | `max_size` | Maximum demolition size. |
| 8 | `u32` | `burn` | Value from `-burn`. |
| 9 | `u32` | `message_1` | First `-message` argument. We confirmed the parser mapping. We do not know the full runtime purpose. |
| 10 | `u32` | `message_2` | Second `-message` argument. We confirmed the parser mapping. We do not know the full runtime purpose. |
| 11 | `u32` | `map_index` | Effect-map selector for `-blob` or `-rect`. The parser uses values `1` through `8`. |
| 12 | `f32` | `map_value` | Value added to the selected effect map. The constructor default is `16.0`. |
| 13 | `Vec2` | `map_half_extents` | Rectangle half-extents. |
| 14 | `f32` | `map_spread` | Rounded expansion or falloff count for map changes. |
| 15 | `f32` | `pause_duration` | Duration for a pause option. |
| 16 | - | Conditional tail | The next two fields exist only when `marker` is not zero. |
| 17 | `u32` | `toxic` | Value from `-toxic`. |
| 18 | `u32` | `extinguish_fire` | Value from `-extinguishFire`. |

| Flag bit | Meaning |
| ---: | --- |
| 0 | `noNetworks` |
| 1 | `noFlora` |
| 2 | `dezone` |
| 3 | `single` |
| 4 | `pauseSim` |
| 5 | `pauseSimHidden` |
| 6 | `pauseClock` |

The conditional fields occur at the end of the wire record. They do not occur
between `burn` and `message_1`, although their C++ object offsets are in that
area.

## Section 8 - Sequence Descriptions

The old name was "Randomized Picks." The actual record is
`cSC4SequenceDescription`. A sequence contains timed `wait` and `play` items.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record marker. Writer value `1`. We do not know its independent purpose. |
| 2 | `vector<SequenceItem>` | `items` | Ordered wait and play operations. |
| 3 | `bitset<3>` | `flags` | Bit 0 is `loop`; bit 1 is `noOverlap`; bit 2 is `hardStart`. |

Each `SequenceItem` is `Vec2 timing` followed by `string effect_name`. A wait
item has an empty effect name. A play item names an effect in the active
effects collection. The definition can come from this resource or another
loaded EFFDIR. The two timing components come from the text `wait` or `play`
command. Their complete independent meanings are not yet confirmed.

## Section 9 - Sound Descriptions

This collection contains `cSC4SoundDescription` records.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record marker. Writer value `0`. We do not know its independent purpose. |
| 2 | `bitset<1>` | `flags` | **Unknown.** We did not find a parser setter or runtime test for bit 0. |
| 3 | `u32` | `resource_key` | Sound resource identifier. Runtime code passes it to the sound system. |
| 4 | `f32` | `location_update_rate` | Stored inverse of text option `-locationUpdateRate`. The constructor default is `0.5`. |
| 5 | `f32` | `length` | Sound effect length. |

## Section 10 - Camera Descriptions

The old page called this section "Effective Radius?" The actual record is
`cSC4CameraDescription`.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `u16` | `marker` | Record marker. Writer value `0`. We do not know its independent purpose. |
| 2 | `bitset<4>` | `flags` | Bit 0 enables zoom, bit 1 enables rotation, bit 2 uses the target, and bit 3 uses the slave. Runtime code tests all four bits. |
| 3 | `u8` | `zoom` | Zero-based game zoom value. |
| 4 | `u8` | `rotation` | Rotation value passed to camera control. |
| 5 | `f32` | `attach_radius` | Radius used to attach or apply the camera effect. |

The Mac text parser has a defect. Its `rotation` option sets flag bit 1 but
writes the argument to the zoom byte. Runtime code reads the separate rotation
byte. A binary editor must keep the two bytes separate.

After all six component collections in Sections 5 through 10, the file stores
the `u16` component/dynamic-particle marker. The current writer writes `1`.

## Section 11 - Dynamic-Particle Descriptions

The old page called this section "UDI Collisions?" The actual record is
`cSC4DynamicParticleDescription`. This collection exists only when the major
version is `4`. A major version 3 file goes directly from the group marker to
the next marker and Section 12.

### Major-4 dynamic-particle descriptor

The wire order is not the C++ member-offset order. The resource identifiers
come before the six floats.

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `bitset<7>` | `flags` | **Unknown.** We did not find a parser setter or runtime test. All three standard Maxis records store zero. |
| 2 | `string` | `base_name` | Base particle effect name from `effectBase`. |
| 3 | `u32` | `model_key` | Model resource identifier. |
| 4 | `vector<u32>` | `model_keys` | Resource identifiers for multiple or random models. |
| 5 | `f32` | `mass` | Body mass. Runtime code stores its reciprocal. The constructor default is `1.0`. |
| 6 | `f32` | `value_14` | **Unknown.** We did not find a parser setter or runtime reader. |
| 7 | `f32` | `friction_min` | Minimum linear friction. |
| 8 | `f32` | `friction_max` | Maximum linear friction. |
| 9 | `f32` | `angular_friction` | Angular friction. |
| 10 | `f32` | `value_24` | **Unknown.** We did not find a parser setter or runtime reader. |

After this collection, the file stores the `u16` dynamic-particle/effect
marker. The current writer writes `2`.

## Section 12 - Effect Descriptions

The old name was "Main Script Index." This collection contains
`cSC4EffectDescription` records. Each record defines the components and
ancillary events of one effect. Section 13 gives the effect its external name.

### Effect records

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `bitset<9>` | `flags` | Top-level effect options. See the flag table. |
| 2 | `u32` | `priority` | Effect priority. |
| 3 | `vector<DescriptionRecord>` | `descriptions` | Particle, decal, brush, attractor, scrubber, sequence, sound, camera, dynamic-particle, and opaque runtime children. |
| 4 | `vector<EventRecord>` | `events` | Shake, flash, and tint events. |
| 5 | `string` | `chain_effect` | Target of `chainEffect`. We confirmed the parser and copy paths. We did not find a consumer in the main manager path. |
| 6 | `u32` | `start_message_1` | First `startMessage` argument. We do not know its full runtime purpose. Minor version 1 omits this field. |
| 7 | `u32` | `start_message_2` | Second `startMessage` argument. We do not know its full runtime purpose. Minor version 1 omits this field. |
| 8 | `u32` | `start_message_3` | Third `startMessage` argument. We do not know its full runtime purpose. Minor version 1 omits this field. |

| Flag bit | Text option |
| ---: | --- |
| 0 | `viewRelative` |
| 1 | `noAutoStop` |
| 2 | `hardStop` |
| 3 | `rigid` |
| 4 | `noPropagate` |
| 5 | `applyCursor` |
| 6 | `ignoreOrientation` |
| 7 | `noLODStop` |
| 8 | `manualRestart` |

Minor version 1 stops each effect record after `chain_effect`. It does not
store the three `start_message` values. We did not find a separate version 1
writer. A tool can preserve an unchanged version 1 resource. It must not add
the current tail to an old record.

### Effect child records

Each `DescriptionRecord` has this layout:

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `string` | `name` | Source child name. The effects collection resolves named records before runtime use. |
| 2 | `u8` | `component_type` | Selects the component collection. See Index Flags. |
| 3 | `bitset<2>` | `flags` | Bit 0 is `ignoreLength`. Bit 1 is `systemSequence`. |
| 4 | `3 x Vec3` | `transform.matrix` | Row-major 3 by 3 rotation matrix. |
| 5 | `Vec3` | `transform.translation` | Child offset. |
| 6 | `f32` | `transform.scale` | Uniform child scale. |
| 7 | `u32` | `transform.revision` | Transform revision. The game object keeps the low byte, but the wire field is four bytes. |
| 8 | `u8` | `lod` | Value from the child `-lod` option. Parser default `1`. We did not confirm its full runtime purpose. |
| 9 | `u8` | `lod_range` | Value from the child `-lodRange` option. Parser default `6`. We did not confirm its full runtime purpose. |
| 10 | `u16` | `shell_count` | Number of particle shells. Runtime code creates this many instances. Default `1`. |
| 11 | `u16` | `shell_offset` | Per-shell geometry offset passed to the child. Default `16`. |
| 12 | `f32` | `emit_scale_min` | Minimum emission scale. |
| 13 | `f32` | `emit_scale_max` | Maximum emission scale. |
| 14 | `f32` | `size_scale_min` | Minimum size scale. |
| 15 | `f32` | `size_scale_max` | Maximum size scale. |
| 16 | `u16` | `selection_group` | Enclosing `select` group. Zero means no group. |
| 17 | `u16` | `probability` | Encoded `prob` value for selection. |
| 18 | `u32` | `description_index` | Resolved index in the selected component collection. `0xFFFFFFFF` means unresolved during parsing. |

The transform revision is a `u32`, not a `u8`. If a tool reads only one byte,
it shifts all later fields and corrupts the record.

Each `EventRecord` has this layout:

| Order | Type | Property | Known use |
| ---: | --- | --- | --- |
| 1 | `bitset<4>` | `flags` | Selects shake, epicenter, flash, or tint behavior. |
| 2 | `string` | `name` | Source shake or light description name. |
| 3 | `f32` | `event_float` | For an epicentered flash, this is the falloff radius. The parser default is `1000.0`. The traced shake and tint paths do not use this float. |
| 4 | `u32` | `description_index` | Direct index into Section 3 for a shake, or Section 4 for a flash or tint. |

| Event bit | Meaning |
| ---: | --- |
| 0 | Dispatch a Section 3 shake. |
| 1 | Use the effect origin as an epicenter. |
| 2 | Dispatch a Section 4 light as a screen flash. |
| 3 | Dispatch a Section 4 light as a lighting tint. |

## Section 13 - Main Effect Directory

Section 13 is the effect-name map. It does not start with a record count. It
contains repeated pairs:

| Order | Type | Property | Description |
| ---: | --- | --- | --- |
| 1 | `string` | `effect_name` | External effect name. Name-based references use this value. |
| 2 | `u32` | `effect_index` | Zero-based index into Section 12. |

The standard Maxis resource has one name-map target for each Section 12
record. Each Section 12 index occurs one time. The `chain_effect` field in
Section 12 is not the name of its own effect.

Section 13 ends with this pair:

```text
string "end"
u32    0xFFFFFFFF
```

This pair is the real terminator. There is no `u16` end marker here.

### 13.5 area

The old page listed one byte, one `DWORD`, and nine floats. The complete
optional record is:

| Order | Type | Property | Description |
| ---: | --- | --- | --- |
| 1 | `u8` | `present` | If zero, the record ends here. If nonzero, the remaining fields are present. |
| 2 | `u16` | `marker` | **Unknown.** Preserve it. The old page omitted this field. |
| 3 | `u32` | `unknown` | **Unknown.** This is not a vector count. Preserve it. |
| 4 | `9 x f32` | `values` | **Unknown.** This is a fixed group of nine floats. It has no stored count. |

We do not know the purpose of this metadata. Do not label the nine values
without more runtime evidence.

## Section 14 - Effect-Key Map

The old name was "Tools FX Linking?" The text commands `effectID` and
`effectGroup` create this two-part map.

| Order | Type | Property | Description |
| ---: | --- | --- | --- |
| 1 | `u32` | Record count | Number of records. |
| 2 | `string` | `effect_name` | Effect name. It can resolve through Section 13 of this resource or another loaded EFFDIR. |
| 3 | `u32` | `group_id` | Effect group identifier. |
| 4 | `u32` | `instance_id` | Instance in the group. |

The group and instance values are not a DBPF TGI for the EFFDIR resource.
Together, they are the effect key created by `effectID` or `effectGroup`.
Multiple related effects can share a group and use different instance values.
This page does not identify all runtime consumers.

After the records, the file stores the `u16` key-map/message-trigger marker.
The current writer writes `0`. The marker is two bytes, not a reserved `u32`.

## Section 15 - Message Triggers

The old name was "Class ID Calls." This collection contains
`cSC4MessageTriggerDescription` records.

| Order | Type | Property | Description |
| ---: | --- | --- | --- |
| 1 | `u32` | Record count | Number of message triggers. |
| 2 | `u32` | `message_id` | Game message identifier. |
| 3 | `string` | `effect_name` | Effect to start. The active effects collection resolves the name. The definition can come from this resource or another loaded EFFDIR. |

The wire order inside each record is message identifier first and string
second.

## Index Flags

The old Index Flags table mixed component types with old section numbers.
We confirmed this mapping for the `component_type` byte in a Section 12
`DescriptionRecord`:

| Value | Component collection | Old section |
| ---: | --- | ---: |
| `0` | Particle description | 1 |
| `1` | Decal description | 2 |
| `2` | Opaque runtime component | None. It is not a collection index. |
| `3` | Brush description | 5 |
| `4` | Attractor description | 6 |
| `5` | Scrubber description | 7 |
| `6` | Sequence description | 8 |
| `7` | Sound description | 9 |
| `8` | Camera description | 10 |
| `16` | Dynamic-particle description | 11 |

We do not know values that are not in this table. Preserve the byte and the
associated index. Do not redirect an unknown value to a guessed section.

## Editing Requirements

The format contains variable-length strings and vectors. A change can move
all later fields. Do not search for a byte pattern to edit the resource.

A tool that follows this specification must:

1. Decompress QFS/RefPack data at the DBPF layer before it parses EFFDIR.
2. Use bounded reads for all counts and strings.
3. Keep unknown fields, unknown bits, markers, string bytes, and trailing
   bytes when the user does not change them.
4. Use the major version to decide if Section 11 is present.
5. Use the minor version to select the shorter version 1 Section 12 record.
6. Resolve Section 13 targets as indices into Section 12.
7. Resolve Section 12 child indices with the component-type table.
8. Report unresolved or out-of-range references before it writes the file.
9. Keep DBPF compression separate from EFFDIR serialization.

The EFFDIR Editor in this repository implements these rules. Its model and
tests also record corrections that came from round-trip tests with the
standard `SimCity_1.dat` resource.
