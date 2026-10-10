# Movement timing — revision 4, 2026-10-07

The slowdown came from an incorrect animation time unit. The prototype processed elapsed VBlanks into 25 Hz updates correctly, but interpreted each original animation duration word as one simulation tick. The original DOS executable advances its animation clock at approximately **60 Hz**. Revision 4 keeps the 25 Hz simulation and converts animation time separately.

## Original-game measurement

The supplied CD edition was run in an isolated, instrumented DOSBox 0.74-3, using the supplied `SAVE0.ITD` to bypass its voiced introduction. Its executable and PAK bytes were unchanged. Local working copies were used; the installed games were untouched. A local disc image supplied the original data and silent placeholder audio tracks because the installation lacks its CD audio/speech files.

The executable programs PIT channel 0 with divisor **19,886**, giving `1,193,182 / 19,886 = 60.0011063` timer interrupts per second. Its gameplay counter and body key-start timestamps were sampled every 10 ms while Edward walked. Repeating with two fixed CPU cycle budgets confirmed the same 110-tick walking loop:

| DOSBox CPU cycles | Observed complete loop | Stored key-start timestamps | Difference |
|---|---|---|---|
| 12,000 | 14.11–15.93 seconds | 578 → 688 | 110 timer ticks |
| 24,000 | 13.89–15.73 seconds | 587 → 697 | 110 timer ticks |

The observed 1.82–1.84-second intervals agree with `110 / 60.0011 ≈ 1.8333 seconds`, within sampling and original frame-completion granularity. Room loading freezes the original game clock, so those measurements use complete loops after room loading finished. The first walking key also advances exactly 346 Z units in 15 timer ticks, matching the imported data. The measured loops continue against a wall; collision blocks travel but the animation clock continues, allowing its cycle timing to be observed without another room transition.

The supplied floppy launcher did not reach gameplay in this DOSBox setup. Its decoded walking and running animations are byte-identical to the CD edition for both characters. The running CD executable supplies the timing baseline; no floppy-executable clock measurement is claimed.

Evidence: `validation/dos-timing-v4.json`, `dos-walk12.csv`, and `dos-walk24.csv`. Original EXE SHA-256: `2f2c0c27aa84fc10958ac10ab77a804cc500b531fac14bab7d7613064a874df1`.

## Corrected time scale

| Character / animation | Original duration units | Root distance per loop | Previous loop time | Corrected loop time |
|---|---:|---:|---:|---:|
| Edward walking | 110 | 1,369 | 4.40 s | 1.8333 s |
| Emily walking | 120 | 1,467 | 4.80 s | 2.0000 s |
| Edward running | 60 | 2,049 | 2.40 s | 1.0000 s |
| Emily running | 60 | 2,196 | 2.40 s | 1.0000 s |

These are original world-coordinate units. The ideal unobstructed cycle-average walking rates are now 746.73 units/s for Edward and 733.50 units/s for Emily; running is 2,049 and 2,196 units/s. This is a **2.4× correction to the previous interpretation**, derived from the original clock rather than an arbitrary movement multiplier. Animation/root data in the asset bank are unchanged.

Each simulation tick advances 2.4 original animation units. Integer fractional phase preserves that ratio exactly, including at keyframe/loop boundaries. Any leftover time advances the next key; completed-key root displacement is retained. Collision still receives the resulting movement through its existing substeps. Idle, backward and turning animations use the same corrected time scale. The prototype’s controller turn rate and original acceleration/state-machine parity have not been recalibrated.

## Validation

The original-data animation check verifies exact complete-cycle root totals for both protagonists walking/running, Edward’s fractional loop boundary, and ten seconds of irregular PAL/NTSC update batches across sequence wrap. It passes without dropping time.

The actual release cartridge was tested on the unmodified PicoDrive core for Edward/Emily in both PAL/NTSC. During each two-second walking interval it renders at 15–17 FPS, while animation advances at 60 units/s through the 25 Hz simulation. Its published animation phase determines the exact expected root displacement; all four measured displacements match. Input sampling and diagnostic publication introduce a short start/end lag, so the published interval contains 47–49 walking ticks rather than exactly 50. Pause freezes position, orientation and animation phase. Reports are `validation/movement-v4-*.json`.

The close NTSC benchmark remains **12 FPS**, with **125 simulation ticks in five seconds**. This correction restores the animation time scale; it does not increase rendering FPS. Revision 3’s eye/rasterizer changes are retained. Physical 32X performance remains untested.

To reproduce the port checks, regenerate the bank, build, then run:

```sh
make build/check_animation
./build/check_animation
python3 tools/check_movement.py /path/to/picodrive_libretro.so --character edward --region NTSC
python3 tools/check_movement.py /path/to/picodrive_libretro.so --character emily --region PAL
```

Repeat the native check in a fresh process for each of the four character/region combinations. `tools/dosbox-reference.patch` preserves the external emulator instrumentation. Its watch addresses are specific to the recorded executable/load sequence; they are not general DOS game addresses. `AITD_KEYS` supplies ascending `emulated_ms key_enum down` lines, `AITD_WATCH` selects a CSV output, and `AITD_STOP` sets an emulated-ms deadline. The recorded load sequence is Escape at 3 s, Down at 4 s, Enter at 5 s and 7 s, then Up held from 10–16 s; each menu press is held 100 ms. DOSBox's key enums are Escape 49, Enter 52, Down 85 and Up 84. The experiment uses normal CPU core, 320×200 original game video and no host display/audio output.
