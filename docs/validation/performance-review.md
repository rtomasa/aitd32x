# 32X performance review — 2026-10-10

The subsequent [implementation follow-up](performance-followup.md) applies the
partial-cache, parallel-contact, engine-update and music-bank recommendations.
The measurements below remain the earlier pass's evidence.

Reference: `a0fd040` (the user-confirmed interaction, occlusion and audio fixes).
The changes below preserve its simulation, animation, painter order and assets.
The review covered engine update/LIFE/collision, rendering and caches, CPU
mailboxes, audio, storage, ROM layout and build constraints. Measurements focus
on the reported interactions and a room transition; they are not a full-game
profile or physical 32X validation.

## Retained optimizations

- Read aligned model, animation, camera, room and raster-program fields with
  SH2 word loads. Keep generic byte readers for formats without that alignment
  guarantee. Importer alignment and record strides were checked against the
  current bank, including 544 model references, 610 animations and 20 cameras.
- Skip interpolation division for unchanged animation channels and skip the
  recursive bone walk for identity rotations. Root movement, key completion,
  the 25 Hz simulation and the approved 60 Hz animation clock are unchanged.
- Use the SH7604 signed 64/32 DIVU for contact-depth gradients. A magnitude
  check retains software division when the quotient cannot fit signed 32 bits,
  preserving the previous narrowing result. Explicit 39-cycle latency follows
  the [SH7604 manual, sections 10.2–10.4](https://antime.kapsi.fi/sega/files/sh7604.pdf#page=308).
  Each CPU owns its DIVU; the audio ISR does not use it.
- Restore interior background spans with word reads, retaining byte endpoint
  handling and the word writes needed for palette index zero.
- Clear compiled-prop coverage only inside its bounds. Write full coverage
  bytes directly, build depth-mask spans by byte, and defer clearing a tile's
  mask until an active mask actually intersects it.
- Write nonzero glass pixels directly; preserve the neighboring pixel when
  clearing to zero. Whole-row CPU ownership is unchanged.

No new global buffer, asset conversion, cartridge mapper or CPU command protocol
is introduced. `profile_contacts.py` now has an unlocked bedroom `chestopen`
fixture. Transition and contact probes use different temporary layout filenames
so running them together cannot overwrite their different structure layouts.

## Measurements

Local PicoDrive libretro `2.04aitd32x`, default clocks, RELEASE, Edward, NTSC.
Each scene measures completed draws during five emulated seconds. Music 0 is
enabled; placement is diagnostic and interaction uses normal controller input.
One five-second window has 0.2 FPS granularity. These positions differ from the
older v14 hallway fixture; its 20 FPS figure is not a comparable baseline.

| Scene | Reference FPS | Current FPS | Change |
|---|---:|---:|---:|
| Hallway camera 2, player `(2700,0,400)` | 8.6 | 10.0 | +16.3% |
| Sustained attic chest pushing | 11.8 | 13.0 | +10.2% |
| Bedroom chest opening/searching | 11.4 | 11.6 | Essentially flat: one extra draw |

The chest fixture unlocks object 36 and suppresses the saber pickup pause.
Its original automatic closing is retained. Static signature-change counts
remain 0/2/1 for hallway/pushing/opening respectively. World progress stays at
25 Hz within completed-frame sampling. The PAL chest-opening smoke check gives
12.0 FPS and exactly 25.0 world ticks/s over its completed-frame interval; no
PAL before/after performance claim is made.

### Room transition remains unresolved

The sofa-room-to-hall walking trace shows:

| Presentation gaps | Reference | Current |
|---|---:|---:|
| First hallway frame | 316.7 ms | 300.0 ms |
| Following frame | 150.0 ms | 300.0 ms |
| Third frame | 133.3 ms | 133.3 ms |
| First three gaps combined | 600.0 ms | 733.3 ms |

This is **not an overall transition improvement**. Faster drawing exposes an
additional ordering state: the first hallway draw occurs at world tick 246,
player Z -1297, instead of tick 247, Z -1255. Insertion sorting static and dynamic
actors together can change the static subsequence as the player moves. The scene
signature correctly changes from `547776375` to `3953669369`, requiring another
full bake. Objects 33 and 63 exchange order; their screen bounds overlap and
their masked drawing programs differ by 706 pixels between the two orders.
Ignoring that change would alter the corrected rendering. No order-skipping
change is retained. Presentation timing is VBlank-quantized and input release
depends on the first completed hallway frame, so this is an interactive trace,
not a fixed-state microbenchmark.

The next substantial transition optimization should rebuild only the affected
background region, including masks and all intersecting props. A separately
validated painter-order redesign is another option. Deferring a required bake
or ignoring its signature would leave wrong scenery pixels.

## CPU, memory and banking findings

| Area | Finding and next useful work |
|---|---|
| Master SH2 | Contact correction repeats geometry/face work after ordinary rendering and runs on the master. Cache or prepare face data once per contact group before splitting depth tiles; measure transformation versus fill cost before choosing the split. |
| Slave SH2 | Already rasterizes rows 100–199 and services 8 kHz PWM interrupts. Contact tiles could be assigned to it through explicit ownership and an uncached queue, but shared geometry/masks must remain valid until completion. Moving LIFE state across CPUs would add synchronization to a currently deterministic update. |
| 68000 | Already handles input, YM2612/PSG music and SRAM from its own RAM. `ROMByte` writes the music bank register per byte; caching the selected bank is a small future bus optimization, requiring music/SRAM verification. It is not an established cause of the measured stalls. |
| Z80 | Its bus is owned by the 68000 music path. A Z80 music driver would require new code and bus/command ownership, with no demonstrated gain for these rendering bottlenecks. |
| Engine update | `RefreshActors` repeatedly scans room visibility for 292 objects; a local visibility bitset could remove repeated work while preserving activation order. `MoveActor` can avoid substep division when there is one step; stationary collision processing must still run for scripts. Neither is changed here. |
| RAM/cache | Continue reusing geometry, coverage and depth scratch. Full-screen depth buffers do not fit the present budget. Both SH2s must continue using uncached aliases for shared queues/coverage and exclusive framebuffer rows. |
| ROM/banking | Current camera data is already raw; there is no runtime camera decompression to eliminate. Fixed prop programs already trade ROM for fewer transforms. Extra animation programs or full-house content need a capacity/mapper plan; pointers retained by actors and the audio ISR prevent naive bank switching. |
| Save/UI/audio | No steady-state rendering gain justifies changing the existing journal, pause/resume timing or audio ownership. Save compatibility and the confirmed sound guards are retained. |

## Focused validation

- Host room-transition comparison: 345 exact pixel/state frames per character.
- Host interaction comparison: 1,080 tick frames and 32 extra fresh/cached draws
  across both characters, bedroom opening, attic pushing and intact/broken
  windows from front/back. Pixels, palettes and state match the reference.
  All variables/active state were compared each tick; all 292 objects at scene
  checkpoints. This ad hoc fixture/report is under ignored `build/`.
- `check_render`: glass CPU split, depth intersections, raw masks, zero pixels,
  colored coverage, restoration and effect footprints pass.
- `check_animation`: original cycle/root totals, fractional crossing and
  PAL/NTSC catch-up pass. The existing reported-bugs check also passed while
  validating the animation shortcuts.
- Native DIVU diagnostic: 13,871 comparisons with native libgcc, including
  3,394 quotients outside signed32 range. The initial overflow-flag-only design
  failed on this core; the retained software magnitude check passes.
- Native NTSC interaction/transition probes and PAL opening complete without
  script faults. They use transient emulator RAM, not user battery saves.

```sh
make -j2 host all build/check_render build/check_animation
./build/check_render
./build/check_animation
python3 tools/check_transition_pixels.py --reference build/perf-reference
python3 tools/check_wide_divide_native.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars
python3 tools/profile_contacts.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --scene chestopen --label perf-final --music 0
python3 tools/check_room_transition.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --label perf-final
```

The reference directory above is a local copy of the pre-change binaries.
For another checkout, build `a0fd040` separately and pass that directory instead.
The compact retained evidence is [performance-review.json](performance-review.json).
Full local traces are `build/perf-{before,final}-*.json`,
`build/room-transition-perf-{before,final}-ntsc.json`,
`build/perf-scene-pixel-parity.json` and `build/wide-divide-native-ntsc.json`.

## Build footprint

| Item | Reference | Current |
|---|---:|---:|
| ROM bytes | 4,128,768 | 4,128,768 |
| Asset bank bytes / entries | 3,976,924 / 1,969 | Unchanged |
| SDRAM startup module bytes | 85,060 | 83,044 |
| BSS bytes | 160,120 | 160,120 |
| Static SDRAM end | `0x0603BDC0` | `0x0603B5E0` |
| Space below reserved stacks | 576 bytes | 2,592 bytes |

The existing 12 KiB master / 4 KiB slave stacks are retained. This is static
layout headroom, not a measured stack high-water mark. The existing linker RWX
LOAD-segment warning remains.

ROM SHA-256: `d34e42d3a1dccae02a3572c071dc0e231a7721b84c52becefa13e409615b69ea`.
Asset SHA-256: `b1a17763e20dd481337d4495c0ee32147b08a9e474c3a4e2c122164079f97dfa`.
Original resources, saves and `.local/baseline` are unchanged. The user's
RePlayOS Raspberry Pi frontend and physical 32X hardware were not measured.
