# Validation — revision 4, 2026-10-07

Revision 4 corrects animation time units using a running original DOS executable. See `TIMING.md` for measurements and the reason for retaining 25 Hz logic alongside 60 Hz animation.

## Revision 4 results

| Check | Result |
|---|---|
| Original DOS timing | PIT divisor 19,886: 60.0011 Hz; Edward walking loop 110 timer ticks at 12,000 and 24,000 emulated CPU cycles |
| Original animation data | Walking/running resources identical across supplied floppy/CD editions for both characters |
| Freestanding 68000 + SH-2 release build | Passed with Marsdev GCC 13.1.0 |
| Clean source ZIP rebuild | Passed: regenerated assets and ROM reproduce byte-for-byte |
| Exact cycle timing/root totals | Both characters walking/running passed; fractional key/loop time retained |
| Irregular rendering/update batches | Exact ten-second root totals at PAL/NTSC refresh rates, including sequence wrap |
| Actual cartridge movement | Edward/Emily in PAL/NTSC: animation phase and unobstructed displacement agree exactly with imported root motion |
| Native pause | Position, orientation and animation phase remain unchanged for both characters/regions |
| Close renderer performance | 12 FPS NTSC; 125 logical ticks in five seconds; FPS matches framebuffer swaps |

The original game's EXE/PAKs and both installations were not modified. The CD edition was loaded from a working copy with silent placeholder CD tracks and its supplied save. The floppy launcher did not enter gameplay in the reference emulator setup, so the timing baseline is explicitly the running CD executable.

Machine-readable results are in `docs/validation/dos-timing-v4.json`, `dos-walk12.csv`, `dos-walk24.csv`, `movement-v4-*.json`, and `release-v4-ntsc-edward-near.json`. The original-DOS traces measure key timestamps; native traces measure actual cartridge state from its ELF-discovered debug address. Diagnostic publication follows completed draws and can lag input by one render.

## Retained renderer validation

The renderer, eye primitive and foreground optimization implementation is unchanged from revision 3. That revision established 966 exact pixel/palette comparisons with the corrected-eye, pre-optimization renderer, including both characters and near-plane clipping. It also checked the 320×224 identity line table, 320×200 logical target, source backgrounds/title, border-only FPS overlay, camera changes, stable pause and PAL/NTSC clock handling. Those historical results and stage profiles remain in `validation/` and `PERFORMANCE.md`; they have not all been rerun for this timing-only change. The two-second native revision-4 captures for both protagonists were inspected.

## Artifact identity

Release ROM: 720,896 bytes; checksum `0x58AE`.

SHA-256: `46dd8db9e9aa7cadaae2cb68b2caaf42f24437cacf546bff16ee43b2c69edd00`

Asset bank SHA-256: `c257542990a41792910f6d542eee040a8aefe985e9ab1801e31dfda67db12213` (unchanged).

SH-2 module: 19,556 bytes; BSS: 78,404 bytes; SDRAM static working set: 97,960 bytes, ending at `0x06017EA8`. The linker enforces the existing stack reservations.

## Limits

No physical 32X test has been performed. Original controller turn acceleration, complete movement state-machine behavior and collision sliding parity still require validation. This correction establishes the original animation time scale and retains its imported root values; it does not establish complete game parity.

LIFE/track execution, object activation, multiple actors, inventory, puzzles, combat, room/floor transitions, cutscenes, audio, saving and completion of the game remain absent. Converted object/script resources are not an implemented script VM. The full milestone exit conditions in the supplied technical plan remain open.
