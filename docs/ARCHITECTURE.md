# Native architecture

This document describes the complete-house engine and resource layout. Current
build evidence and remaining validation limits are recorded in
[window/door validation](validation/window-door.md),
[draw-order validation](validation/draw-order.md) and
[full-game validation](validation/full-game.md). Earlier rendering decisions
remain documented in the [performance follow-up](validation/performance-followup.md),
[initial review](validation/performance-review.md) and
[reported-bugs validation](validation/reported-bugs.md).

## CPU and timing

The 68000 boots the cartridge, detects PAL/NTSC and publishes coherent controller
snapshots each VBlank. It also services cartridge mapping, SRAM and YM2612/PSG
music from its own RAM. The master SH2 executes the 25 Hz simulation, LIFE/track,
active objects, animation, collision, inventory and camera selection; it
transforms/sorts geometry and presents completed frames. Both SH2s rasterize
disjoint whole-row bands through a cache-through eight-entry command ring.
Ordinary jobs start with a split at row 100, adapting within rows 20–180;
contact jobs separately adapt the master's share from 10% to 90% of their
repair rectangle. The slave also owns autonomous PWM
sample mixing; audio interrupts remain available during rendering.

The runtime is freestanding C++17 with no heap, OS, filesystem, SDL, STL, RTTI
or exceptions. Shared-RAM completion/queue waits and COMM/VDP waits use compact
SH2 loops with an address-register write in the branch delay slot. This keeps
PicoDrive's polling detector from incorrectly sleeping on a completed exchange
without padded NOP loops. Payload fences and uncached aliases are retained.
A VBlank phase accumulator
catches up simulation independently of completed draws. The approved animation
clock remains 60 Hz with fractional phase units of 1/1500 second: each logic
update consumes 60 units and each original key lasts `duration * 25` units.
Walk/run displacement and interpolation carry their remainder across keys.
Pause, inventory, pickups, books and cinematic picture/movie holds stop the
world clock. Presentation input consumes controller edges without advancing it.

Both SH2s initialize their CPU-local free-running timer at phi/128 in RELEASE
as well as PROFILE. Ordinary jobs measure master submission/drawing time minus
queue stalls and slave rasterization time; contact jobs measure both tile
passes. A 25% imbalance and three agreeing samples move the split by four rows
(four units out of 200 for contacts). Tiny jobs retain the split.
Each BEGIN/CONTACT payload freezes ownership until END; masks and shared scratch
reuse still follow that fence. Timer reads retry across high-byte rollover.
The timer is polled and enables no timer interrupts; PWM stays interruptible.

Background repairs of at least eight rows and 512 words dispatch the bottom
half of the damaged rectangle to the slave while the master copies the top.
The master can then transform/sort the next model or item preview while the
copy remains pending. The slave reads the existing RAM image through its
uncached alias; no second image or copy buffer is allocated. A separate restore
token fences framebuffer writes/readback, RAM composition and presentation.
Small repairs and RAM targets retain synchronous copying. These paths are
shared by gameplay, startup/death/ending and inventory/pickup screens.

## Complete world and script state

All eight original floors are available: 58 room records and 144 camera views.
Two auxiliary rooms have no original camera; their metadata remains available
for collision/script links and no synthetic view is imported. Floors 2–6 are ordinary
gameplay resources. Floor 7 also supplies the original arrival. There is no
floor-1 staging cutoff or special death-only access to floor 6.

The bank supplies 292 original 26-word object records, 207 variables, 45 CVars,
563 LIFE scripts and 45 tracks. Found-item metadata stays in the world record;
an active slot owns body, flags, position, angles, LIFE, animation and track
state until deactivation writes it back. Activation retains the original
floor/life-mode/visibility rules and object order. Room visibility is prepared
once per refresh, including adjacent rooms. A capacity error stops with a
diagnostic rather than overwriting memory.

The active pool has the original 50 slots. The imported bodies use at most 379
vertices and 28 groups, within the 384-vertex/384-primitive workspaces. Each
`GroupState` stores its type and three deltas as signed 16-bit words: eight
bytes rather than the previous 16-byte representation. Both current and
previous bone poses retain the original resource bounds; this reduces per-actor
pose memory enough to expand the pool without a second geometry buffer.
Renderer membership, dynamic/static selection and contact groups use 64-bit
masks so slots 32–49 remain distinct. Resource and capacity evidence is in the
full-game validation report.

LIFE operands and track data use big-endian native words. The interpreter checks
cursor/branch/variable/object bounds, caps recursion at eight and caps each
invocation at 2048 instructions. Expressions on targeted commands preserve
the original caller. Unsupported commands raise a LIFE/word diagnostic. The
original scripts implement item actions, pickups, reading, weapons, ammunition,
enemies, puzzles, room/floor transitions, the Pregzt ritual and escape.
Follow tracks use the original walking speed and movement timing.

`LIGHT` changes a separate darkness flag; it preserves `C_VAR 13`, the original
lantern source object. Corridor/library scripts toggle full illumination.
Underground LIFE selects either the held lantern/player or a dropped lantern
as its local source. After Pregzt dies, the original killed-sorcerer guard stops
further darkness changes. `END_SEQUENCE` requests the ending movie and continues
its LIFE command tail, which installs escape state. `GAME_OVER` and
`WAIT_GAME_OVER` terminate their sequence without manufacturing a death flag;
original death scripts set `DEAD_PERSO` themselves.

The inherited source leaves `RND_FREQ`, `SHAKING` and `WATER` effects as cosmetic
stubs. `GET_HARD_CLIP` prepares clipping for primitive type 5 in FITD, whose own
drawing path is ignored; none of the imported AITD1 bodies uses that primitive.
It has no collision/progression effect in this port. These limits do not imply
full playthrough or original visual parity. SPECIAL effects use three bounded
slots of up to 30 points for evaporation, hit particles and smoke. Their
presentation RNG does not alter LIFE random choices.

## Startup, inventory and cinematics

Startup reproduces the original Infogrames model/logo animation, title, English
credits, start menu, character portraits, biographies and scripted arrival.
Arrival starts at floor 7, room 1, camera 3, target 286; LIFE/track visits floors
3, 2 and 1 before LIFE 539 ends. Completion or skipping initializes a fresh
gameplay world. `World::intro` identifies that presentation sequence; it no
longer grants access to otherwise blocked floors. Intro flags and picture
requests are transient and loading clears them explicitly.

Startup time uses 1/1500-second units from PAL/NTSC VBlank. Logo animation,
palette fades, credits and pictures use the independent presentation clock;
the arrival world remains at 25 Hz. The frog picture freezes world updates
for its original 20 presentation ticks. Credits/biographies decode paper once
and compose in the existing RAM background. Static fades update CRAM without
redrawing pixels. Original proportional glyphs write contiguous spans and
preserve source casing, copyright A9 and I-Motion FA glyph indices. Gameplay
and presentation text directory IDs share the same original payload. Startup
hides the FPS border; gameplay restores it.

The original inventory uses a 320×100 list and two 160×100 lower sections.
Compressed panels and labels compose on content changes directly into the
64,000-byte RAM background. `BackgroundComposition` restores the framebuffer
target and merges changed regions into both damage histories, avoiding
framebuffer readback. Preview animation restores damaged pixels, shares
geometry/face-sort scratch, and clips to the original item viewport. Fully
visible faces bypass clipping; disjoint faces are rejected. The 60 Hz orbit
clock uses region-adjusted VBlank time, with draws capped at 30 Hz. Closing
invalidates the scenery bake. No extra image, vertex or depth buffer is used.

Pickups use the original 240×120 panel, black surround, Leave/Take options and
rotating found-body model. Shared preview scratch preserves the 15000-unit
orbit, projection 300×298 and center (160,100). Loading a pending prompt restores
Take after the load pause closes. Pause menus capture the room once and compose
option changes in RAM. Reading retains original paper/book/notebook artwork,
illustrations, proportional text and page sounds. Information text uses one
unframed native overlay at (160,184), color 16, across gameplay and cinematics.

Death continues player/enemy LIFE and track state, including scripts 39,
555–558 and 554, the cemetery views and ITD_RESS:12. Picture/end holds retain
idle pixels and stop world updates. Skip/title return never writes SRAM.

The original ending movie has 32 frames. Frame zero is a compressed type-2
image; the other 31 frames are banked type-19 changed-span programs. Each
program patches the existing RAM background, with outstanding changes merged
into both framebuffer damage histories. Playback uses five 60 Hz presentation
ticks per frame and requires no second bitmap; exact DOS timing remains to be
compared. Finishing or skipping resumes
the original escape world after the ritual; the later completion hold returns
to the title. Ending state is presentation-only and is cleared on load.

## Cartridge banking

The SH2 direct cartridge window is 32 Mbit / 4 MiB. Larger ROMs require a
compatible cartridge mapper; this build uses extended SSF 512 KiB pages and
bounds physical ROM to 15 MiB (pages 0–29). Pages 30/31 are reserved for the
cartridge OS and SRAM. The asset directory starts at physical `0x20000`.
Fixed data and the BIOS-loaded SH2 module remain below 4 MiB; executable ROM
code stays below the asset origin. Banked images/movie deltas begin at
physical `0x400000`. Directory offsets remain relative to the asset origin.
The importer writes `bank-main.bin`, `bank-extra.bin` and the full logical
`bank.bin` for host tools; native linking places the BIOS module in the gap
before the extension.

All protected data avoids physical `0x80000–0xFFFFF`, the complete 512 KiB mapper
aperture. That includes camera/room metadata, models, animations, LIFE/track,
static drawing programs, font data, sound effects and music streams. Thus
world reads, slave audio and contact jobs never depend on the selected image
page. Every banked payload fits within one page.

Flag `0x8000` marks banked type-2 images and type-19 deltas. Decode/Blit ask the
68000 RAM supervisor to write `A130F3` when the requested page changes. It
briefly sets RV for the register write and restores its previous value before
acknowledging. SH2 reads use uncached `0x22080000`. Raw original backgrounds
also map through a scoped view while RAM holds baked scenery; camera binding
finishes first and actor/contact jobs fence before the scope ends.

Complete-game banks retain the selected page after image work. Selection is
cached, eliminating two supervisor exchanges when successive images share a
page. Older banks with fixed resources in the aperture are detected from their
directory and restore identity page 1 before world reads. Scoped mappings
restore asset pointers in either case. Mapping policy is shared by gameplay
cameras, UI images, startup/death images and ending deltas.

The system header is `SEGA SSF`, selecting extended mapping instead of the
linear 10M mode reported on Mega EverDrive Pro. The `.32x` extension and MARS
bootstrap/module remain intact. Before releasing the SH2s, the RAM-resident
68000 initializer resets banks 1–7, probes extended bank-0 remapping by
comparing 256 ROM bytes against bank 2, restores bank 0, and writes `0xC000`
to `A130F0` (protected control update, 32X mode, ROM writes disabled). Standard
SSF2 emulation ignores bank-0 remapping and retains conventional SRAM access.

On extended hardware, each SRAM word temporarily selects page 31 in bank 4.
The supervisor sets RV, uses `0x8000` for reads or `0xA000` for writes, accesses
the word at `0x200000 + journal offset`, restores bank 4/page 4 and `0xC000`,
then restores RV before acknowledging. This targets Mega EverDrive Pro's
word-wide SRAM at the start of page 31; older EverDrive layouts are not
validated. The retained image bank is untouched, and music pumping remains
suspended during save transactions. The header declares 128 KiB SRAM. No
serialization migration is introduced or required for this mapper change.

The [Krikzz extended SSF specification](https://krikzz.com/pub/support/mega-everdrive/x3x5x7/dev/extended_ssf-v2.txt)
documents the header/control protocol; the
[Pro FPGA source](https://github.com/krikzz/mega-ed-pub/blob/master/fpga/mapper/map_ssf/map_ssf.sv)
routes page 31 to SRAM. [Mapper validation](validation/ssf-mapper.md) separates
stock PicoDrive coverage, the extended-SRAM bus model and pending hardware tests.

The [Sega hardware manual](https://consolemods.org/wiki/images/e/e9/32X_Hardware_Manual_1994_Sega_text.pdf)
describes the direct window and arbitration. PicoDrive implements
[32X SSF2 reads](https://github.com/notaz/picodrive/blob/master/pico/32x/memory.c),
[mapper registers](https://github.com/notaz/picodrive/blob/master/pico/carthw/carthw.c)
and [mapper selection for ROMs larger than 4 MiB](https://github.com/notaz/picodrive/blob/master/pico/cart.c).
Emulator evidence does not validate physical RV arbitration. A flash cartridge
must provide compatible 32X mapper support and sufficient ROM storage.

## Rendering and static props

Packed-pixel video is 320×224 in both regions, with a 320×200 logical scene at
(0,12). Each framebuffer has a native line table and independent damage bounds.
Aligned longword copies/fills share four-store unrolled loops across solid
spans, background repairs/readback, panels and image decoding. Word leads/tails,
unaligned copy fallback and partial-pixel handling preserve exact boundaries.
Normal word/longword writes restore palette index zero correctly; transparent
and depth-tested pixels retain selective stores. FPS counts completed draws
against VBlank and requests a repaint only when its displayed value changes;
idle static presentation screens retain their pixels.

Original FITD group geometry, Q15 arithmetic, flat primitives, stable depth
order, projection and conditional foreground masks remain. World primitives
are rejected in full when any referenced vertex has camera Z <=100, matching
FITD's visibility rule. Ordinary drawing, prepared props and contact depth use
the same policy; crossing faces are not turned into new clipped polygons.
Type-2 eye points occupy one pixel; small type-3 spheres can also shrink to one
pixel. Back faces are culled. Material 2 uses fixed 50% screen-door transparency.

Gameplay, contact geometry, effects and 3D previews share paired signed
projection in `project.cpp`. During X division the CPU loads/multiplies Y;
during Y division it centers/clamps X. Conservative instruction counting plus
36/34 padding NOPs guarantees at least 39 cycles before either quotient read.
No other DIVU access can intervene; PWM interrupts preserve MACL and do not
use DIVU. World coordinates retain +/-4096 clamping, while effects/previews
retain unclamped coordinates and their existing near-plane checks. Isolated
edge, radius, reciprocal-depth and wide-gradient divisions retain their waits.

Translation/mask tests use each actor's floor and room. A stable world painter
sort orders models before their primitive sort. The original pair-dependent
distance heuristic supplies a preference; a stable bounded graph pass enforces
separated camera-depth intervals across the complete list. Compatible vertical
precedence keeps floor hatches below standing actors. X/Z separating planes
also constrain overlapping camera-depth ranges, including windows behind pushed
furniture. Contradictory X/Z preferences retain the preceding stable order.
Cyclic plane preferences are broken deterministically without dropping
separated-depth constraints.
Equal zero-thickness intervals retain stable ties. The graph uses 400 bytes
temporary stack and executes from protected ROM; an already valid order skips
its selection pass. Interpenetrating geometry still needs local per-pixel depth.

One 64,000-byte RAM image holds scenery with static props baked in. All 144
camera backgrounds retain raw storage and aligned word copies, with banked
mapping shared across floors. View changes reset the bake and slot history;
same-camera room links retain it. Binding/copy happens once per rebuild. CRAM
reload follows actual palette changes. Movable props and deforming animations
remain dynamic. Missing-animation props and bodies with no deformable child
groups use the shared pose/mask quiet timer throughout the game, caching after
25 unchanged world ticks. Slot ownership
resets history when an actor slot is recycled.

A changed static painter order repairs the region enclosing intersecting props
and mask writes. Geometry/membership/camera changes keep full rebuilds. Colored
static drawing records coverage, including black pixels, glass and mask
clipping, into an uncached 8000-byte bitmap shared by the row-owning SH2s. This
reuses contact/face-sort scratch after face indices move to a local array.
Bitmap runs form a bounded 3072-span cache without a second draw or framebuffer
scan. Each cached span is `(u16 pixel start, u16 length)`; exhausted pools fall
back to regular model drawing. Baking copies only changed static rectangles.
Foreground replay copies cached colored spans and reapplies the actor's original
architectural masks, including background erasures absent from its silhouette.
Both operations are clipped to the overwritten region. A regular full-draw
fallback expands that region so subsequent cached props repair all its writes.

Combat/LIFE bounds share separate gameplay geometry scratch. Rendering shares
a union between ordinary vertices and compact contact vertices. Physical
contacts resolve reciprocal depth per pixel in 64×64 tiles; the 8 KiB tile
reuses 6 KiB face-sort scratch and adds 2 KiB. Nearby character/prop overlaps
activate correction in idle poses as well as Search/Push. Initial selection
excludes flat floor patches. Screen-overlapping models between the first and
last selected painter ranks join the same group, including foundable items;
only later models replay afterward. Full foreground draws expand the repair
footprint, preserving untouched pixels beyond the original contact area.
Groups remain bounded to 768 vertices; exceeding that limit retains painter
order rather than allocating a larger buffer.
Prepared primitives/gradients share idle gameplay scratch. Larger jobs use
disjoint SH2 bands and two 64×32 halves of the depth workspace, with explicit
CONTACT/END fences. Oversized groups or models with near-rejected vertices use
the fallback, which retains valid primitives. Original camera masks and unrelated foreground ordering survive
contact repair. Audio interrupts remain available.

Dark rooms apply a bounded lamp mask after normal scene drawing. LIFE selects
its source; the renderer projects that source's current collision center
through the active camera, and requires it in the current draw list. A prepared
ellipse table avoids per-row division/square roots. Mask writes cover only
restored/drawn damage; each physical buffer retains black pixels outside the
light and restores the union of its previous and current lit footprints.
Lighting changes request a full restore, while ordinary lamp motion preserves
partial repairs. This adds no bitmap and does not alter simulation clocks.
The light footprint is this port's rendering implementation; original visual
parity still needs playthrough comparison.

## Asset bank version 2

Header: `A32X`, u32 version/count/size. Four-byte-aligned big-endian directory
entries contain u32 offset/packed size/unpacked size and u16 type/flags. Codec
flags are 0 raw, 1 RLE, 2 raw LZ4, and 3/4 type-13 raw width/height headers
followed by RLE/LZ4 pixels; `0x8000` combines with the codec for banked payloads.
The shared LZ4 decoder accelerates offset-one constant runs while preserving
zero pixels, padding and overlapping matches. Framebuffer decoding uses word
writes and requires no scratch bitmap.

The bank has 2316 asset IDs. Existing 2053 IDs and the imported-game save
fingerprint `0x0eebc721` remain unchanged; new rooms/views and the ending are
appended. Both 272-body/305-animation banks, all LIFE/track, original text,
21 English books, startup/UI/death resources, 101 effects and eight music tracks
remain available. Models keep a 36-byte header and a u32 primitive-offset table;
primitives are compact `(u8 type,count,color,material; u16 size; indices[])`.
Original proportional text preserves glyph bytes rather than forcing uppercase.
UI panels precompose ITD_RESS:4 rails/corners/plaque; runtime restores raw or
compressed pixels through the same RAM composition/damage paths.

Type-14 fixed-prop programs contain a u32 count and sorted `(view, pose key,
program offset)` records, where view is `(floor << 8) | camera`. Pose FNV-1a
includes model identity, floor/room, position and angles; skeleton-free geometry
is required. Programs store screen bounds and literal `(start,length,color)`
spans captured with two sentinel backgrounds using the native integer renderer.
They cover eligible poses throughout the house, subject to the fixed-ROM
budget. Current collision bounds apply architectural masks on replay.
Missing/moved/rotating/skeletal poses use regular rendering.

Static keys hash mask activation rather than raw collision coordinates;
painter order remains in the scene key. Group-zero animation is excluded
because actor angles replace it in geometry. Child states and real geometry
changes remain dependencies, preserving ordering without needless rebakes.

`assets/manifest.json` records input/bank hashes; `full_game_manifest.json`
records complete-floor coverage and appended resources. The importer reads
original installations without modifying them. Converted resources remain
separate from the engine license and are excluded from source archives/Git.

## Memory and diagnostics

The complete-game RELEASE ROM is 14,155,776 bytes (13.5 MiB). Fixed bank data
uses 3,964,720 bytes and the extension 9,932,868 bytes. The 85,076-byte BIOS
module ends at physical byte 4,180,868, leaving 13,436 bytes below the 4 MiB
direct-window limit. BSS uses 160,672 bytes; module/BSS/linker overhead total
245,752 bytes, ending at `0x0603BFF8`. The static margin below the reserved
stacks is 8 bytes. Camera setup, video initialization, scenery readback and
worker control/copy helpers execute from
protected ROM; hot raster loops remain in SDRAM. `build/bank-layout.json` is the authoritative
generated layout report for this build; later changes require fresh figures.

SH2 SDRAM remains 256 KiB. The master reserves 12 KiB and the slave 4 KiB at
its top; the linker rejects static allocations at or above `0x0603C000`.
Framebuffer RAM is separate. No additional image/depth buffers or heap are
introduced; the remaining static margin must be measured after changes.

COMM retains coherent input, sequence, region and heartbeat. `debug_state[32]`
preserves the initial timing/render words and exposes floor, room, menu,
LIFE/word/code fault, inventory/hand/prompt, actor peak, world ticks, action,
health, book, finish and camera target. PROFILE uses SH7604 FRC scopes;
RELEASE removes timer instrumentation. Diagnostics and host fixture helpers
remain outside the cartridge where applicable.

## Persistent saves

The RA header advertises 128 KiB SRAM at `0x200000–0x21FFFF`. SH2 transports
sequential bytes through blocking COMM commands serviced by the 68000, batching
two bytes per exchange. Conventional SRAM is enabled during a transaction;
extended SSF maps it only for each protected word access. Six u32
header words store magic AITD, schema, generation, length, FNV-1a checksum and
the original imported-game fingerprint. Two 64 KiB journal records alternate;
magic clears first and commits last, followed by readback. A damaged newest
record falls back to the older valid record.

New writes use S16/01 (`0x53313601`): 50 actor slots, signed 16-bit bone states
and a trailing darkness flag. Loading also accepts S14/01 (`0x53313401`): 24
slots and signed 32-bit bone states; remaining slots clear and darkness is
reconstructed from original saved room/script variables. The fingerprint and
original resource IDs remain stable. Older ROMs cannot read S16 records.
Migration preserves the valid old journal until a later normal save reuses it.
The expanded pool's worst-case record remains within the 65512-byte payload
limit; measured evidence belongs in the full-game validation report.

Loads validate length/schema/resource bounds in bounded scratch before applying
state, then rebuild pointers and renderer caches. Scheduling rebases after
SRAM operations so time spent saving cannot advance gameplay on Resume. No
heap or full-save RAM buffer is used. Compatibility checks compare every saved
world/actor/bone/effect field using isolated host SRAM; they never read or write
user battery files. Music restarts at its restored track; active sample voices
and exact audio playheads are presentation state.

## Autonomous audio

Type 15 stores u32 PCM count, i16 predictor, u8 IMA step index, one reserved
byte and low-nibble-first ADPCM. Two slave-owned voices mix at 8 kHz. A
cache-through eight-request ring carries sample/next/repeat state from the
master. PWM level-6 IRQ refills three samples per interrupt and preserves
ABI registers/PR/MACH/MACL. Voice updates briefly protect against the ISR;
the idle slave polls requests while rendering interrupts remain available.
IRQ disables after centered silence when voices finish. Sample headers come
from immutable protected bank data, independent of master-cached globals.

Type 16 stores driver duration/count followed by four-byte
`(delta ticks, port, register, value)` commands: ports 0/1 YM2612, 2 PSG,
3 wait and 4 end. The 68000 executes from RAM through its 1 MiB ROM window,
caches bank selection and advances rational `294/(5×refresh)` timing per
VBlank. It owns the Z80 bus with reset released, including controller reads.
COMM `0x5010–0x5014` handles selection/status/stop/fade. Music pauses while
SRAM is mapped and preserves queued LIFE transitions. FM two-operator patches
use algorithm 4 or additive 7 with unused operators muted. OPL multipliers
and pitch translate; envelopes, waveforms and percussion remain approximations.
CD narration is not implemented.

The importer shares identical type/flags/payload blocks. Source IDs and static
programs regenerate against the final bank layout without changing original
resource identities. Mapper image-page changes cannot replace audio payloads,
and neither rendering nor presentation changes the 25/60 Hz clocks.
