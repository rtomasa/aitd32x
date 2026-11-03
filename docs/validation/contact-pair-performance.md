# Planned contact pairs — 2026-11-03

The renderer now prepares simple dynamic character/prop contacts before shading.
It reuses each model's transformation/projection for ordinary and depth drawing,
omits redundant overlap fill where coverage is proven, and corrects depth before
later foreground models draw. This applies throughout gameplay under the same
conditions, without door, object or room IDs. Accurate contact ordering remains
enabled. The broader contact renderer handles ambiguous scenes.

Baseline is commit `3ad514c`, ROM SHA-256
`c94626606e7b39fedfee7421bd185031c1cf1d984cb4ef2def711fbd89a95c64`.
The [machine-readable evidence](contact-pair-performance.json) records sampled
results and artifact hashes. This follows the [scenery review](scenery-performance.md);
the historical player-front door policy remains rolled back.

## Bounds and correctness

Planning requires one animated triggering character source, one nearby dynamic
nonflat prop, and at most 768 total vertices. Intervening scenery must have cached
coverage disjoint from both projected models. Both face lists and the entire
bounded depth command program are prepared before any pixels are omitted.
Near-plane/clamped-depth, ambiguous membership, prepared-color props and capacity
failures retain the existing path without partial framebuffer writes.

Ordinary triangles and proven convex polygon faces omit the contact rectangle;
other primitives and nonconvex faces retain ordinary coverage. Stable face order,
black/glass rules and architectural masks remain intact. The second model's
damage footprint enters scenery repair only at its original painter rank.
No simulation, collision, LIFE, audio, animation-clock or save-format changes are
included. Gameplay remains 25 Hz independently of the approved 60 Hz animation
clock and presentation.

## PicoDrive results

Matched frozen NTSC poses use a calibrated FRC-enabled PicoDrive build, one second
of warmup and at least three seconds of timing. Both versions explicitly retain
the same prop as dynamic while simulation is frozen. Draw time includes contact
work and excludes presentation wait. All six before/after pixel hashes match;
every timed candidate draw uses the planned path.

| Frozen pose | Before draw | After draw | Reduction |
| --- | ---: | ---: | ---: |
| Edward, corridor door 96 | 73.941 ms | 68.727 ms | 7.1% |
| Edward, bathroom door 160 | 49.664 ms | 41.781 ms | 15.9% |
| Edward, moved chest 800 | 42.839 ms | 40.547 ms | 5.4% |
| Emily, corridor door 96 | 83.708 ms | 78.051 ms | 6.8% |
| Emily, bathroom door 160 | 46.058 ms | 40.659 ms | 11.7% |
| Emily, moved chest 800 | 41.655 ms | 40.094 ms | 3.7% |

Stock PicoDrive live controller routes retain real movement, collision and
scripts, using private SRAM fixtures and Edward:

| Live action window | Before | After |
| --- | ---: | ---: |
| Approach/open/enter bathroom, eight seconds | 19.50 FPS | 19.75 FPS |
| Open/exit bathroom, eight seconds | 20.125 FPS | 20.875 FPS |
| Push attic chest, five seconds | 17.00 FPS | 20.00 FPS |

For completed draws with observed door angle strictly between 0 and 256, mean
intervals fall from 116.7 to 107.0 ms entering (17/19 samples) and 53.6 to 46.9 ms
exiting (37/43 samples). Idle bathroom/corridor samples remain 25/20 FPS
respectively. The sampled bathroom-exit/corridor-entry interval remains 183.3 ms.
Live presentation poses and simulation batches can
differ, so these averages establish neither a minimum FPS nor exact device
timings. Door-route gains are modest; the larger live gain is during pushing.
Ordinary warm-cache diagnostic scenes remain approximately unchanged.

## MiSTer

The matched six-pose comparison passes on MiSTer's installed `S32X_20260603`
core at nominal 60 Hz, with the same warmup/timing protocol as above. Every
before/after pixel hash matches the emulator fixtures, and every timed candidate
draw uses the planned path. FRC stage times are scaled by measured VBlank
progress, independently of the emulator's CPU timing model.

| Frozen pose | Before draw | After draw | Reduction | Before FPS | After FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Edward, corridor door 96 | 114.917 ms | 104.952 ms | 8.7% | 8.57 | 8.57 |
| Edward, bathroom door 160 | 73.467 ms | 60.199 ms | 18.1% | 12.00 | 15.00 |
| Edward, moved chest 800 | 69.133 ms | 62.873 ms | 9.1% | 12.27 | 15.00 |
| Emily, corridor door 96 | 125.458 ms | 114.606 ms | 8.7% | 7.50 | 8.57 |
| Emily, bathroom door 160 | 67.345 ms | 58.073 ms | 13.8% | 14.10 | 15.00 |
| Emily, moved chest 800 | 66.967 ms | 62.511 ms | 6.7% | 14.51 | 15.00 |

The unchanged Edward corridor FPS illustrates VBlank quantization despite lower
drawing cost. These are frozen overlapping poses, not whole-route averages or
minimum FPS. No live MiSTer crossing/pushing route was measured in this pass.

Diagnostic ROMs were uploaded under separate `AITD32X-contact-pair-before/after-20261103.32x`
names. All five existing save/configuration files retain their original hashes;
the MiSTer menu is restored. Screenshots and raw reports remain under
`build/contact-pair-profile/{before,after}`. MiSTer FPGA results and physical
Sega 32X validation are separate; physical 32X validation remains pending.

## Validation and memory

- RELEASE/host builds and linked bank-layout checks pass.
- 900 bathroom-route pixel comparisons cover both characters and alternating
  framebuffer histories against the preserved renderer. The planned path runs
  in all four routes. Eight isolated pair comparisons cover both painter orders
  and both banks. Eight guard and two near-plane rejections leave clean pixels.
- The preserved-renderer sweep passes 2,660 comparisons across 144 cameras.
  The existing contact-order and prepared-contact-cache checks pass 64 and 30
  cases respectively.
- Band checks pass 2,400 ordinary comparisons, 192 deferred-triangle comparisons
  and 120 convex-polygon/depth-fan comparisons, including black/glass and clipping.
- Native PicoDrive scheduling checks pass 10 scenes in each of NTSC/PAL,
  including both characters with a moving bathroom door and moved chest. Forced
  split positions 20/180/100 and both framebuffer banks match host pixels.

These are sampled renderer checks, not a full puzzle/playthrough visual audit.
They never overwrite battery saves. Detailed local logs remain under ignored
`build/contact-pair`, `build/contact-pair-profile` and `build/door-performance`.

The RELEASE module grows 224 bytes, from 84,580 to 84,804 bytes; BSS remains
160,704 bytes. Static SDRAM ends at `0x0603BF08`, leaving **248 bytes** before the
reserved stacks. Pair preparation adds two temporary face-index arrays totaling
1,536 bytes on the existing 12 KiB master stack. The static gap is separate from
runtime stack headroom; runtime high-water use has not been measured. Cold
planning/drawing helpers execute from protected ROM. Existing vertex, command
and depth scratch is reused; no persistent image/pose/depth buffer or heap is
added. The command queue retains its size and uses spare header bit 23 for
per-face polygon omission. ROM size remains 14,155,776 bytes; original assets are
byte-identical. Further code changes must recheck the very tight static margin.

Playable candidate: `build/AITD32X-contact-pair.32x`, SHA-256
`f88affea8388d574318e25df52b7a4129243fae1224d29a0a32cc3fc62bbfce9`.
Diagnostic-only timing/counters are excluded. No commit or release is made.

## Reproduction

Preserve the baseline source and host library before building the candidate:

```sh
make -j2 host all build/check_bands
python3 tools/check_contact_pair.py --reference /path/to/baseline/build/libaitd32x.so
build/check_bands
python3 tools/check_draw_order_cache.py --sweep --reference-library /path/to/baseline/build/libaitd32x.so
python3 tools/check_sh2_scheduling_native.py .local/tools/picodrive_libretro.so --region NTSC
python3 tools/check_sh2_scheduling_native.py .local/tools/picodrive_libretro.so --region PAL
python3 tools/profile_contact_pair.py --source /path/to/baseline --label before --core /path/to/calibrated-picodrive.so
python3 tools/profile_contact_pair.py --label after --core /path/to/calibrated-picodrive.so
```

The profile tool writes isolated cartridges under `build/contact-pair-profile`.
Load each on MiSTer, authenticate SSH separately, then use
`tools/collect_mister_profile.py --host root@HOST --ssh-control /tmp/CONTROL --project build/contact-pair-profile/before --rom build/contact-pair-profile/before/build/AITD32X.32x --variant 64`;
repeat with `after`. Compare hashes before interpreting timings. The explicit
movable flag is diagnostic-only and identical in both versions.
