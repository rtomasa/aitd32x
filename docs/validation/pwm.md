# PWM carrier and footstep correction — 2026-10-20

Reference: `6f3eff4`, ROM SHA-256
`239f0d4a57e8ac1a3cc3eaf304e474fc64d77360cd26121b254a63a36f84ceb8`.
Revised candidate SHA-256:
`4b6b7894573dd084e03dc6e7b413083cfb0e65f3769b0eb0a73744290d30de21`.
The preceding blocking candidate was
`1faa7f95ba7f19db13e234358fcf43217cc830ce02dc6309db6a4ab5cdac6445`.
The user reports that candidate improved sound but froze the logo/white flash
and the arrival/car sequence while music continued. It is superseded.

## Findings and change

The [preceding investigation](hardware-issue-1.md) identified an approximately
8 kHz PWM carrier left running at midpoint after each effect. Masking its IRQ
does not disable the physical output. The user also narrowed the MiSTer
observation to alternating footsteps: one sounds metallic, with correct
playback duration. These are distinct observations; an emulator cannot confirm
the console's analog tone or the MiSTer timbre.

Walking alternates samples 30 and 31. Comparing the imported ADPCM with the
original VOC resampled through the existing importer gives:

| Sample | PCM samples | Duration | ADPCM RMS error | Signal/error ratio |
| --- | ---: | ---: | ---: | ---: |
| 30 | 6,895 | 0.861875 s | 151.89 | 23.50 dB |
| 31 | 5,174 | 0.646750 s | 130.88 | 24.08 dB |

This does not identify an unusually bad ADPCM conversion on one foot. It does
not establish whether either original waveform sounds metallic. The source
and decoded comparison WAVs are in ignored `build/audio-reference/`.

All effects now share a roughly 24 kHz output carrier, using cycle 960 in
NTSC and 951 in PAL. Each interrupt decodes one 8 kHz source sample per voice
and mixes them using the existing gain/clamp. Three interpolated pulse widths
span the previous/current levels, providing a simple reconstruction filter.
The source rate and effect lengths are retained. Samples/assets, effect IDs,
music synthesis, simulation and animation clocks are unchanged.

The first candidate added unbounded FULL/EMPTY polling inside the PWM
interrupt. A stuck wait monopolizes the rendering slave, while 68000 music
continues independently. That is an unsafe regression consistent with the
reported symptoms. The precise status/timing condition on the user's device
has not been captured; the hang was not reproduced in stock PicoDrive.
The earlier PWM check skipped most startup animation, leaving an integration
coverage gap.

The revised ISR never waits for status. It performs at most three writes,
retains an unwritten partial group when FULL is asserted, and returns without
advancing the source again. After its final ramp, shutdown happens on the next
three-period interrupt, without reading EMPTY. Explicit stop also completes
if FULL remains stuck. New requests reset pending state or cancel deferred
shutdown. The 24 kHz interpolation that improved the reported sound is retained.

[Sega's hardware manual](https://consolemods.org/wiki/images/e/e9/32X_Hardware_Manual_1994_Sega_text.pdf),
printed pages 24–25 and 57, documents cycle timing, the three-entry FIFOs,
FULL/EMPTY flags and the stopped counter when both channels are off. The
24 kHz carrier is above normal audibility; whether this fixes the reported
console tone and MiSTer footstep timbre still requires listening on those
devices. MiSTer's digital reconstruction differs from the physical PWM output.

## Focused native checks

`tools/check_pwm_native.py` runs the actual ROM in the preserved stock
PicoDrive libretro core using private RAM. It never reads/writes battery files.
The NTSC reference was recorded before changing the driver. Candidate checks
ran in NTSC and PAL, covering:

- Thunder and both footstep effects, with nonzero captured PCM and full decoded
  sample counts at completion.
- Sample chaining and finite repeats, with expected aggregate durations.
- Two simultaneous indefinitely repeating voices, followed by explicit stop.
- Disabled PWM output after completion and stop, including repeated restarts.
- Frozen first-room rendering while idle and with two sustained audio voices.
- Complete startup in both regions: 73 distinct rotating-logo frames in NTSC,
  62 in PAL, complete arrivals with 21 camera/room path entries each, original
  picture holds, gameplay, then save/load through a fresh core.

`tools/check_pwm_irq.py` compiles the production ISR body against private host
I/O stubs. It verifies return with FULL stuck high, shutdown without EMPTY,
partial-group preservation and restart during deferred shutdown. The body
performs at most four status reads per call. These are algorithmic fault
injections, not emulation of a complete MiSTer bitstream or physical bus.

| Case | Expected | NTSC reference | NTSC candidate | PAL candidate |
| --- | ---: | ---: | ---: | ---: |
| Thunder (6) | 3.850125 s | 3.867 s | 3.867 s | 3.860 s |
| Footstep 30 | 0.861875 s | 0.867 s | 0.867 s | 0.860 s |
| Footstep 31 | 0.646750 s | 0.650 s | 0.650 s | 0.660 s |
| 30 then 31 | 1.508625 s | 1.517 s | 1.517 s | 1.500 s |
| 31 repeated once | 1.293500 s | 1.300 s | 1.300 s | 1.300 s |

Observations are quantized to one video frame and include request polling.
The source-rate rounding error is below 0.03% with these cycle settings.

In the four-second frozen NTSC rendering windows, both idle and two-voice
throughput remain **19.25 completed draws/s** before and after. The PAL
candidate gives 16.0 draws/s in both windows; no paired PAL reference was
recorded. These are a sampled rendering-capacity check, not general gameplay
FPS or hardware performance guarantees. Master-bound scenes can conceal
additional slave CPU cost. Interrupt frequency rises from approximately
2.67 to 8 kHz; total ADPCM decodes per second remain unchanged.

The audio object has no division helper dependencies and no DIVU access.
Its only arithmetic helper is the existing signed-shift routine. The assembly
IRQ wrapper continues preserving PR, MACH/MACL and ABI registers, so interrupts
cannot corrupt the renderer's in-flight division or multiplication. Compiler
stack reports give the mixing body 28 bytes, `Sample` 8 and `Start` 4, excluding
the existing assembly wrapper and interrupted rendering call stack.

## Memory and artifacts

The linked layout check passes. ROM remains **14,155,776 bytes**. Relative
to the original 8 kHz driver, pending-state storage adds **8 bytes of BSS**
(160,704 bytes total). Infrequent effect setup now executes from protected ROM,
keeping the loaded-code increase to **112 bytes**, or **120 bytes** combined
static growth. The module is 84,724 bytes. Static SDRAM ends at `0x0603BEB8`,
leaving **328 bytes** below the reserved stacks. Module ROM placement ends at
4,180,516, leaving 13,788 bytes below the direct-window boundary. No heap or
full sample buffer was added.

Ignored evidence:

- `build/pwm-before-NTSC.json`, `build/pwm-after-NTSC.json`, `build/pwm-after-PAL.json`.
  The after reports now describe the revised candidate; initial logs are historical.
- `build/pwm-irq-faults.json`, `build/pwm-nonblocking-*.log`, `build/pwm-startup-*.log`.
- `build/startup-native-{NTSC,PAL}.json`: full startup and fresh-core save/load.
- `build/audio-regression/`: preserved blocking candidate and source.
- Corresponding `.log` files and `pwm-{before,after}-*-step-{30,31}.wav` captures.
- `build/pwm-audio-disassembly.txt`, `build/pwm-audio-stack.su`, `build/bank-layout.json`.
- `build/audio-reference/`: preserved preceding ROM/ELF/host library and footstep comparisons.

## Device confirmation

Test `build/AITD32X-audio-test-v2.32x` on MiSTer and, when available, a physical
32X/EverDrive. Listen to the first logo thunder and the silence afterward,
then alternate footsteps while walking/running and compare both steps. Also
compare FPS in the same room/camera with sustained sound. Actual acoustic
quality and hardware performance of this revision remain unvalidated here.
The user confirmed improved sound on the preceding revision, but its freezes
mean it must not be treated as validated gameplay. The existing SRAM
format is retained; no save files, release bundles or baseline ROM were
replaced, and no commit or publication was made.
