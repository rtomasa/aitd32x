# AITD32X revision 15 validation

ROM SHA-256: `556275aae35a59cf1863d9c47f39912578912be772a749c40d17a9506857eb60`  
ROM size: 4,128,768 bytes (3.9375 MiB); checksum 7C6E.  
Asset bank: 3,976,924 bytes; 1,969 entries. SHA-256: `b1a17763e20dd481337d4495c0ee32147b08a9e474c3a4e2c122164079f97dfa`.  
SH-2 startup module: 85,108 bytes; BSS: 160,120 bytes. Static end 0x0603BDF0 leaves 528 bytes below the reserved stacks. No additional gameplay RAM was allocated.

## Window script

The preserved v14 source reproduced fault 910, LIFE 20, word 59 when the attic creature collided with object 4 at (-2840, 0, 4540). A plain monster-entry test does not reach this collision branch. Opcode 63 is SAMPLE_THEN (two evaluated operands), and opcode 75 is REP_SAMPLE (evaluated sound plus raw repeat count); v14 had their formats swapped. Opcode 78 is PICTURE with three raw operands, not 2D_ANIM_SAMPLE. Correct formats prevent the reader from crossing the end of LIFE 20. Both-character host collision tests pass; actual cartridge collision tests pass in PicoDrive NTSC and PAL. The sound chain is effect 2 followed by effect 29.

## Music and balance

The CD installation’s LIFE music numbers do not index its eight AdLib songs. The supplied floppy LIFE scripts give matching music cues: 101 paired commands establish the mapping in tools/audio/music_cues.json. CD track 12 at creature entry now plays AdLib 1; queued CD 4 returns to AdLib 0. For example, directly using CD 4 previously selected AdLib 4, causing the wrong ambient theme. CD cue numbers remain in world/save state. Cues sharing a physical theme retain the music playhead; an ended stream can restart for a new event. CD-only cues without an AdLib counterpart stop FM; their original PCM effects remain on the sound path. Later full-house/CD-only sequences are not newly implemented in this revision.

Native comparison of the same AdLib track 0 and separately isolated effect 0 measures music RMS at 0.5001× v14 and effect RMS at 1.4999× v14. These fixtures contain no clipped output samples. FM carrier total levels increase by eight steps and PSG by three steps (about -6 dB); PWM voice gain changes from 1/2 to 3/4. Summed loud simultaneous effects still use the existing saturating mixer. Stop/track-end mutes all FM operators so zero-release instruments cannot hang after key-off. Native explicit-stop checks pass.

## Original reading screens

All 21 imported documents and 166 compiled pages passed page-forward/back/limit checks. The original paper, book and notebook backgrounds, original proportional font, mixed case, centered titles, indentation, explicit page breaks, five illustrations and navigation arrows are imported from ITD_RESS. Effect 49 is the original SAMPLE_PAGE. Opening through the actual inventory READ script emits it; page-turn and closing controls also emit it. Gameplay time freezes while reading; closing restores the scene cache.

The note, Golden Fleece cover and notebook produce exact host/native pixel matches in both framebuffer banks, in NTSC and PAL. Page-turn sound is verified separately with music stopped. Captures are v15-reading-1/2/7.png. This is the original bitmap font and artwork, with offline word layout rather than a DOS renderer running on the console. CD spoken narration is not added.

## Saves and build

Existing round-trip, corruption fallback, title load and invalid-save checks pass for Edward and Emily, with all serialized payload bytes compared. A v14-generated SRAM journal loads in v15 with all 292 object records and a diagnostic variable restored. Save format and original asset IDs remain compatible. For versioned emulator ROM filenames, copy/rename the existing .srm file to the v15 filename.

A clean source-archive asset import and ROM rebuild are recorded in rebuild-v15.json. Earlier versioned deliverables remain unchanged. Physical 32X/audio hardware has not been tested. FM/PSG instruments and percussion remain adaptations of AdLib, and the port still imports floors 0 and 1.
