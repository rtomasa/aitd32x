# Alone in the Dark 32X

## Technical Development Plan

### 1. Objective

Create a native Sega 32X conversion of **Alone in the Dark 1**, using **FITD** as the reference implementation for:

- game logic
- script interpretation
- room/floor handling
- actor state
- animation
- collision
- inventory
- camera definitions
- original resource formats

The result should not be a generic FITD port running through an abstraction layer.

The final architecture should be a **native 32X engine specialized for AITD1**, retaining FITD-derived game behavior while replacing its desktop rendering, filesystem, audio, input, memory management and platform code.

Working project name:

`AITD32X`

---

# 2. Reference projects

## Primary source

### FITD

Repository:

`yaz0r/FITD`

FITD is the canonical game-engine reference.

Use FITD as the source of truth for:

- PAK/resource decoding
- actors
- objects
- animations
- rooms
- floors
- camera definitions
- script opcodes
- collision
- game variables
- inventory
- save-state structures
- gameplay behavior

The first development task should be to identify and freeze a FITD revision against which the original game can be played reliably.

---

## Console-port reference

### Dream in the Dark

DITD is a FITD-derived Dreamcast port that already replaces substantial desktop-specific portions of FITD, including its renderer, timing, platform integration and math routines.

Use it as a reference for:

- separating engine and platform layers
- removing desktop assumptions
- fixed-point-friendly architecture
- console asset management
- replacing the FITD renderer

Do not attempt to port the Dreamcast renderer itself.

---

## 32X reference

### Doom 32X Resurrection

Use D32XR as the principal reference for:

- 32X initialization
- master/slave SH-2 startup
- communication
- framebuffer management
- SH-2 optimization
- fixed-point routines
- PWM audio
- ROM layout
- SRAM
- dual-SH2 workloads

---

## Toolchain

Use:

**Marsdev + 32XDK**

The required compilers are:

```text
m68k-elf-gcc
sh-elf-gcc
```

---

# 3. Overall architecture

The game should be divided into three execution domains:

```text
                  ┌──────────────────────┐
                  │      Cartridge       │
                  │ engine + AITD assets │
                  └──────────┬───────────┘
                             │
                       Sega 32X bus
                             │
            ┌────────────────┴────────────────┐
            │                                 │
        Motorola 68000                   Master SH-2
            │                                 │
     system supervisor                 FITD game core
     joypad handling                   script VM
     audio control                     actors
     save/SRAM                         rooms
     SH-2 startup                      collision
            │                          animation
            │                          renderer setup
            │                                 │
            │                    ┌────────────┴──────────┐
            │                    │                       │
            │               Master SH-2             Slave SH-2
            │                    │                       │
            │              game / geometry        rasterization
            │              render commands        polygon work
            │                    │                       │
            └────────────────────┴──────────┬────────────┘
                                           │
                                       32X VDP
                                           │
                                     8-bit framebuffer
```

The **68000 must not run FITD gameplay code**.

Its role should remain small and deterministic.

The SH-2 side runs the actual engine.

---

# 4. CPU responsibilities

## Motorola 68000

Responsibilities:

- 32X bootstrap
- controllers
- region detection
- SRAM access
- Mega Drive-side sound hardware
- communications with SH-2
- optional music playback
- system-level services

It should expose a very small mailbox to the SH-2:

```c
struct MDServices {
    uint16_t pad1;
    uint16_t pad2;
    uint16_t region;
    uint16_t command;
    uint16_t response;
};
```

Avoid continuous communication between processors.

The SH-2 side should consume one input snapshot per game tick.

---

# 5. SH-2 workload

## Master SH-2

Master SH-2 runs:

```text
FITD state machine
script interpreter
actor update
animation
collision
room transitions
camera selection
inventory
AI
3D transforms
projection
render command generation
```

The initial implementation should run all gameplay on the Master SH-2.

Do not prematurely distribute gameplay logic.

---

## Slave SH-2

Initially:

```text
idle / debug worker
```

Then move rendering workloads to it.

Long-term:

```text
Master SH-2
    game logic
    transforms
    clipping
    render list creation

Slave SH-2
    polygon rasterization
    dirty-region restoration
    foreground masking
```

A later optimization could have both SH-2s rasterize different actors or screen regions.

---

# 6. Video architecture

Use the 32X VDP in:

**Packed Pixel mode — 8 bits per pixel.**

This provides a 256-entry palette and maps naturally to AITD's palette-oriented graphics.

The game keeps its original logical rendering resolution:

```text
320 × 200
8 bpp
```

The physical 32X video output is standardized to:

```text
320 × 224
```

on **both NTSC and PAL systems**.

There is no vertical scaling.

There is no repeated-line scaling.

There is no filtering.

Every original AITD pixel maps directly to exactly one 32X framebuffer pixel.

---

# 7. 320×200 centered inside 320×224

The 200-line AITD image is centered vertically inside the 224-line 32X output.

Layout:

```text
320 × 224 output

┌────────────────────────────────┐
│          12 lines              │
│        border / black          │
├────────────────────────────────┤
│                                │
│                                │
│          AITD image            │
│           320×200              │
│                                │
│          exact 1:1             │
│                                │
├────────────────────────────────┤
│          12 lines              │
│        border / black          │
└────────────────────────────────┘
```

Therefore:

```text
AITD pixel (x, y)
        ↓
32X pixel (x, y + 12)
```

with:

```text
0 <= x < 320
0 <= y < 200
```

No transformation is required.

---

# 8. Region behavior

Use **320×224 for both NTSC and PAL**.

Do not use PAL 320×240 for gameplay.

This ensures identical rendering geometry on every console:

```text
NTSC
320×224
12 + 200 + 12

PAL
320×224
12 + 200 + 12
```

Benefits:

- identical framebuffer layout
- identical projection
- identical camera coordinates
- identical occlusion masks
- identical debugging
- identical screenshots
- no PAL-specific rendering path

Only timing differences between 50 Hz and 60 Hz need to be handled separately.

---

# 9. Border handling

Initially, the extra scanlines should simply be black.

```text
lines   0–11     black
lines  12–211    AITD
lines 212–223    black
```

Later these regions may contain decorative pixel art.

Possible uses:

```text
top border:
    Alone in the Dark visual motif
    mansion ornamentation
    subtle decorative pattern

bottom border:
    decorative pattern
    optional status indicators
```

Any decorative border must remain completely independent of the 320×200 gameplay surface.

The gameplay framebuffer coordinates must never change.

This ensures that future presentation improvements cannot break:

- projection
- actor positioning
- collision visualization
- foreground masks
- camera data

---

# 10. Gameplay viewport abstraction

Internally define:

```c
#define SCREEN_WIDTH       320
#define SCREEN_HEIGHT      224

#define GAME_WIDTH         320
#define GAME_HEIGHT        200

#define GAME_X_OFFSET        0
#define GAME_Y_OFFSET       12
```

The 3D engine should continue thinking in pure AITD coordinates:

```text
0..319 × 0..199
```

Only the final framebuffer write adds:

```text
GAME_Y_OFFSET
```

This distinction should be maintained throughout the project.

---

# 11. Framebuffer strategy

Use double buffering.

Architecture:

```text
Framebuffer A
Framebuffer B
```

while the VDP displays A:

```text
SH-2 renders B
```

then swap.

The logical game surface itself is:

```text
320 × 200 = 64,000 bytes
```

at 8 bpp.

The full visible framebuffer is:

```text
320 × 224 = 71,680 bytes
```

The top and bottom 12-line regions remain static most of the time.

They therefore do not need to be rewritten every frame.

---

# 12. Border initialization

At startup:

```text
clear framebuffer A
clear framebuffer B
```

This creates black borders automatically.

If decorative borders are later implemented:

```text
copy border artwork into framebuffer A
copy border artwork into framebuffer B
```

The border then remains untouched during normal game rendering.

Only the central 320×200 viewport changes.

---

# 13. Do NOT redraw the entire room every frame

AITD is unusually suitable for the 32X because the room is not real-time polygonal geometry.

The background is static.

Therefore maintain:

```text
background image
+
dynamic actors
+
foreground occlusion
```

The simplest prototype can copy all 64 KB of the active background before rendering a frame.

Once correctness is established, implement dirty rectangles.

For every actor:

```text
previous bounding rectangle
current bounding rectangle
```

Before redrawing:

```text
restore previous rectangle from static background
```

Then:

```text
draw actor at new location
```

Only damaged portions of the 320×200 game area need restoring.

The 12-line borders are never involved.

---

# 14. Camera changes

When FITD changes camera:

```text
load camera background
load palette
load occlusion information
reset dirty rectangles
copy full 320×200 background
```

Copy it into the central viewport:

```text
destination_y = source_y + 12
```

The borders remain untouched.

Because AITD cameras are static, expensive full-screen operations occur relatively infrequently.

---

# 15. Background storage

Do not retain all room backgrounds in RAM.

Store them in cartridge ROM.

On a camera transition:

```text
ROM
 ↓
decompress
 ↓
SDRAM background cache
 ↓
central 320×200 framebuffer region
```

The active background requires approximately:

```text
64 KB
```

of working memory.

The 32X SDRAM budget is small enough that working sets must be managed explicitly.

General rule:

**ROM = storage**

**SDRAM = currently active working set**

---

# 16. Asset build pipeline

Do not make the 32X parse the complete PC installation dynamically.

Create a host-side converter:

```text
tools/aitdpack
```

Input:

```text
Original AITD1 installation
*.PAK
game resources
```

Output:

```text
AITD32X asset bank
```

The converter should reuse FITD's knowledge of the original formats.

Pipeline:

```text
AITD PC files
      │
      ▼
FITD resource parser
      │
      ▼
AITD32X converter
      │
      ├── backgrounds
      ├── palettes
      ├── models
      ├── animations
      ├── rooms
      ├── cameras
      ├── collision
      ├── scripts
      ├── samples
      └── text
      │
      ▼
32X-native ROM structures
```

Runtime resources should be:

- big-endian/native where beneficial
- aligned
- indexed
- pointer-free
- directly addressable from cartridge where practical

Avoid runtime parsing of DOS-era container formats whenever possible.

---

# 17. ROM resource index

Generate something like:

```c
typedef struct {
    uint32_t offset;
    uint32_t packed_size;
    uint32_t unpacked_size;
    uint16_t type;
    uint16_t flags;
} AssetEntry;
```

And:

```text
asset directory
background data
models
animations
rooms
scripts
audio
strings
```

This allows the runtime to locate assets without filenames or a filesystem.

---

# 18. Compression

Start simple.

Recommended first choices:

```text
backgrounds     LZSS or similar
scripts         uncompressed
models          uncompressed
animations      uncompressed
audio           PCM / ADPCM later
```

Do not optimize ROM size until gameplay works.

Fast decompression is more important than maximum compression ratio.

---

# 19. FITD refactoring

Create a platform-neutral engine layer.

Target structure:

```text
src/
    engine/
        actor/
        animation/
        camera/
        collision/
        inventory/
        room/
        script/
        game/

    render/
        render_api.h
        render_32x.c

    platform/
        platform_api.h

        32x/
            input.c
            timing.c
            storage.c
            save.c
            audio.c

    sh2/
        master/
        slave/

    md/
        main68k.c

tools/
    aitdpack/
```

FITD platform calls must disappear from the engine.

The core should see interfaces such as:

```c
Platform_ReadAsset()
Platform_GetTicks()
Platform_GetInput()
Platform_PlaySound()

Renderer_SetCamera()
Renderer_DrawActor()
Renderer_DrawOverlay()
```

Nothing in the gameplay layer should know that the machine is a 32X.

---

# 20. C++ strategy

Do not immediately rewrite FITD completely in C.

That introduces unnecessary risk.

First make a minimal freestanding C++ subset compile for SH-2.

Use:

```text
-fno-exceptions
-fno-rtti
-fno-threadsafe-statics
```

and avoid:

```text
iostream
filesystem
threads
heavy STL containers
dynamic allocation in gameplay
```

Then convert individual hot or problematic systems to C where useful.

The objective is:

**port behavior first, simplify implementation second.**

---

# 21. Memory allocation

There should be no general-purpose heap during gameplay.

Use dedicated arenas.

Example:

```text
SDRAM
──────────────────────────────
engine state
actor state
script state
current room
current models
current animations
background cache
audio buffers
temporary render workspace
──────────────────────────────
```

Possible allocators:

```c
room_arena
frame_arena
audio_arena
```

`frame_arena` resets every frame.

`room_arena` resets when changing floor or large scene group.

This avoids fragmentation completely.

---

# 22. 3D renderer

Do not port a generic 3D engine.

AITD needs only the rendering functionality its models actually use.

Implement:

```text
model transform
world → camera transform
near clipping
perspective projection
backface rejection
polygon ordering
flat polygon filling
line drawing if required
```

No:

```text
texture mapping
perspective-correct interpolation
dynamic lighting
z-buffer
general-purpose scene graph
```

This is a very small 3D workload compared with Doom or Quake.

---

# 23. Coordinate system

The 3D renderer must project directly into:

```text
320 × 200
```

coordinates.

The viewport offset must **not** be included in projection calculations.

Example:

```text
projected actor position:

x = 155
y = 87
```

remains:

```text
logical position = (155,87)
```

Only when writing pixels:

```text
physical framebuffer position = (155,99)
```

because:

```text
87 + 12 = 99
```

The same rule applies to:

- backgrounds
- actors
- masks
- overlays
- inventory graphics
- subtitles
- debug geometry intended to align with gameplay

---

# 24. Numeric representation

The renderer should use fixed-point arithmetic.

For example:

```text
16.16    world transformations
20.12    where extra range is useful
integer  screen coordinates
```

Generate lookup tables for:

```text
sin
cos
reciprocal
possibly perspective division
```

Only optimize with SH-2 assembly after profiling.

---

# 25. Polygon rasterizer

Initial version:

```text
C implementation
scanline flat polygon filler
8-bit framebuffer
```

All rasterizer clipping should be performed against:

```text
x = 0..319
y = 0..199
```

not against the complete 224-line display.

The destination framebuffer pointer then incorporates:

```text
GAME_Y_OFFSET
```

After correctness is established:

```text
SH-2 assembly hot loop
```

Optimize:

- horizontal spans
- clipping
- framebuffer writes
- repeated color fills
- aligned writes

The rasterizer should be write-oriented and avoid unnecessary framebuffer reads.

---

# 26. Occlusion

Correct background occlusion is essential to AITD.

Render order:

```text
1. restore background
2. draw visible actors
3. apply foreground masks
4. draw game UI
```

Occlusion data remains entirely in the original:

```text
320×200 coordinate space
```

Convert camera occlusion information at build time into a format optimized for the 32X.

Potential representation:

```text
scanline run lists
```

Example:

```c
struct MaskSpan {
    uint16_t y;
    uint16_t x1;
    uint16_t x2;
};
```

When accessing the actual framebuffer:

```text
physical_y = mask_y + 12
```

This is cheaper and safer than modifying original camera geometry.

---

# 27. Game simulation

FITD behavior should initially remain unchanged.

Preserve:

```text
script opcode semantics
actor state transitions
collision rules
animation timing
object state
inventory rules
room state
```

Do not rewrite gameplay systems merely to make them cleaner.

Accuracy is much easier to verify if the 32X version continues to use FITD semantics.

---

# 28. Timing

Gameplay simulation must not depend directly on render FPS.

Architecture:

```text
hardware timing
      │
      ▼
fixed game tick
      │
      ├── gameplay update
      └── rendering when possible
```

Because output is standardized to 320×224 but PAL and NTSC still operate at different refresh rates, simulation timing must compensate for:

```text
NTSC ≈ 60 Hz
PAL  = 50 Hz
```

The game should run at the same logical speed on both.

Do not simply update gameplay once per VBlank.

Maintain a region-independent simulation clock.

Target:

```text
original gameplay speed
stable render cadence
identical game logic on PAL and NTSC
```

---

# 29. Audio

Split audio into two categories.

## Music

Prefer Mega Drive audio hardware where practical.

Possible long-term route:

```text
AITD AdLib music
      ↓
offline conversion
      ↓
YM2612 event stream / VGM-derived format
      ↓
68000 / Z80 playback
```

## Sound effects

Use 32X PWM.

Pipeline:

```text
original sample
    ↓
offline conversion
    ↓
8-bit PCM
    ↓
PWM mixer
```

Start around:

```text
11–16 kHz
mono
```

and increase quality only if CPU and ROM budgets permit.

---

# 30. CD version

Do not make the CD version the first target.

Start with the floppy/DOS data set.

Reasons:

- smaller data set
- no CD audio problem
- no large speech archive
- easier ROM footprint
- simpler validation

Later add:

```text
CD voices
higher-quality samples
alternate music
```

as optional enhanced cartridge builds.

---

# 31. Input

68000 polls the controller once per VBlank.

Expose a normalized state:

```c
enum {
    PAD_UP,
    PAD_DOWN,
    PAD_LEFT,
    PAD_RIGHT,
    PAD_A,
    PAD_B,
    PAD_C,
    PAD_START
};
```

Map AITD controls logically rather than reproducing PC keyboard bindings.

Potential default:

```text
D-pad    movement
A        action
B        fight/action modifier
C        inventory
Start    pause/options
```

Final mapping can be tuned after gameplay is operational.

---

# 32. Saving

Use cartridge SRAM.

Do not initially reproduce arbitrary FITD filesystem save files.

Define a compact native save structure:

```c
struct SaveGame {
    header
    version
    current_floor
    current_room
    player_state
    inventory
    object_states
    game_variables
    checksum
};
```

If desirable, later create a PC-side converter between FITD saves and AITD32X SRAM images.

---

# 33. Debugging infrastructure

Debugging facilities should exist from day one.

Reserve COMM registers for telemetry:

```text
engine state
camera
room
actor count
frame counter
render time
error code
```

Provide compile-time:

```text
DEBUG
PROFILE
RELEASE
```

builds.

A fatal error should display something useful on screen rather than simply locking the SH-2.

Debug text that does not need to align with gameplay may use the top and bottom 12-line regions during development.

This gives the otherwise-unused border area a useful debugging purpose.

---

# 34. Desktop reference build

Keep a desktop build of the refactored core.

Architecture:

```text
                engine/
               /       \
              /         \
      desktop backend   32X backend
```

The desktop backend should reproduce the same logical rendering surface:

```text
320×200
```

This allows game logic and render positioning to be compared exactly with the 32X implementation.

The desktop renderer does not need to be sophisticated.

Its purpose is engine validation.

---

# 35. Deterministic testing

Create recorded input sequences.

Example:

```text
frame 00001 UP
frame 00002 UP
frame 00003 UP+A
...
```

Run the same sequence through:

```text
desktop reference
32X emulator
```

Periodically compare:

```text
floor
room
camera
player XYZ
animation
life
inventory
game variables
actor states
```

Rendering comparisons should crop the 32X image to:

```text
x = 0..319
y = 12..211
```

producing an exact:

```text
320×200
```

image for comparison with the desktop version.

This makes visual regression testing particularly straightforward.

---

# 36. Development phases

## Phase 0 — FITD reference

Deliverables:

- build current FITD
- obtain known-good AITD1 data set
- verify major gameplay
- identify regressions
- pin source revision
- implement state logging

Exit condition:

**desktop reference is deterministic enough to act as the specification.**

---

## Phase 1 — 32X skeleton

Implement:

- ROM boot
- 68000 initialization
- Master SH-2 startup
- Slave SH-2 startup
- 320×224 video mode
- packed-pixel framebuffer
- 12-line top border
- 12-line bottom border
- double buffering
- joypad
- debug telemetry

First video test:

```text
12 black lines
200-line test pattern
12 black lines
```

Exit condition:

```text
ROM boots on emulator and real hardware
both SH-2 CPUs alive
320×224 output works
central 320×200 viewport is exact 1:1
input works
```

---

## Phase 2 — asset converter

Implement host tool able to extract:

- palette
- one background
- one body/model
- one animation
- one room
- one camera

Exit condition:

**32X displays the first AITD camera centered at 320×200 with untouched pixels and 12 black lines above and below.**

---

## Phase 3 — FITD core extraction

Port:

```text
resource IDs
rooms
floors
actors
camera state
object state
script interpreter
```

Initially no complete rendering required.

Exit condition:

**the attic loads and the game script reaches the expected initial state.**

---

## Phase 4 — protagonist renderer

Implement:

```text
model decoding
animation
transforms
projection
polygon clipping
polygon filling
```

The protagonist is projected into the original 320×200 coordinate system.

Exit condition:

**Edward/Emily appears correctly positioned over the unscaled attic background.**

This is the first major visual milestone.

---

## Phase 5 — complete camera renderer

Implement:

```text
background cache
palette
dirty rectangles
occlusion masks
multiple actors
double buffering
camera transitions
```

Exit condition:

**the player can walk around the attic and change camera correctly while preserving exact pixel alignment.**

---

## Phase 6 — gameplay

Enable and validate:

```text
collision
inventory
doors
object interactions
enemies
combat
room transitions
floor transitions
```

Exit condition:

**the player can progress through several rooms without platform-specific hacks.**

---

## Phase 7 — audio

Implement:

```text
sound effects
music
volume
PWM
YM2612/Z80 integration
```

Exit condition:

**full gameplay with functional audio.**

---

## Phase 8 — complete game

Systematically verify:

```text
all rooms
all puzzles
all enemies
inventory
combat
cutscenes
death states
ending
```

Exit condition:

**AITD1 can be completed on the 32X.**

---

## Phase 9 — presentation

Once the game is stable, replace the black borders if desired.

Possible work:

```text
pixel-art border
subtle mansion ornamentation
region-independent decorative frame
debug/status removal for release build
```

The central 320×200 viewport must remain untouched.

No decorative work may alter:

```text
GAME_X_OFFSET = 0
GAME_Y_OFFSET = 12
GAME_WIDTH    = 320
GAME_HEIGHT   = 200
```

---

## Phase 10 — optimization

Only now optimize.

Profile:

```text
actor update
script interpreter
transform
projection
polygon rasterization
background restoration
ROM transfers
audio
```

Potential improvements:

```text
SH-2 assembly span renderer
dual-SH2 rasterization
pretransformed data
lookup tables
dirty-span restoration
ROM layout optimization
asset prefetching
```

Exit condition:

**stable target frame rate on real hardware.**

---

# 37. First playable milestone

The first major objective should be:

```text
Boot
 ↓
320×224 output
 ↓
12-line black border
 ↓
AITD title / game
 ↓
12-line black border
 ↓
start game
 ↓
attic background at exact 320×200
 ↓
Edward / Emily visible
 ↓
walk around
 ↓
correct animation
 ↓
correct collision
 ↓
camera changes
```

No:

```text
audio
saving
full inventory
all enemies
CD features
decorative borders
```

until this works.

This milestone proves almost every fundamental technical assumption.

---

# 38. Biggest technical risks

### FITD dependencies

Modern FITD contains assumptions unsuitable for a machine with a very small working-memory budget.

Mitigation:

**extract game semantics rather than blindly compiling the application.**

### RAM

This is likely the most important constraint.

Mitigation:

- current-room working set
- ROM-backed immutable assets
- explicit arenas
- camera-level caching
- no heap fragmentation

### ROM bandwidth

SH-2 cartridge access is relatively expensive.

Mitigation:

- sequential transfers
- prefetch
- active asset caching in SDRAM
- avoid repeatedly traversing structures in ROM

### Rendering

Likely much less problematic than RAM.

AITD geometry is simple and flat-shaded.

The strict 320×200 viewport also avoids all scaling overhead.

### Asset size

Speech and CD music would dwarf the actual game engine.

Mitigation:

**floppy version first.**

---

# 39. Recommended development philosophy

The port should progress through three transformations:

```text
STEP 1

FITD
Desktop game
↓
FITD
Portable game core
```

then:

```text
STEP 2

Portable FITD core
↓
Native 32X platform implementation
```

then finally:

```text
STEP 3

General FITD-derived engine
↓
Highly specialized AITD1 32X engine
```

Do not attempt Step 3 immediately.

First make it correct.

Then make it small.

Then make it fast.

---

# 40. Final target architecture

```text
              ORIGINAL AITD1 DATA
                      │
              ┌───────▼─────────┐
              │ aitdpack tool   │
              │ FITD-derived    │
              └───────┬─────────┘
                      │
              optimized ROM bank
                      │
      ┌───────────────┴────────────────┐
      │                                │
   68000                           Master SH-2
      │                                │
 Input                           FITD-derived core
 SRAM                            Script VM
 Music                           Actors
 Services                        Collision
      │                           Animation
      │                           Geometry
      │                                │
      │                         Render command list
      │                                │
      │                           Slave SH-2
      │                                │
      │                         Polygon rasterizer
      │                         Background restore
      │                         Occlusion
      │                                │
      └────────────────────────────────┤
                                       ▼
                              32X framebuffer
                                  320×224
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                 12 lines          320×200            12 lines
                  border            AITD                border
                                   exact 1:1
                                       │
                                       ▼
                                      CRT
```

# 41. Core video rule

The following should be treated as a permanent design constraint:

```text
Physical output:       320×224
Gameplay viewport:     320×200
Gameplay offset:       (0,12)
Scaling:               none
Line duplication:      none
Filtering:             none
NTSC geometry:         identical
PAL geometry:          identical
```

The original game image is always displayed **pixel-for-pixel at 1:1**.

The 24 additional scanlines belong to the presentation layer, never to the game engine.

---

# 42. Core principle

**Port FITD's game, not FITD's PC architecture.**

The game logic, data interpretation and behavior are the valuable parts of FITD.

The graphics and platform layers should be designed specifically for the Sega 32X.

And for video specifically:

**preserve the original 320×200 image exactly and fit the console around it, rather than modifying the game to fit the console.**