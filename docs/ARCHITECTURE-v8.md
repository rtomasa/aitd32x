# Native architecture — revision 8

## CPU and timing

The 68000 boots the cartridge, detects PAL/NTSC and publishes coherent controller snapshots each VBlank. The master SH2 executes the 25 Hz simulation, LIFE/track, active objects, animation, collision, inventory and camera selection. It transforms and sorts geometry and presents completed frames. Both SH2s rasterize: the master owns logical rows 0–99 and the slave owns 100–199, using the v6 cache-through eight-entry command ring.

The runtime is freestanding C++17 with no heap, OS, filesystem, SDL, STL, RTTI or exceptions. A VBlank phase accumulator catches up simulation ticks independently of rendering. The approved animation clock remains 60 Hz with fractional phase units of 1/1500 second: each logic update consumes 60 units and each original key lasts `duration * 25` units. Walk/run root displacement and pose interpolation carry remainder across keys. Pause, inventory, prompts and books stop the world clock.

## World and script state

The bank supplies 292 original 26-word object records, 207 variables and 45 CVars. Found-item metadata stays in its world record; an active slot owns body, flags, position, angles, LIFE, animation and track state until deactivation writes it back. The imported models use at most 379 vertices, so the single-model scratch bound is 384. The actor pool has 24 slots, each with a bone pose and collision bounds. Activation follows floor/life mode/room visibility and original object order. A capacity error stops with a diagnostic rather than overwriting memory.

LIFE operands and track data are big-endian native words. The interpreter checks cursor/branch/variable/object bounds, caps recursion at eight and caps each invocation at 2048 instructions. It preserves the original caller for expressions on targeted opcodes. Unsupported instructions raise an on-screen LIFE/word error. Sound and music playback remain deferred. SPECIAL now emits bounded presentation effects: death evaporation, hit particles and smoke. Three effect slots each hold at most 30 points, with their own presentation RNG; they do not alter LIFE random choices. Music state remains available to scripts.

The original scripts select action animations, offer/take/equip/read/reload/drop/throw items, schedule enemy arrivals, update health/ammunition and drive stair transitions. The console maps B+Up to run and C to inventory. The first loaded-floor boundary is deliberate: attempts to stage the camera target beyond floor 1 show END OF THIS BUILD.

## Rendering and static props

The packed-pixel VDP presents 320×224 in both regions, with a 320×200 logical scene at `(0,12)`. Each bank has a valid native line table and separate damage bounds. Word writes restore palette index zero correctly. The FPS overlay occupies the upper border and counts completed draws against VBlanks.

Original FITD group geometry, Q15 arithmetic, flat primitives, stable depth order, camera projection, near clipping and conditional foreground masks remain in use. Type-2 eye points occupy one native pixel; small type-3 sphere eyes can shrink to one pixel instead of retaining a three-pixel minimum. Back-facing polygons are culled. Material 2 uses a fixed 50% screen-door pattern to show the scenery through glass. Actor translation/mask tests use the actor's own floor and room. A stable world-level painter sort orders multiple models before their own primitive sort.

One 64,000-byte RAM image stores the current background with static props baked in. Camera/model/position/angle/pose/bounds changes invalidate it. Animated or pushed props leave that cache. Static props must still appear in front of farther moving actors: at rebuild, a temporary monochrome render captures their actual visible pixel coverage, including camera-mask clipping, into a bounded 3072-span cache. Each span is a four-byte `(u16 pixel start, u16 length)` record. Overlapping foreground props copy only their cached pixels; an exhausted span pool falls back to a normal model draw. A separate gameplay geometry scratch array is shared by combat and LIFE bounds calculations. The renderer shares a union between normal geometry scratch and compact contact-group vertices. At physical model contacts it resolves reciprocal depth per pixel in 64×64 tiles. The 8 KiB tile reuses the 6 KiB face-sort workspace and adds only 2 KiB. Both stationary and pushed furniture participate; groups are bounded to 1024 vertices and fall back to existing painter output if that bound is exceeded. Near clipping and conditional architectural masks remain applied.

## Asset bank version 2

Header: `A32X`, `u32 version`, `u32 count`, `u32 size`. Directory entries: `u32 offset`, `u32 packed size`, `u32 unpacked size`, `u16 type`, `u16 flags`. Assets are four-byte aligned with big-endian fields. Flag 1 means `(u8 count, u8 palette index)` RLE; backgrounds use it only when smaller.

This bank contains 1840 assets, 2,899,916 bytes: floor 0 (one room/five cameras), floor 1 (eight rooms/fifteen cameras), both 272-model/305-animation banks, 563 LIFE scripts, 45 tracks, object/variable/define state, title/palettes, item text and 21 English book entries. Names identify floor and room/camera. Models keep the original 36-byte header; the primitive offset points to an array of u32 offsets, followed by compact variable-length primitives `(u8 type,count,color,material; u16 size; u16 indices[count])`. The largest supported model has 384 vertices, 40 groups and 384 primitives. Text/book control codes are converted to uppercase printable text and line breaks for the small native font.

`assets/manifest.json` records original input and bank hashes. The importer reads the supplied installation without modifying it. Converted game resources are separate from the engine license and are excluded from the source ZIP.

## Memory and diagnostics

The RELEASE module occupies 81,508 SDRAM bytes; BSS uses 162,312. Static SDRAM ends at `0x0603B870` (243,824 bytes), leaving 1,936 bytes below the stack reservation. The master reserves 12 KiB and the slave 4 KiB at the top of 256 KiB SDRAM. The linker rejects static allocations at or above `0x0603C000`. Framebuffer RAM is separate. This is a tight budget; later systems need measured reuse, fewer live poses, or overlays rather than unchecked additions.

COMM registers retain the v6 coherent input, sequence, region and heartbeat protocol. `debug_state[32]` preserves its first sixteen timing/player/render words and adds floor, room, menu, script-fault LIFE/word/code, inventory/in-hand/prompt, actor-pool peak, world ticks, selected action, health, book, finish and camera-target state. PROFILE builds retain SH7604 FRC scopes; RELEASE removes timer instrumentation. See the v6 architecture report for the inherited mailbox details and `PERFORMANCE.md` for the current measurements.
