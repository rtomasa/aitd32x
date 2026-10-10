# Revision 15

See [revision 15 validation](validation/v15-validation.md) for sound-command fixes, original music-cue mapping, native sound levels, document rendering and save compatibility. No new gameplay FPS benchmark is claimed for this revision. Historical measurements below remain version-specific.

# Revision 14 validation

Release ROM SHA-256: `d0529b3f4b19bfa301438844d20f4f8a9d7c737d51f24a01e96af3167a45a3ad`. ROM 3,932,160 bytes (3.75 MiB), checksum 18D2. Bank 3,788,160 bytes, SHA-256 `0e6a3f1321223eebd7ab7e449a263e7fe34215660a2ae80394217ed6a2871f65`, 1,957 native assets. Module 85,252 bytes, BSS 160,120, static SDRAM end 0x0603BE80: 384 bytes below the unchanged 12 KiB master / 4 KiB slave stack reservation. Native linker assertions pass.

Focused checks completed on the release:

- Both characters: save/load round trips restore all world/object/variable/inventory data. Re-saving without advancing simulation produces identical payload bytes, covering RNG, active actor transient state, animation bones/phases and effects. Damaging the newest committed record restores the previous valid one. A title load reconstructs character/floor/resource pointers. Invalid saves fail without changing gameplay state.
- Full 24-slot actor pool with the largest imported 28-bone model: 45,207-byte payload fits the 65,512-byte journal payload limit and round-trips byte for byte.
- Stock PicoDrive NTSC and PAL: controller input saves to 128 KiB cartridge SRAM, the emulator core is closed/reinitialized, the frontend-provided SRAM is restored, and title B loads the original position and world variable. Loading pauses gameplay; Resume works. Actual walking triggers original effects. Native menu/copyright/pickup/inventory/action/book/death/error checks preserve bezels and four black pixels of text padding; native title/inventory/action/pause cover both framebuffer banks.
- Each of the eight imported ADLM tracks produces native audio and reaches its end at the expected duration in both regions while gameplay/rendering is paused. PWM effect 0 advances about 4,000 samples in half a second, consumes exactly 6,600 samples and stops. Checks use chip/voice state as well as audio, separating FM playback from sampled effects. First-six-second music peaks remain below clipping after mix headroom adjustments; this is not a complete subjective listening review.
- Original reported vase/key, dog departure/death, zombie death particles and hallway camera cases still pass for both characters in the host engine after wiring sound opcodes.
- Exact framebuffer/selected-state parity against v13 on 345 route frames per character, 690 total. All 216 deduplicated prepared-prop keys pass two bounds modes, 432 exact pixel/coverage/bounds comparisons, plus three relocated/rotating fallback poses. Duplicate imported payloads share storage; prior payloads are unchanged except the enlarged pause panel and regenerated raster keys.
- Actual-ROM hallway and pushing measurements with music enabled retain 20.0 and 11.8 FPS respectively. The sofa-to-hall route retains its two 216.7/233.3 ms initial gaps and no delayed redundant rebuild. See PERFORMANCE.md for scope.

The standalone source archive excludes original converted asset banks and compiled products. The release requires regeneration from the supplied original installation. A clean import/build comparison is recorded in `validation/rebuild-v14.json`.

AdLib OPL2 and YM2612/PSG have different operators, waveforms and voice layouts. The eight songs are musical adaptations: FM envelopes/waveforms and PSG percussion/auxiliary voices differ from the PC. Some low PSG notes are raised by octaves. Effects are lossy 8 kHz IMA ADPCM. Saves preserve gameplay and queued music context, but restart the current song and clear active sample voices. One visible save slot is backed by two journals; PC save files are not imported. The native restart check exercises battery RAM persistence through the core's frontend API, not a particular GUI frontend's disk-save settings.

Floors 0 and 1 remain the implemented scope. Full-house progression, complete PC audiovisual fidelity, every sound/room combination and physical hardware validation remain unfinished. Prior versioned reports remain historical evidence.
