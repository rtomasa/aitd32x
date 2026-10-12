# Scheduled DIVU projection

## Shared implementation

`src/render/project.cpp` pairs X/Y projection, replacing two separate scalar
divider calls. The shared helper is used by ordinary actors throughout the
house and cinematics, contact-depth vertex preparation, effects, inventory
and pickup previews. Near-plane rejection remains at each caller. World
screen coordinates still clamp to +/-4096; effects and previews stay unclamped.
Camera products, signed truncation, projection centers and depth inputs are
unchanged. Prepared prop assets do not need regeneration.

The [SH7604 hardware manual](https://antime.kapsi.fi/sega/files/sh7604.pdf),
section 10.3.2, specifies 39-cycle signed division. X division now overlaps a
Y load, multiplication and MACL read, followed by 36 NOPs. Y division overlaps
X centering and two clamp comparisons/branches, followed by 34 NOPs. Counting
each scheduled instruction as only one cycle gives at least 39 cycles on
every path; taken branches, loads, multiplication stalls and interrupts can
only add time. Optional clamp moves add time as well. The assembly block keeps
these operations in order and declares MACL, T and memory clobbers.

Eight padding NOPs per projected vertex become useful work. The remaining
padding preserves hardware latency even when an emulator computes DIVU
results instantly. Each CPU retains its own divider; PWM saves multiply
registers and uses no DIVU. Standalone raster-edge, radius, reciprocal-depth
and wide-gradient divisions retain their existing waits. The helper uses
no reciprocal approximation, new buffer or interrupt masking.

## Focused checks

- RELEASE ROM and host library build. Only the existing RWX linker warning.
- `check_projection_native.py`: 9,368 defined signed projection cases match
  independent native C division, including negative/zero coordinates, signed
  focal values, near-valid and distant depths, both clamp modes and varied
  centers. The diagnostic cartridge is isolated under `build/`, with read-only
  asset links and no user SRAM. Report: `build/projection-native-ntsc.json`.
- `check_sh2_scheduling_native.py`: NTSC and PAL; both characters, glass and
  cupboard, bedroom door and a contact group. Forced row boundaries and both
  framebuffer banks match host pixels. Reports:
  `build/sh2-scheduling-native-{NTSC,PAL}.json`.
- `check_gameplay_ui.py --native-only`: NTSC and PAL rotating Actions, Oil Lamp
  and Gramophone previews, both banks, unchanged static UI and paused world.
  Sampled preview cadence remains 30 draws/s. Report:
  `build/gameplay-ui-check/report.json`.
- A/B native scene hashes match in all three sampled floors/cameras below.
  Linked bank/RAM/protected-ROM checks and `git diff --check` pass. Disassembly
  in `build/projection-asm.txt` confirms the scheduled operations and padding.

PicoDrive results do not validate physical DIVU timing, EverDrive or MiSTer.
Rendering checks sample states and items; they are not a complete playthrough.
The minimum-latency guarantee comes from the instruction schedule, rather than
the emulator's arithmetic comparison.

## Measurements

The immediately preceding ROM/ELF/host library is preserved under ignored
`build/projection-reference/`, with identical assets. In an isolated PicoDrive
NTSC benchmark, 262,144 calls per mode compare the prior serial DIVU projection
with the new helper; both helpers execute in SDRAM. Timing uses the 68000's
VBlank sequence. An initial FRT probe returned zero in the core and was replaced;
no FRT-based performance claim is made.

| Isolated helper work | Before | After | Reduction |
|---|---:|---:|---:|
| Clamped projection | 153 VBlanks | 135 VBlanks | 11.8% |
| Unclamped projection | 143 VBlanks | 137 VBlanks | 4.2% |

These timings include diagnostic loop/setup/output work and are quantized to
VBlank. They measure this workload, not universal per-vertex cycle counts.
Evidence: `build/projection-native-ntsc.json`.

The separate matched game comparison is recorded in
`build/projection-performance.json`:

| Sample | Before | After |
|---|---:|---:|
| 10-second early-game trace | 24.2 draws/s | 24.2 draws/s |
| Frozen floor 3, room 1, camera 3 | 19 draws/s | 19 draws/s |
| Frozen floor 6, room 0, camera 2 | 29 draws/s | 29 draws/s |
| Frozen floor 7, room 1, camera 3 | 29 draws/s | 29 draws/s |

Sampled menu latency is unchanged. Whole frames can remain limited by the
25 Hz simulation cadence, VBlank presentation and work outside projection.
Simulation/animation clocks are unchanged. A matched MiSTer/real-32X retest is
needed to establish a hardware FPS benefit.

## Memory and ROM

RELEASE ROM remains 14,155,776 bytes. BIOS module is 85,076 bytes (+160); BSS
remains 160,672 bytes. Static end is `0x0603BFF8`, leaving 8 bytes below the
existing stack reserve (previously 168). The linker enforces this limit;
further static growth requires freeing space or moving suitable code to ROM.
Master/slave stack reservations are unchanged. Projection stays in SDRAM.
No asset, banking or save-format changes. PROFILE was not built.

Candidate: `build/AITD32X.32x`, checksum `7517`, SHA-256
`c542dcea37c8c4ad1c4c35685c94305165d7f89ce1e8f3b47744629b195b33f6`.
Existing release/test bundles and `.local/baseline` remain intact. No commit
was created.
