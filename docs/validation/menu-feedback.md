# Native messages, pickups and menu response

Information text now uses one shared original overlay: centered at (160,184),
font color 16, directly over the scene. Gameplay no longer draws the additional
gold message bezel. Arrival and death call the same renderer. Original casing,
glyphs, simulation-based expiration and serialized message fields are retained.
All 204 imported strings fit within the scene; "You feel weak" is record 106.
Current drawing paths were mutually exclusive; the requested framed gameplay
presentation has been removed rather than adding a second message mechanism.

Pickups restore the original `FoundObjet` layout: black surround, centered
240×120 gold panel at (40,40), rotating original found-body model, and
Leave/Take choices. Left/Right selects; A confirms, with Take selected initially;
B/C leaves directly. Original projection (300×298), center (160,100) and
15000-unit orbit are preserved. Taking dispatches existing found LIFE; leaving
retains its existing debounce. A saved pending pickup resumes after closing
the load pause menu. Presentation choices are excluded from saves.

## Shared performance changes

Inventory and pickup content formerly went through framebuffer composition,
full framebuffer readback and immediate full upload. `BackgroundComposition`
now redirects fixed-panel/text drawing into the existing RAM background and
merges its changed area into both physical framebuffer damage histories.
No new bitmap buffer or global state is allocated. Animated previews retain
their original independent 60 Hz orbit clock and 30 FPS presentation cap.
Inventory ignores navigation that does not actually change its content.
Gold inventory/pickup frames decode only on entering; subsequent choices clear
and replace the interior labels while retaining the frame pixels.

The start-menu bezel is cached on entering. Subsequent startup option changes
restore only damaged pixels; character frames retain their underlying portrait
image. Biographies cache the framed portrait once. Pause captures the room once; later changes compose only its opaque
panel in RAM. Full-width RAM images use the contiguous byte decoder instead of
framebuffer read/modify/write literals. Reading pages compose on opening/paging and retain
idle pixels. Closing these screens invalidates the scenery bake and restores
the original room on both banks.

Shared LZ4 decoding fills constant offset-one matches directly. Even-offset
matches on even-width/stride targets copy pairs of pixels, splitting at both
source and destination row boundaries. Sequential stores preserve overlapping
matches. Odd widths/offsets keep the byte path. RAM matches copy sequentially
without per-pixel renderer calls. All compressed image/panel paths benefit.

Presentation edges dispatch from coherent controller snapshots without waiting
for the next simulation update. Each edge is consumed once. World and
arrival/death scripts remain at 25 Hz; animation/presentation timing remains
independent. Save/load continues to discard blocked wall time before resuming.

## ROM and memory

- ROM: **5,373,952 bytes (5.125 MiB)**, unchanged padded size. SHA-256
  `96124b1276b812448425657b98ee13f8b81798e72e652ccd22ff8cc82c3af607`.
- Bank: **2,053 IDs**, 5,224,474 logical bytes. SHA-256
  `f1d333c0723c17b1544f5ed4e3b016e2e947c0f2e6f54fb1d5e50266464935d3`.
- All 2,052 preceding IDs and their payloads are unchanged. The appended
  pickup panel is **1,155 packed / 28,804 unpacked bytes**.
- Fixed assets: **3,911,420 bytes**, **+1,172** including directory/padding.
  Extra banked images: **1,161,242 bytes**, unchanged.
- BIOS module: **83,108 bytes**, **−272**; source **4,042,492** is longword
  aligned. Physical end **4,125,600**, **68,704 bytes** remain below 4 MiB.
- BSS: **160,176 bytes**, unchanged. Static SDRAM ends at **`0x0603B658`**,
  leaving **2,472 bytes** before the unchanged master/slave stack reserves.

The importer pads the fixed bank end to four bytes, including when its final
compressed payload has an odd size. Both linker and linked-layout check reject
an unaligned BIOS module source. This was caught by native startup validation.
Save schema and fingerprint `0x0eebc721` are unchanged.

## Focused checks

```sh
make assets
make -j2 all host build/check_decode
./build/check_decode
python3 tools/check_bank_layout.py --output build/menu-feedback-layout.json
python3 tools/check_pickup.py
python3 tools/check_menu_messages.py
python3 tools/check_menu_latency.py .local/tools/picodrive_libretro.so
```

Host checks cover both characters, the single unframed weak message, native
position/color, paused world, all pickup controls, 58 distinct 3D poses, a
saved pending prompt, reading pagination, and both framebuffer restorations.
Decoder fixtures independently cover aligned/unaligned output, zero pixels,
offset-one fills, offset-two overlap, offset-3200 paired copies, odd/even widths,
row padding and bounds. Linked layout and `git diff --check` pass.

PicoDrive libretro NTSC/PAL controller-to-visible measurements, in emulated
milliseconds (ranges across both regions and sampled directions):

| Screen | Before | After |
| --- | ---: | ---: |
| Start menu | 150–180 | 40–50 |
| Character selection | 440–467 | 60–67 |
| Pause options | 100–120 | 60–67 |
| Inventory object | 660–760 | 100–117 |
| Object actions | 740–767 | 117–120 |
| Pickup Leave/Take | — | 83–100 |
| Biography paging | — | 80–100 |
| Reading pages | — | 117–200 |

The original release did not have the new pickup layout. Biography/reading
were not sampled in that before report; an intermediate measurement retained
under `build/menu-latency-interim.json` had reading at 300–400 ms before direct
RAM decoding. These are sampled presentation latencies, not hardware results
or a worst-case bound for every model/document. World ticks remain frozen in
all these menus. Alternating character screens match all 64,000 scene pixels
of the original composition in both framebuffer banks, with mapper bank 1
restored. The independent 25 Hz world and 60 Hz preview clocks are retained.
All 15 biography pages and four pages of BOOK_2 also match the preceding
release pixel for pixel across both banks. Reading fixtures enter through a
paused menu before injecting private book state, avoiding a race with an
unfinished gameplay draw; normal LIFE requests mark their draw dirty directly.

Before/after PicoDrive menu measurements are retained under ignored
`build/menu-latency-{before,after}.json`; host evidence is in
`build/pickup-check/` and `build/menu-message-check/`, with layout/build logs
under `build/`. Fixtures use only private host/emulator memory. No original
resources, frontend battery saves or `.local/baseline` were changed. These are
host/emulator checks; physical 32X hardware remains unvalidated. No commit
was made.
