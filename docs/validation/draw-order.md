# Shared draw-order repairs — 2026-10-11

The complete-house build had shared actor-order and scenery-composition defects.
The repairs apply through the common scene pipeline across the game. Distance
alone cannot order intersecting polygons, so ordinary painter order, original
camera masks and the existing bounded contact-depth pass remain separate.

This report describes the first repair stage. Subsequent user-reported poses
revealed additional visibility defects; [window/door validation](window-door.md)
records their fixes and supersedes the ROM/layout figures below.

## Demonstrated defects and repairs

- The pair-dependent distance comparator can form cycles. Insertion sorting
  then violates even its separated camera-depth relationships. Floor 3 camera
  19 showed doors 139/140 before farther prop 145 or the player. A stable graph
  pass now honors separated depth ranges across the complete actor list and
  retains compatible vertical/hatch precedence. Ambiguous vertical cycles break
  deterministically; equal degenerate planes retain stable ties. Existing
  heuristic order remains the preference where constraints allow it. An already
  valid list skips graph selection.
- Cached foreground actors restored their colored silhouettes but omitted
  architectural background erasures. Original dining-room placement
  `floor 1, room 4, camera 6, player (-700,0,-2700)` produced 1,148 incorrect
  pixels. Cached replay now applies both spans and original masks, clipped to
  the overwritten region. It also handles empty silhouettes and black pixels.
- Contact correction redrew an intermediate object over a nearer member of
  the depth group. An original attic item/chest fixture reproduced 62 promoted
  pixels for Edward and 42 for Emily. Intervening screen-overlapping actors
  now join the same painter interval before depth correction; only models after
  its final rank replay afterward.
- Full foreground/fallback draws can write beyond a contact rectangle. Later
  actors now repair their entire expanded write footprint. A floor 3 camera 22
  fixture verifies that four pixels outside the contact area retain the ordinary
  painter result, rather than merely making two faulty paths agree.

No resource, simulation or save-schema change is part of these repairs. The
25 Hz world and independent 60 Hz animation clock retain their implementation.
The master/slave row ownership, contact fences and audio interrupt behavior
remain unchanged. No global bitmap, full-screen depth buffer or heap is added.

## Focused checks

```sh
make -j2 host all
python3 tools/check_world_order.py --reference build/draw-order-reference
python3 tools/check_draw_order_cache.py --sweep
python3 tools/check_contact_order.py
python3 tools/check_partial_cache.py
python3 tools/check_bank_layout.py
python3 tools/check_draw_order_native.py .local/tools/picodrive_libretro.so --region NTSC
python3 tools/check_draw_order_native.py .local/tools/picodrive_libretro.so --region PAL
```

| Check | Result and scope |
|---|---|
| World constraints | Both characters, all 144 cameras, 2,780 sampled room/view/position cases and 99,856 separated-depth constraints pass; ten explicit door/prop/player fixtures pass. The preserved preceding library violated 15,686 constraints in 1,003 cases. Collision bounds are the ordering inputs, not an independent polygon-visibility oracle. |
| Cached/uncached scene parity | 2,648 sampled comparisons across all 144 cameras and both characters pass with original flags. The oracle shares actor order, masks, contacts, effects and lighting, but makes every actor dynamic. Sixty focused mask/contact-footprint comparisons also pass. |
| Contact interval | 64 comparisons with both characters, both framebuffer histories, cached/full drawing, original colors and private ownership-color copies pass against a three-model reciprocal-depth oracle. The preceding path differed on 12,568 total pixels. |
| Partial scenery rebuilds | Forced-full-rebuild comparison passes both character routes and reversed static ordering, black/glass/masks, geometry invalidation and both buffer histories. The fixture now uses direct gameplay startup and all 50 cache slots. |
| Previous hallway/hatch scenes | Twelve focused host comparisons pass for both characters/banks: hallway door before player and hatch angles 400/700, compared with local depth and fresh cache rebuilds. |
| NTSC/PAL cartridge | Six frozen scenes per region, both characters: original dining-room masks, floor-3 foreground doors and attic contact item. Both physical framebuffer banks match loaded host scene pixels exactly. Each emulator fixture uses a fresh process and private SRAM. |
| Linked layout | Fixed ROM/mapped pages, code/audio protection, checksum, module and SDRAM limits pass. |

Reports remain in ignored `build/`: `world-order.json`, `draw-order-cache.json`,
`draw-order-cache-focused.json`, `contact-order-{before,after}.json`,
`partial-cache-parity.json`, `reported-order.json`,
`draw-order-native-{NTSC,PAL}.json`, and `bank-layout.json`.
Original resources, user battery files and `.local/baseline` were not modified.
The pre-repair ROM/ELF/library remain in `build/draw-order-reference/`.

The historical full `check_reported_bugs.py` does not currently pass with the
complete-game startup/interaction fixtures. Its unchanged startup no longer
enters gameplay; an attempted direct-start adaptation reached an unrelated
chest interaction assertion. That adaptation was reverted. The rendering
portion was checked separately with current direct-start fixtures, as above.
This report does not claim a pass for that historical full script.

## Performance and build

Ten-second early-game controller traces on the preserved/current ROMs retain
24.3 draws/s in NTSC and 24.2 in PAL. Both runs advance 252/251 world ticks
respectively; the NTSC simulation/animation segment trace is identical. PAL
controller edges land one update apart at some render boundaries, so exact PAL
pose/animation trace equality is not claimed. The rendering changes do not
modify world-update or animation-clock code.

The floor-3 entrance fixture `(room 1, camera 3)` also retains its preceding
rates: frozen rendering 29 draws/s NTSC and 24 PAL; the initial one-second live
sample is 10 draws/s in each region. Those short cold-room samples still show
the existing animated entrance bottleneck. These measurements establish no
observed draw-rate loss in the sampled cases, not performance across a full
playthrough. Evidence is `draw-order-performance.json` and
`draw-order-busy-performance.json`.

The RELEASE ROM remains 14,155,776 bytes / 13.5 MiB. SHA-256:
`35bd332fa0e777ca30666212dfbb513aa7c96b7f9093873a90e311a53dc203f0`;
checksum `A228`. The asset bank is unchanged from the complete-game snapshot:
`d9ee34b9b1dd1b4ea6d52854fb1a99ebd95b6c48e39006ff6e82b1e9d6762c55`.

The BIOS-loaded module is 84,964 bytes, 704 bytes larger. BSS remains 160,640
bytes. Static SDRAM ends at `0x0603BF68` / 245,608 bytes, leaving only 152 bytes
below the reserved stacks. The new graph workspace is 400 temporary stack
bytes; its helper is explicitly kept out of line in protected ROM to avoid
consuming SDRAM for that code. The module ends at physical ROM byte 4,180,908,
leaving 13,396 bytes below the direct 4 MiB boundary. Linker budget assertions
pass; the existing freestanding RWX LOAD warning remains. Future changes must
measure these tight budgets.

## Limits

The sweeps sample original initial world states and selected overlap poses;
they do not prove every animation/model/camera has original DOS visibility.
Single model primitive sorting remains a stable maximum-vertex-depth painter
sort. Concave/interpenetrating geometry can have visibility cycles that no
single distance key solves. Contact groups still have a 768-vertex limit;
larger groups retain ordinary painter order. Cinematic scenes retain their
existing contact-depth bypass. Full manual playthrough and physical 32X
validation remain necessary; all native results here are PicoDrive evidence.
