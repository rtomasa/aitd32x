# Partial scenery rebuilds and parallel contact depth — 2026-10-11

This implements the recommendations following the
[initial performance review](performance-review.md). The immediate reference is
that review's uncommitted build, ROM SHA-256
`d34e42d3a1dccae02a3572c071dc0e231a7721b84c52becefa13e409615b69ea`,
preserved locally with its source and host library in `build/perf2-reference`.
The original `a0fd040` reference and `.local/baseline` remain untouched.

## Implementation

**Partial scenery repairs.** The cache remembers static membership and painter
ranks. When only order changes, it identifies overlapping inverted pairs, then
expands the affected rectangle to enclose all intersecting static actors and
whole framebuffer words. It restores that region from the original camera,
replays those props in the new order, and copies the region into the background
cache. Existing coverage spans remain valid because geometry and active masks
are unchanged. The opposite framebuffer bank receives damage for that region.

The closure includes mask writes even for props with empty visible coverage.
Whole-actor replay preserves raster rounding without introducing a new clipping
rule. Disjoint order changes require no repaint. Changed camera, membership,
pose or mask state retains the full-rebuild path. No invalidation is deferred
and the previously corrected door/hatch occlusion is preserved.

**Prepared contact geometry and both SH2s.** After transforming a contact group,
the idle 4,608-byte gameplay vertex workspace holds up to 164 prepared 28-byte
primitive records. Off-region faces are rejected and triangle depth gradients
are computed once, rather than again for every tile. Ordinary actor rendering
still performs its own transforms; no persistent transformed-model cache is
added. `may_alias` explicitly permits the shared scratch representation under
the pinned GCC toolchain.

The existing 8,192-byte depth buffer supplies two 64×32 scratch tiles. Larger
contact regions split at a complete screen row: master and slave fill disjoint
bands, each clearing and owning its own half. The existing command ring carries
a CONTACT job and completion fence. Slave inputs use uncached aliases; SH7604
write-through stores publish the immutable geometry/context before the job.
The master waits before reusing scratch or drawing foreground models. PWM
interrupts remain enabled. Small jobs stay on the master. Near-clipped groups
or prepared-command overflow take the original path before any pixels are
changed; that fallback executes from ROM to fit the SDRAM budget. The existing
768-vertex contact limit and painter fallback remain.

**Engine and 68000 work.** Actor refresh builds a local room-visibility bitset
once, preserving activation order and the original fallback for room IDs
outside the bitset. Single-step movement avoids six divisions while retaining
stationary collision processing. The 68000 writes its music ROM bank register
only when the bank changes, invalidating the cached selection at startup and
SRAM close. Music stays on the 68000; no Z80 driver or new cartridge mapper is
introduced. Those were reviewed alternatives, not recommended changes.

The 25 Hz simulation, 60 Hz animation clock, original assets, audio guards,
save schema and UI behavior are unchanged.

## Measured results

PicoDrive libretro `2.04aitd32x`, default clocks, RELEASE, Edward, NTSC, music 0.
Same diagnostic positions and normal controller interactions as the previous
review; completed draws are counted over five emulated seconds.

| Scene | Previous pass | Current | Change |
|---|---:|---:|---:|
| Hallway camera 2 | 10.0 FPS | 12.0 FPS | +20.0% |
| Sustained attic chest pushing | 13.0 FPS | 14.8 FPS | +13.8% |
| Bedroom chest opening/searching | 11.6 FPS | 13.4 FPS | +15.5% |

World progress remains 25 Hz within completed-frame sampling. The original
automatic closing behavior is retained. Against the earlier `a0fd040` build,
these scenes were 8.6, 11.8 and 11.4 FPS respectively.

| Sofa-room → hallway presentation gap | Previous pass | Current |
|---|---:|---:|
| First hallway frame | 300.0 ms | 250.0 ms |
| Following frame | 300.0 ms | 183.3 ms |
| Third frame | 133.3 ms | 100.0 ms |
| First three combined | 733.3 ms | 533.3 ms |

The combined gap decreases 27.3%; the original `a0fd040` trace was 600.0 ms.
The required order change still occurs: signature `547776375` becomes
`3953669369`, now with a partial repair. An isolated cache/engine stage measured
633.3 ms before the contact changes. The route releases movement after the
first completed hallway frame, so changed cadence also changes the release
tick. These are VBlank-quantized interactive traces, not identical-work timing
microbenchmarks. A five-second FPS sample has 0.2 FPS granularity.

The first new-camera rebuild and substantial contact work remain. Larger gains
would require more changes; this pass does not promise 25 rendered FPS in every
scene. Neither physical 32X hardware nor the user's RePlayOS device was measured.

## Validation

- Both-character host differential: 345 transition frames each, plus 1,080
  opening/pushing/window tick frames and 32 additional draws, with identical
  pixels and state against the previous build.
- Partial-cache oracle: independent forced-full-rebuild instance, both host
  framebuffer banks, both characters, natural room route, reversed overlapping
  static order, in-memory black/glass materials and original masks. Ten partial
  repairs are exercised. Camera and geometry changes verify the full fallback.
- Contact path counters in the interaction check: 1,102 prepared groups, maximum
  154 commands. These counters exist only in the host library.
- Native contact differential passes eight scenes each in NTSC and PAL using
  canonical actor states in both ROMs and both physical framebuffer banks. It
  compares opening chest, pushing chest, opening hatch and hallway door scenes
  for both character selections. The diagnostic freezes scheduler data without
  a pause overlay, asserts unchanged gameplay ticks and distinct visible
  Edward/Emily images, and leaves ROM code unchanged. Release-ring inspection
  verifies two completed slave CONTACT→END jobs per scene, not just matching
  final pixels.
- Explicit host fixtures trigger near clipping and prepared-command overflow
  for both characters. Counters confirm each fallback and pixels match the
  previous renderer exactly.
- Rendering, animation and reported-bug checks pass, covering masks, glass,
  zero pixels, depth intersections, opening poses, saber behavior and timing.
- NTSC/PAL native save/load and audio checks pass on the final ROM, including FM
  playback after SRAM close and core-restart reload, plus cached bank state.
  All eight music streams also pass duration/audio checks and PWM completes
  6,600 samples in 0.825 seconds on the preceding candidate. Only the SH2 scratch
  alias annotation changed afterward; audio/68000 sources and assets did not.
  The retained reports identify their respective ROM hashes. All current music
  assets occupy bank 3, so natural playback across a bank boundary is untested.

```sh
make -j2 host all build/check_render build/check_animation
./build/check_render
./build/check_animation
python3 tools/check_reported_bugs.py
python3 tools/check_partial_cache.py
python3 tools/check_transition_pixels.py --reference build/perf2-reference
python3 tools/check_contact_native.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --reference build/perf2-reference --region NTSC
python3 tools/check_contact_native.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --reference build/perf2-reference --region PAL
python3 tools/profile_contacts.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --scene chestopen --label perf2-final --music 0
python3 tools/check_room_transition.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars --label perf2-final
```

The native differential requires a reference directory containing its matching
ROM, ELF and source so layouts come from the correct compiler inputs. Reports
are summarized in [performance-followup.json](performance-followup.json).
Detailed local reports are `build/perf2-final-*.json`,
`build/room-transition-perf2-final-ntsc.json`, `build/partial-cache-parity.json`,
`build/perf2-scene-pixel-parity.json`, `build/contact-native-parity-*.json`,
`build/contact-host-fallback-parity.json` and `build/perf2-audio/`.
Fixtures use host memory/transient libretro SRAM; no user
battery files are read or overwritten.

## Memory and build

| Item | Previous pass | Current |
|---|---:|---:|
| ROM bytes | 4,128,768 | 4,128,768 |
| Startup module bytes | 83,044 | 84,532 |
| Linked SH2 BSS bytes | 160,120 | 160,144 |
| Static SDRAM end | `0x0603B5E0` | `0x0603BBC8` |
| Gap below reserved stacks | 2,592 bytes | 1,080 bytes |

Cache metadata adds 28 declared bytes; linked BSS grows 24 bytes with alignment.
Contact rendering adds no persistent buffer. The 68000 bank cache adds two bytes
of its own BSS. The reserved master/slave stacks remain 12 KiB/4 KiB. Static
prologue inspection estimates the slave contact-plus-audio chain around 1.3 KiB;
the master fallback's roughly 2.4 KiB local frame nests inside the contact
setup's roughly 1.2 KiB frame. These are not measured stack high-water marks.
The linker still enforces the stack boundary and retains its existing RWX LOAD
warning. The assembler also expands out-of-range SH2 short branches into longer
instruction sequences; the resulting ROM is the one measured above.

Final ROM SHA-256:
`aa48c754bdf2ae39a25b30cb294da9222721cbdf9f02f7e091d8eb9dcc51ff6f`.
Asset bank is unchanged: 3,976,924 bytes, 1,969 entries, SHA-256
`b1a17763e20dd481337d4495c0ee32147b08a9e474c3a4e2c122164079f97dfa`.
