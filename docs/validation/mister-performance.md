# MiSTer/PicoDrive profiling — 2026-10-20

The same automatic diagnostic cartridge reproduces a substantial rendering
gap on the user's MiSTer `S32X_20260603` core. Draw work takes approximately
1.7–1.9 times as long as PicoDrive in these samples. Framebuffer-swap waiting
alone does not explain the gap. This is an instrumented comparison, not a new
release FPS benchmark or physical 32X validation.

The [follow-up optimization report](mister-optimization.md) records the
low-overhead scheduling experiments and the selected shared text-rendering
change. This report preserves the initial measurements.

## Matched setup and results

Both platforms ran Edward in NTSC with diagnostic ROM SHA-256
`2f2f6e5bd8e82fdc0105d985c8f678f7e890bf2730c252aaa24665fa4ec201a2`.
The diagnostic was built from the current sound-fix source. Its release ROM,
`4b6b7894573dd084e03dc6e7b413083cfb0e65f3769b0eb0a73744290d30de21`,
matches the user's existing `AITD32X-audio-test-v2.32x` exactly.

Each case warms the renderer for one second, measures for at least three
seconds, then displays results for eight seconds. The live case retains the
25 Hz simulation and original 60 Hz animation clock. Frozen cases force draws
without advancing the world; they measure renderer capacity. Near-camera
position is `(3231,0,-3733)`, camera zero. The final case is a synthetic frozen
floor-3/room-1/camera-3 fixture at `(0,0,0)`, not the previously measured
sofa-room/hallway continuation. No saved game is loaded for any fixture.

| Case | PicoDrive draws/s | MiSTer draws/s | PicoDrive draw ms | MiSTer draw ms |
|---|---:|---:|---:|---:|
| Live starting room | 19.78 | 12.20 | 34.68 | 59.65 |
| Frozen starting room, quiet | 24.00 | 15.00 | 35.12 | 60.74 |
| Frozen starting room, two voices | 20.00 | 14.92 | 36.65 | 66.95 |
| Frozen near camera, quiet | 20.00 | 12.00 | 41.78 | 71.08 |
| Frozen near camera, two voices | 20.00 | 12.00 | 43.26 | 77.98 |
| Frozen floor 3, room 1, camera 3 | 29.83 | 15.00 | 31.94 | 58.46 |

Machine-readable measurements, raw counters, native screenshots and calibration
ratios are recorded in [mister-performance.json](mister-performance.json).
Ignored build evidence lives in `build/mister-profile/`.

## What the measurements establish

The live starting-room sample reproduces a 7.58 FPS difference in the diagnostic.
Its average game-update work per completed draw is 3.51 ms in PicoDrive versus
11.64 ms on MiSTer. Geometry transformation is 4.20 versus 6.28 ms, sorting
4.31 versus 5.87 ms, and the ordinary primitive stage 11.28 versus 19.51 ms.
Those stages contain different amounts of nested work and must not be added
to the inclusive draw time. Update work per draw also depends on how many
25 Hz updates are batched between draws.

Swap waits in that case are 11.67 versus 9.84 ms; MiSTer is slower despite
spending less time waiting to flip. In the frozen starting-room quiet case,
swap waits are 6.54 versus 5.89 ms while draw work grows by about 25.6 ms.
The measured slowdown is therefore in executing the workload, rather than
simply an extra fixed wait in the presentation path.

The floor-3 fixture's command-queue wait grows from 3.69 to 17.50 ms per draw;
the wait at worker completion grows from 0.08 to 1.30 ms. The automatically
adapted row ownership may differ between platforms. This is evidence of a
slave/queue bottleneck in this fixture, not proof of a particular bus fault.

Two repeating footstep voices increase MiSTer's inclusive draw time from
60.74 to 66.95 ms at the start and from 71.08 to 77.98 ms near the camera.
Queue waits grow as well. The latter still reports 12 FPS because reduced
flip waiting absorbs the additional work. Unchanged displayed FPS can hide
audio/rendering contention. Two simultaneous looping voices are a deliberate
stress case, not a claim about ordinary footsteps' duty cycle.

The results support investigating external-memory/cache costs and shared-bus
contention, plus queue traffic and adaptive SH2 ownership. They do **not**
isolate cache misses, ROM latency, SDRAM arbitration or individual instruction
timings. Those require targeted experiments before choosing a production fix.

## Instrumentation and limits

- `tools/build_mister_profile.py` copies source into ignored
  `build/mister-profile/`, substitutes only the diagnostic master entry point
  and modifies profiling support in that copy. The release source and build
  remain unchanged.
- Reporting and profile helpers execute from protected ROM. Existing renderer
  scope instrumentation and worker queue/end-wait counters are enabled.
  Instrumentation, call placement and changed cache layout affect throughput;
  the figures above must not be substituted for release performance.
- No diagnostic text is drawn during measurement. Native 320×224 screenshots
  carry a 32-word result barcode with an XOR check. PicoDrive verification
  compares every decoded report with published native RAM. MiSTer collection
  accepts only checksum-valid reports.
- Stage time is calibrated from the accumulated free-running counter ticks
  and elapsed VBlanks of each measurement, avoiding an assumed shared CPU
  clock between platforms. Individual intervals must finish before the
  16-bit timer wraps. PicoDrive uses the existing counter-only FRC shim;
  its total timer/VBlank calibration passes within 3% in every case.
- `draw_inclusive` covers `Game::Draw()` and the final restore fence. Update,
  palette upload and framebuffer flips are outside that scope. Primitive/fill
  and queue/end-wait measurements can overlap other stages. Restore timing
  covers submission and the master's copy; slave restoration can overlap
  geometry preparation. These counters are not an exclusive-time breakdown.
- The live test consumes 74 updates in PicoDrive and 73 on MiSTer before its
  final draw, consistent with an incomplete update batch at the sampling
  boundary. Frozen tests consume zero measured updates. All six cases report
  zero world faults on both platforms.
- The collector requests a screenshot approximately every two seconds, including
  some measurement periods. Screenshot collection can perturb HPS/memory
  activity; there was no external capture device or logic analyzer.
- This is one short sample per case, with no physical console comparison and
  no whole-game performance claim. Hardware-cache or bus-level causes remain
  hypotheses.

## Memory, validation and device state

The diagnostic ROM stays at 14,155,776 bytes. The startup module is 83,572
bytes (1,152 fewer than release), BSS is 160,880 bytes (+176), and static SDRAM
ends at `0x0603BAE8`, leaving 1,304 bytes below the unchanged reserved stacks.
The fixed module ends at ROM byte 4,179,364. These are diagnostic-only figures;
the production ROM, memory layout, assets and save format are unchanged.

Focused checks: diagnostic build and linked bank-layout checks pass, with only
the existing RWX linker warning. The six-case PicoDrive run verifies reports,
timer calibration and the live simulation cadence. The deployed diagnostic
hash matches, and all six MiSTer reports decode successfully.

The original alpha3 ROM, sound-fix ROM, existing `AITD32X.sav` and `S32X.CFG`
have identical hashes before/after the run. No fixture writes SRAM. After
collection, the existing sound-fix ROM was loaded again; the preceding paused
runtime session was not preserved across the core reload. The separate
diagnostic remains at `games/S32X/AITD32X-mister-profile-v1.32x`. Its launch
descriptions are temporary files under MiSTer's `/tmp`.

Reproduction:

```sh
python3 tools/build_mister_profile.py
python3 tools/check_mister_profile.py --core .local/tools/picodrive-frt_libretro.so
# Upload build/AITD32X-mister-profile-v1.32x under a unique filename and launch it.
# Authenticate an SSH control connection separately; no credentials are stored.
python3 tools/collect_mister_profile.py --host root@MISTER_IP --ssh-control /tmp/mister-control
```

No production optimization, commit or release was made.
