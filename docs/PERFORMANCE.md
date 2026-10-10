# Revision 15

See [revision 15 validation](validation/v15-validation.md) for sound-command fixes, original music-cue mapping, native sound levels, document rendering and save compatibility. No new gameplay FPS benchmark is claimed for this revision. Historical measurements below remain version-specific.

# Revision 14 audio/save performance — 2026-10-07

Stock PicoDrive DRC_SH2, RELEASE, default clocks. Controller actions execute normal gameplay after diagnostic placement. Music 0 is enabled through the normal SH2/68000 request path for the two five-second scene measurements. These are focused emulator measurements.

| Check | V13 reference | V14 |
|---|---:|---:|
| Settled hallway camera 2, music enabled in v14 | 20 FPS | 20.0 FPS |
| Sustained chest pushing, music enabled in v14 | 11.8 FPS | 11.8 FPS |
| Sofa room → hall initial presentation gap | 216.7 ms | 216.7 ms |
| Next required rebuild gap | 233.3 ms | 233.3 ms |
| Delayed redundant cache rebuild | Removed | Absent |

The hallway advances exactly 25 world ticks/s; the pushing sample advances 24.95 ticks/s over its presentation-bounded window. End positions and cache rebuild counts match the stable behavior. Adding audio does not remove the two remaining initial transition gaps or improve pushing speed. Sound activity can use some slave CPU time; this report covers these measured fixtures rather than every effect/room combination.

PCM decoding runs at 8 kHz through the slave PWM interrupt, including during rasterization. Music commands run on the 68000 once per VBlank with a 58.8 Hz rational driver clock. Both regions pass sample/track timing checks. No runtime OPL emulation is used. The scene images remain raw. Identical resource blocks share ROM storage, making room for about 648 KB of effects and 360 KB of music command streams inside a 3.75 MiB cartridge.

Save/load intentionally pauses gameplay while transferring SRAM through COMM0/1. The first tested save completes in roughly two seconds in NTSC and PAL. Existing-record checks, larger saves and loading can take longer. The screen reports GAME SAVED after readback validation. Gameplay clock accumulation is reset once after a transaction, so time spent saving/loading cannot advance the player on Resume. Music is held while SRAM is mapped; the PWM interrupt remains independent.

Reports: `validation/v14-audio-hall2.json`, `validation/v14-audio-chest.json`, `validation/room-transition-v14-ntsc.json`, `validation/audio-save-native-*.json` and `validation/audio-streams-*.json`. Physical hardware has not been measured. V13's detailed transition investigation is preserved in PERFORMANCE-v13.md.
