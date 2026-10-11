# Native architecture — revision 13

This document records the inherited architecture. For current code/RAM figures,
aligned asset reads, contact-depth arithmetic and the review of CPU allocation,
see the [performance follow-up](validation/performance-followup.md) and
[initial review](validation/performance-review.md).
The [reported-bugs changes](validation/reported-bugs.md) extend contact repair
to idle poses and moving doors/hatches and apply each actor's masks before depth.

Current additions: unchanged static geometry with a changed painter order uses
a partial repair enclosing intersecting props and mask writes. Geometry,
membership and camera changes keep full rebuilds. Contact primitives/gradients
are prepared in idle gameplay scratch; larger jobs use disjoint SH2 row bands
with two 64×32 halves of the existing depth buffer and an explicit CONTACT/END
fence. Near-clipped or oversized prepared groups retain the original depth path.
Audio interrupts remain available. The 68000 now caches its music-bank selection;
actor refresh caches room visibility per call. Detailed limits and current
memory figures are in the follow-up report; revision-specific numbers below
describe the inherited baseline.

## Startup and cartridge banking

The startup reproduces the original Infogrames model/logo animation, title,
English credits, main menu, character portraits, half-page biographies and
scripted arrival. The arrival starts at floor 7, room 1, camera 3, target 286;
its original LIFE/track sequence visits floors 3, 2 and 1 before LIFE 539 ends.
Only the required extra views are imported. `World::intro` permits those floors
during presentation; gameplay still stops beyond floors 0 and 1. Completion
and skipping initialize a fresh gameplay world. Intro flags and the temporary
frog picture are not serialized; loading clears them explicitly. Existing
asset IDs and save fingerprint `0x0eebc721` remain compatible.

Startup time uses 1/1500-second units from the PAL/NTSC VBlank counter. Logo
steps, palette fades and picture/credit holds use the original 60 Hz clock;
the arrival world uses the existing 25 Hz simulation. The frog picture freezes
world updates for its original 20 presentation ticks. The renderer reuses its
64,000-byte background, with no additional image buffer or heap. Intro camera
images copy once on changing views or rebuilding the scenery cache. Original
mask pixels come from a scoped raw ROM mapping while RAM holds baked scenery.
Settled intro doors without animation data use the same pose/mask hash as
scenery; scripted movement invalidates their bake until they settle again.
The arrival retains its original painter ordering and camera masks; gameplay
continues to use contact-depth repair. Cache rebuilds preserve intro fade levels.
Gameplay camera images and existing UI panels/sprites retain their raw paths.
Credits and biographies decode their paper once. Biography composition reuses
the hidden framebuffer to preserve the selected portrait, then caches the
combined RAM background. Static fades update CRAM without restoring pixels,
and hidden startup FPS statistics do not force draws. Original font glyphs
write contiguous horizontal spans. A separate text asset preserves original
casing and font glyph bytes, including copyright and I-Motion symbols. Gameplay
now uses the same original text/font; both directory IDs share one ROM payload.
The FPS border is hidden throughout presentation and restored in gameplay.

The current RELEASE ROM is **5,373,952 bytes (5.125 MiB)**, with 2,053 asset
IDs, a 3,911,420-byte fixed bank and 1,161,242 bytes of extra image data. The
83,108-byte BIOS module ends at physical byte 4,125,600, leaving 68,704 bytes
below the direct-window limit. Static SDRAM is 243,288 bytes: module 83,108,
BSS 160,176, and four bytes of linker overhead. It ends at `0x0603B658`, with
2,472 bytes before the existing stack reservation. Startup adds 32 bytes of
state; expanded world lookup tables move to fixed ROM to recover RAM. Figures
and checks for this build are recorded in
[menu feedback validation](validation/menu-feedback.md).

The original inventory has a 320×100 list and two 160×100 lower sections.
Compressed panels and proportional labels are composed on content changes,
directly into the existing 64,000-byte RAM background. `BackgroundComposition`
restores the framebuffer target and merges the changed region into both bank
histories, avoiding framebuffer readback. Preview animation restores
only damaged pixels, uses the existing geometry/face-sort scratch and clips
to the original item viewport. The stable merge sort is shared with gameplay;
fully visible preview faces bypass clipping and disjoint faces are rejected.
The 60 Hz orbit clock comes from region-adjusted VBlank time, with draws capped
at 30 Hz. The world remains paused. Closing invalidates the scenery bake so
the next draw restores the original room. No new image, vertex or depth buffer
is allocated. Cold presentation code/strings remain in fixed ROM.

Pickups use the original centered 240×120 panel, black surround, Leave/Take
choices and rotating found-body model. The same preview scratch uses the
original 15000-unit orbit, projection 300×298 and center (160,100). Loading a
pending prompt restores Take after the load pause menu closes. Pause menus
capture the room once and compose subsequent option changes in RAM; closing
invalidates the scenery bake. Information text shares one unframed native
overlay at (160,184), color 16, across gameplay, arrival and death.

Menu edges dispatch from coherent VBlank controller snapshots without
advancing the world. Simulation and cinematic scripts remain at 25 Hz;
presentation rotation remains 60 Hz. The shared LZ4 decoder fills offset-one
constant matches directly, preserving zero pixels, row padding and overlapping
matches. This applies to every compressed presentation image/panel path.

Death continues the existing player/enemy LIFE and track state, including
scripts 39, 555–558 and 554. Only DEAD_PERSO permits floor 6; normal playable
floor limits remain unchanged. Three banked cemetery cameras (0, 8, 13) and
ITD_RESS:12 complete the movie. Picture/end holds stop world updates and use
the existing presentation clock, with idle pixels retained. Death can return
or skip to the title without modifying SRAM. Loading explicitly resets the
presentation phase; the save schema and fingerprint remain unchanged.

The SH2 direct cartridge window is **32 Mbit / 4 MiB**, rather than 32 MiB.
Larger ROMs require a cartridge mapper. This build implements the SSF2 mapper
with 512 KiB pages and limits its physical ROM to 32 MiB. The asset directory
starts at physical `0x20000`; fixed resources follow, and cold presentation
images begin at physical `0x400000`. The BIOS module stays entirely below
4 MiB. All executable ROM code stays below the asset origin. The importer
generates `bank-main.bin`, `bank-extra.bin`, and the full logical `bank.bin` for
host tools; its zero-filled gap is occupied partly by the BIOS module in the
native ROM. Directory offsets remain relative to the fixed asset origin.

Flag `0x8000` marks banked type-2 image payloads. Decode/Blit ask the 68000 RAM
supervisor to set `A130F3`, temporarily mapping the source page into slot 1,
physical `0x80000–0xFFFFF`. The supervisor briefly sets RV for the mapper write
and restores its previous value before acknowledging. The SH2 decoder reads
through uncached `0x22080000`, then restores bank 1 on success or decode failure.
Raw intro originals can also remain mapped during `Game::DrawScene`. Camera
binding/decoding completes before this scope; all actor and contact jobs fence
before it ends. Only actors on the current intro floor are allowed. Original
asset pointers and bank 1 are restored before UI drawing or world updates.
Each image fits in one page. The importer and linked-layout checker protect
all intro camera/room metadata, models, animations and static rasters from
the aperture; old gameplay metadata in that slot is accessed after unmapping.
Code, all sound payloads and music streams avoid the aperture, so slave PWM and
the 68000 music reader keep their existing transport and timing.

Bank format version 2 remains in use. Codec flags are 0 for raw, 1 for RLE,
2 for a standard raw LZ4 block, and 3/4 for type-13 images with a raw four-byte
width/height header followed by RLE/LZ4 pixels. The banked bit combines with
the image codec. Framebuffer decompression uses word writes to preserve zero
pixels and supports overlapping LZ4 matches without a scratch bitmap.

The [Sega hardware manual](https://consolemods.org/wiki/images/e/e9/32X_Hardware_Manual_1994_Sega_text.pdf)
describes the direct window and mapper arbitration. PicoDrive implements
[32X SSF2 reads](https://github.com/notaz/picodrive/blob/master/pico/32x/memory.c),
[mapper registers](https://github.com/notaz/picodrive/blob/master/pico/carthw/carthw.c),
and [automatic mapper selection for ROMs larger than 4 MiB](https://github.com/notaz/picodrive/blob/master/pico/cart.c).
Emulator checks cannot validate RV arbitration on physical hardware; a physical
cartridge or flash cart must provide a compatible mapper. Use the focused
startup and bank-layout checks in DEVELOPMENT.md when changing this flow.

## CPU and timing

The 68000 boots the cartridge, detects PAL/NTSC and publishes coherent controller snapshots each VBlank. The master SH2 executes the 25 Hz simulation, LIFE/track, active objects, animation, collision, inventory and camera selection. It transforms and sorts geometry and presents completed frames. Shared-RAM wait reads are spaced by 24 NOPs to avoid a terminal-read polling-detector sleep in PicoDrive. Both SH2s rasterize: the master owns logical rows 0–99 and the slave owns 100–199, using the v6 cache-through eight-entry command ring.

The runtime is freestanding C++17 with no heap, OS, filesystem, SDL, STL, RTTI or exceptions. A VBlank phase accumulator catches up simulation ticks independently of rendering. The approved animation clock remains 60 Hz with fractional phase units of 1/1500 second: each logic update consumes 60 units and each original key lasts `duration * 25` units. Walk/run root displacement and pose interpolation carry remainder across keys. Pause, inventory, prompts and books stop the world clock.

## World and script state

The bank supplies 292 original 26-word object records, 207 variables and 45 CVars. Found-item metadata stays in its world record; an active slot owns body, flags, position, angles, LIFE, animation and track state until deactivation writes it back. The imported models use at most 379 vertices, so the single-model scratch bound is 384. The actor pool has 24 slots, each with a bone pose and collision bounds. Activation follows floor/life mode/room visibility and original object order. A capacity error stops with a diagnostic rather than overwriting memory.

LIFE operands and track data are big-endian native words. The interpreter checks cursor/branch/variable/object bounds, caps recursion at eight and caps each invocation at 2048 instructions. It preserves the original caller for expressions on targeted opcodes. Unsupported instructions raise an on-screen LIFE/word error. Sound and music playback remain deferred. SPECIAL now emits bounded presentation effects: death evaporation, hit particles and smoke. Three effect slots each hold at most 30 points, with their own presentation RNG; they do not alter LIFE random choices. Music state remains available to scripts.

The original scripts select action animations, offer/take/equip/read/reload/drop/throw items, schedule enemy arrivals, update health/ammunition and drive stair transitions. The console maps B+Up to run and C to inventory. The first loaded-floor boundary is deliberate: attempts to stage the camera target beyond floor 1 show END OF THIS BUILD.

## Rendering and static props

The packed-pixel VDP presents 320×224 in both regions, with a 320×200 logical scene at `(0,12)`. Each bank has a valid native line table and separate damage bounds. Word writes restore palette index zero correctly. The FPS overlay occupies the upper border and counts completed draws against VBlanks.

FPS sampling requests a repaint only when its displayed value or readiness
changes. Once the counter settles, idle pause, inventory, action and document
screens retain their pixels. Inventory/actions mark content dirty only on input
edges; the world remains paused while those menus are open.

Original FITD group geometry, Q15 arithmetic, flat primitives, stable depth order, camera projection, near clipping and conditional foreground masks remain in use. Type-2 eye points occupy one native pixel; small type-3 sphere eyes can shrink to one pixel instead of retaining a three-pixel minimum. Back-facing polygons are culled. Material 2 uses a fixed 50% screen-door pattern to show the scenery through glass. Actor translation/mask tests use the actor's own floor and room. A stable world-level painter sort orders multiple models before their own primitive sort. Vertically disjoint bounds use their camera-relative physical order before horizontal distance, keeping the attic hatch below the standing chest/player without broad height buckets.

One 64,000-byte RAM image stores the current background with static props baked in. Changed camera assets reset the bake and per-slot history; same-camera room links retain them and update the room binding. A cache rebuild binds/copies its camera once. All 20 camera backgrounds use raw ROM storage and aligned word copies. Compressed camera assets are rejected; the unused 600-byte row index is removed. CRAM reload is conditional on actual palette changes and occurs after drawing but before presenting the frame. Animated/movable models leave the bake, and stationary flags still remain dynamic until their rendered-pose/mask hash has stayed unchanged for 25 world ticks. This keeps sustained pushing out of the bake while allowing settled doors and stopped ghosts to return to it. Per-slot object ownership resets cache history when activation recycles a slot; owners and quiet timestamps use 96 bytes total. Static props must still appear in front of farther moving actors: at rebuild, their colored draw also records visible pixel coverage into an uncached 8000-byte bitmap shared by the row-owning SH2s, including black model pixels, screen-door glass and camera-mask clipping. The bitmap reuses contact/face-sort scratch after up to 384 face indices move to a 768-byte local array. Its bits generate a bounded 3072-span cache without a second monochrome draw or framebuffer scan; scanning reads each bitmap byte once and skips uniform runs. Full restores use direct aligned word reads, and baking copies only the static damage rectangle into the original RAM background. Each span is a four-byte `(u16 pixel start, u16 length)` record. Overlapping foreground props copy only their cached pixels; an exhausted span pool falls back to a normal model draw. A separate gameplay geometry scratch array is shared by combat and LIFE bounds calculations. The renderer shares a union between normal geometry scratch and compact contact-group vertices. At physical model contacts it resolves reciprocal depth per pixel in 64×64 tiles. The 8 KiB tile reuses the 6 KiB face-sort workspace and adds only 2 KiB. Search/Push animations activate physically touching prop groups; flat floor patches are excluded; groups are bounded to 768 vertices and fall back to existing painter output if that bound is exceeded. Near clipping and conditional architectural masks remain applied. Masks read the original raw camera asset rather than composite bake pixels. Unrelated foreground models retain their normal painter position after the contact repair. All-front contact vertices reuse camera-space X for cached reciprocal depth; near-crossing groups retain X for clipping.

## Asset bank version 2

Header: `A32X`, `u32 version`, `u32 count`, `u32 size`. Directory entries: `u32 offset`, `u32 packed size`, `u32 unpacked size`, `u16 type`, `u16 flags`. Assets are four-byte aligned with big-endian fields. Flag 1 means `(u8 count, u8 palette index)` RLE; the generic decoder understands it, but all current assets are raw and the camera renderer requires flag zero.

This bank contains 1957 assets, 3,788,160 bytes: floor 0 (one room/five cameras), floor 1 (eight rooms/fifteen cameras), both 272-model/305-animation banks, 563 LIFE scripts, 45 tracks, object/variable/define state, title/palettes, item text and 21 English book entries. Names identify floor and room/camera. Models keep the original 36-byte header; the primitive offset points to an array of u32 offsets, followed by compact variable-length primitives `(u8 type,count,color,material; u16 size; u16 indices[count])`. The largest supported model has 384 vertices, 40 groups and 384 primitives. Text/book control codes are converted to uppercase printable text and line breaks for the small native font. Copyright (source byte A9) becomes `(C)` and the I-Motion separator (FA) becomes `-`, avoiding unsupported glyphs. Seven type-13 UI assets contain `u16 width, u16 height` followed by raw indexed pixels. The host importer precomposes the original ITD_RESS:4 corners, repeating rails and 44×8 title plaque. The title panel matches their colors to the existing title palette; gameplay panels retain the original indices. Runtime panels use aligned word copies, including black pixels, and merge their rectangle into per-bank damage. They require no additional RAM bitmap, decompressor or palette changes. Panel coordinates and widths are even and within the logical scene. The single-panel console layout and controls remain intact.

`assets/manifest.json` records original input and bank hashes. The importer reads the supplied installation without modifying it. Converted game resources are separate from the engine license and are excluded from the source ZIP.


## Fixed prop drawing programs

AS_STATIC_RASTERS is a raw type-14 asset. Its u32 entry count is followed by sorted `(u32 view, u32 pose key, u32 program offset)` records. View is `(floor << 8) | camera`. Pose FNV-1a hashes model offset relative to GAME_PALETTE, floor/room, position and actor angles; skeleton-free geometry is required. Shared programs contain four i16 screen bounds, u32 command count, then `(u16 start pixel, u16 length, u8 color, u8 pad)` literal drawing spans. The importer captures unmasked output using two sentinel backgrounds and the same native integer renderer. Runtime spans maintain damage and optional coverage, then use the actual current ZV to apply architectural masks. Missing/moved/rotating/skeletal poses fall back to normal drawing.

The static cache key hashes camera-mask activation rather than raw collision coordinates. The scene key preserves static painter order because collision bounds also influence ordering. Group-zero animation state is excluded because actor angles replace it during vertex generation. Child states and real geometry changes remain dependencies. These rules prevent unnecessary dynamic classification and a second bake after the quiet timer, while retaining required order changes.

## Memory and diagnostics

The RELEASE module occupies 83,108 SDRAM bytes; BSS uses 160,176. Static SDRAM ends at `0x0603B658` (243,288 bytes), leaving 2,472 bytes below the stack reservation. The master reserves 12 KiB and the slave 4 KiB at the top of 256 KiB SDRAM. The linker rejects static allocations at or above `0x0603C000`. Framebuffer RAM is separate. This is a tight budget; later systems need measured reuse, fewer live poses, or overlays rather than unchecked additions.

COMM registers retain the v6 coherent input, sequence, region and heartbeat protocol. `debug_state[32]` preserves its first sixteen timing/player/render words and adds floor, room, menu, script-fault LIFE/word/code, inventory/in-hand/prompt, actor-pool peak, world ticks, selected action, health, book, finish and camera-target state. PROFILE builds retain SH7604 FRC scopes; RELEASE removes timer instrumentation. See the v6 architecture report for the inherited mailbox details and `PERFORMANCE.md` for the current measurements.

## Persistent saves

The RA header advertises 128 KiB cartridge SRAM at 0x200000–0x21FFFF. The SH2 transports sequential bytes through blocking COMM0/1 commands serviced by the 68000, batching two bytes per exchange. SRAM is enabled only for a transaction. A record has six big-endian u32 words: magic AITD, schema S14/01, generation, length, FNV-1a payload checksum and an imported-game fingerprint. Fingerprinting includes object/variable/define data and original LIFE/track PAKs. Two 64 KiB records alternate; the older valid record remains while writing. Magic is cleared first and committed last, then read back. A newer damaged record is rejected. Length and schema/resource bounds are validated before applying state. Loading first parses into bounded local scratch, then rebinds original asset IDs and applies the payload. Renderer caches and pointers are reconstructed. Native scheduling rebases once after save/load so SRAM time cannot advance gameplay on Resume. No heap or full-save RAM buffer is used.

## Autonomous audio

Type 15 stores u32 PCM sample count, i16 initial predictor, u8 initial IMA step index, one reserved byte and low-nibble-first ADPCM. Two slave-owned voice states mix at 8 kHz. A cache-through eight-request ring carries sample, next sample and repeat state from the master. PWM level-6 IRQ refills three samples per interrupt and preserves ABI registers/PR/MACH/MACL. Voice updates are protected briefly against the ISR. The idle slave polls requests; interrupts remain available during rasterization. The IRQ is disabled after centered silence when voices finish. Sample headers are read directly from immutable asset_bank so slave audio does not depend on master-cached platform globals.

Type 16 stores driver duration and command count as two u32 values, then four-byte `(delta ticks, port, register, value)` commands. Ports 0/1 target YM2612, 2 PSG, 3 a wait and 4 the end marker. The 68000 reads through the standard 1 MiB bank window, executes from its own RAM and advances a rational 294/(5×refresh) phase per VBlank. It owns the Z80 bus with reset released, including across controller reads. Music selection/status/stop/fade use COMM commands 0x5010–0x5014. Music pauses while SRAM is mapped, avoiding ROM/SRAM access conflicts. The game polls completion and preserves queued LIFE music transitions. Loading restarts the selected song rather than serializing chip/playhead state. FM two-operator patches use YM algorithm 4 (or additive 7), with the unused operator pair muted. OPL multipliers/pitch are translated; envelope, waveform and PSG percussion behavior are approximations.

The offline importer shares identical `(type, flags, payload)` blocks, preserves old asset IDs and appends 101 effect / 8 music assets. Shared model payloads reduce prepared-prop keys to 216 entries while retaining the 169 distinct drawing programs. Prior fixed camera, mask and renderer paths remain unchanged. Source IDs/raster programs are regenerated with the final bank layout.
