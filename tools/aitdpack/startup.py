"""Original AITD1 startup resources and bounded, lossless image encoders.

Presentation screens use LZ4. All camera backgrounds stay raw for fast
restores and original foreground-mask sampling, including banked intro views.
The block encoder is deterministic and needs no optional Python package.
"""
from collections import defaultdict, deque
import hashlib
import struct

BANK_PHYSICAL_BASE = 0x20000
BANK_EXTRA_ORIGIN = 0x400000 - BANK_PHYSICAL_BASE
BANK_PAGE_BYTES = 0x80000
BANK_APERTURE = (0x80000, 0x100000)
# Leave space for the BIOS-loaded SH2 module after the immutable asset bank.
# The linked-layout check remains authoritative for the actual module size.
BANK_MODULE_RESERVE = 0x18000
INTRO_CAMERAS = {2: (28, 37), 3: (0, 1, 2, 3, 17), 7: (0, 1, 2, 3, 4)}
DEATH_CAMERAS = (0, 8, 13)


def lz4_block(data):
    """Encode a standard raw LZ4 block, with its required final literal bytes."""
    output = bytearray()
    positions = defaultdict(lambda: deque(maxlen=64))
    anchor = position = 0
    size = len(data)

    def extension(length):
        while length >= 255:
            output.append(255)
            length -= 255
        output.append(length)

    def sequence(end, distance=0, match=0):
        literals = end - anchor
        output.append((min(literals, 15) << 4) | min(max(0, match - 4), 15))
        if literals >= 15:
            extension(literals - 15)
        output.extend(data[anchor:end])
        if match:
            output.extend(struct.pack('<H', distance))
            if match - 4 >= 15:
                extension(match - 19)

    while position <= size - 12:
        best = distance = 0
        key = data[position:position + 4]
        for previous in reversed(positions[key]):
            if position - previous > 65535:
                break
            length = 4
            while position + length < size - 5 and data[position + length] == data[previous + length]:
                length += 1
            if length > best:
                best, distance = length, position - previous
            if position + length == size - 5:
                break
        if best >= 4:
            sequence(position, distance, best)
            advance = best
        else:
            advance = 1
        for entry in range(position, position + advance):
            if entry + 4 <= size:
                positions[data[entry:entry + 4]].append(entry)
        position += advance
        if best:
            anchor = position
    sequence(size)
    encoded = bytes(output)
    if decode_lz4(encoded, size) != data:
        raise ValueError('LZ4 image round-trip failed')
    return encoded


def decode_lz4(data, expected):
    """Independent bounded importer check, including overlapping matches."""
    output = bytearray()
    position = 0

    def length(value):
        nonlocal position
        if value == 15:
            while True:
                if position >= len(data):
                    raise ValueError('truncated LZ4 length')
                extra = data[position]
                position += 1
                value += extra
                if extra != 255:
                    break
        return value

    while position < len(data):
        token = data[position]
        position += 1
        literals = length(token >> 4)
        if position + literals > len(data) or len(output) + literals > expected:
            raise ValueError('invalid LZ4 literals')
        output.extend(data[position:position + literals])
        position += literals
        if position == len(data):
            break
        if position + 2 > len(data):
            raise ValueError('truncated LZ4 distance')
        distance = int.from_bytes(data[position:position + 2], 'little')
        position += 2
        match = length(token & 15) + 4
        if distance == 0 or distance > len(output) or len(output) + match > expected:
            raise ValueError('invalid LZ4 match')
        for _ in range(match):
            output.append(output[-distance])
    if len(output) != expected:
        raise ValueError('invalid LZ4 output size')
    return bytes(output)


def panel_rle(data, encode):
    width, height = struct.unpack_from('>HH', data)
    pixels = data[4:]
    if len(pixels) != width * height:
        raise ValueError('invalid panel image')
    packed = encode(pixels)
    restored = bytearray()
    for position in range(0, len(packed), 2):
        count, color = packed[position:position + 2]
        if not count:
            raise ValueError('empty panel run')
        restored.extend(bytes((color,)) * count)
    if restored != pixels:
        raise ValueError('panel RLE round-trip failed')
    return data[:4] + packed


def encoded_panel(data, encode):
    """Keep dimensions raw; use the smaller independently checked pixel codec."""
    rle = panel_rle(data, encode)
    lz4 = data[:4] + lz4_block(data[4:])
    return (rle, 3) if len(rle) <= len(lz4) else (lz4, 4)


def arrival_room(data, native_room, cameras):
    """Keep original room coordinates/boxes and only available intro cameras."""
    original = native_room(data)
    count, hard_count, scenario_count = struct.unpack_from('>3H', original, 6)
    camera_offset, hard_offset, scenario_offset = struct.unpack_from('>3I', original, 12)
    selected = [camera for camera in struct.unpack_from('>' + str(count) + 'H', original, camera_offset)
                if camera in cameras]
    output = bytearray(original[:32])
    def append(payload):
        output.extend(bytes((-len(output)) % 4))
        position = len(output)
        output.extend(payload)
        return position
    camera_offset = append(struct.pack('>' + str(len(selected)) + 'H', *selected))
    hard_offset = append(original[hard_offset:hard_offset + hard_count * 16])
    scenario_offset = append(original[scenario_offset:scenario_offset + scenario_count * 16])
    struct.pack_into('>H', output, 6, len(selected))
    struct.pack_into('>3I', output, 12, camera_offset, hard_offset, scenario_offset)
    return bytes(output)


def compile_startup(get, defines_data, native_model, native_room, native_camera, offsets, native_panel, rle, native_text):
    from books import Font, layout
    assets, provenance = [], []

    def add(name, kind, data, pak, index, original, flags=0, unpacked=None):
        assets.append((name, kind, data, len(data) if unpacked is None else unpacked, flags))
        provenance.append(dict(name=name, source=f'{pak}:{index}',
                               source_sha256=hashlib.sha256(original).hexdigest(),
                               source_bytes=len(original), packed_bytes=len(data),
                               unpacked_bytes=assets[-1][3], flags=flags))

    logo = get('ITD_RESS', 0)
    add('STARTUP_LOGO_MODEL', 5, native_model(logo), 'ITD_RESS', 0, logo)
    palette = get('ITD_RESS', 1)
    if len(palette) != 768:
        raise ValueError('invalid startup logo palette')
    palette16 = b''.join(struct.pack('>H', (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10))
                         for r, g, b in zip(palette[::3], palette[1::3], palette[2::3]))
    add('STARTUP_LOGO_PALETTE', 1, palette16, 'ITD_RESS', 1, palette)
    for name, index in [('STARTUP_LOGO_IMAGE', 2), ('STARTUP_SELECTION', 10),
                        ('STARTUP_BACKGROUND', 14), ('STARTUP_PICTURE', 11)]:
        original = get('ITD_RESS', index)
        pixels = original[770:] if index == 2 else original
        if len(pixels) != 64000 or (index == 2 and original[:2] != b'VP'):
            raise ValueError(f'invalid startup image {index}')
        add(name, 2, lz4_block(pixels), 'ITD_RESS', index, original, 0x8002, len(pixels))
    defines = struct.unpack('>45h', defines_data)
    font = Font(get('ITD_RESS', 5))
    graphics = get('ITD_RESS', 9)
    biographies = []
    for character, define, rectangle in [(0, 5, (5, 5, 154, 194)),
                                         (1, 6, (165, 5, 314, 194))]:
        index = defines[define] + 1
        original = get('ENGLISH', index)
        commands, pages = layout(original, 1, font, graphics, rectangle)
        add(f'STARTUP_BIOGRAPHY_{character}', 17, commands, 'ENGLISH', index, original)
        biographies.append(dict(character=character, text=index, rectangle=rectangle, pages=pages))
    bezel = get('ITD_RESS', 4)
    for name, width, height in [('UI_STARTUP_MENU', 320, 80), ('UI_STARTUP_SELECTION', 160, 200)]:
        data = native_panel(bezel, width, height)
        packed, flags = encoded_panel(data, rle)
        add(name, 13, packed, 'ITD_RESS', 4, bezel, flags, len(data))
    levels = {}
    for floor, cameras in INTRO_CAMERAS.items():
        counts = []
        for kind, entry, convert in [('ROOM', 0, native_room), ('CAMERA', 1, native_camera)]:
            source = get(f'ETAGE{floor:02}', entry)
            entries = offsets(source)
            counts.append(len(entries))
            for index, position in enumerate(entries):
                if kind == 'CAMERA' and index not in cameras and floor != 7:
                    continue
                end = entries[index + 1] if index + 1 < len(entries) else len(source)
                original = source[position:end]
                native = arrival_room(original, native_room, cameras) if kind == 'ROOM' else convert(original)
                add(f'{kind}_{floor}_{index}', 4 if kind == 'ROOM' else 3,
                    native, f'ETAGE{floor:02}', entry, original)
        levels[floor] = tuple(counts)
        for index in cameras:
            original = get(f'CAMERA{floor:02}', index)
            if len(original) != 64000:
                raise ValueError('invalid original arrival background')
            # Hold the raw mapped source during a scene draw so masks sample
            # immutable scenery while the existing RAM background is baked.
            add(f'BACKGROUND_{floor}_{index}', 2, original, f'CAMERA{floor:02}', index,
                original, 0x8000)
    # Retain the presentation table's existing ID; its original-glyph payload
    # now deduplicates with the gameplay table.
    original = get('ENGLISH', 0)
    add('STARTUP_TEXT', 12, native_text(original, original_font=True), 'ENGLISH', 0, original)
    # Append new gameplay presentation resources after the complete startup
    # bank so existing IDs and save-linked models/animations stay unchanged.
    from gameplay_ui import compile_gameplay_ui
    inventory_assets, inventory_report = compile_gameplay_ui(get, encoded_panel, rle)
    assets.extend(inventory_assets)
    death_counts = []
    for kind, entry, convert in [('ROOM', 0, native_room), ('CAMERA', 1, native_camera)]:
        source = get('ETAGE06', entry)
        entries = offsets(source)
        death_counts.append(len(entries))
        for index, position in enumerate(entries):
            if kind == 'CAMERA' and index not in DEATH_CAMERAS:
                continue
            end = entries[index + 1] if index + 1 < len(entries) else len(source)
            original = source[position:end]
            native = arrival_room(original, native_room, DEATH_CAMERAS) if kind == 'ROOM' else convert(original)
            add(f'{kind}_6_{index}', 4 if kind == 'ROOM' else 3,
                native, 'ETAGE06', entry, original)
    levels[6] = tuple(death_counts)
    for index in DEATH_CAMERAS:
        original = get('CAMERA06', index)
        if len(original) != 64000:
            raise ValueError('invalid original death background')
        add(f'BACKGROUND_6_{index}', 2, original, 'CAMERA06', index, original, 0x8000)
    original = get('ITD_RESS', 12)
    if len(original) != 64000:
        raise ValueError('invalid original death picture')
    add('DEATH_PICTURE', 2, lz4_block(original), 'ITD_RESS', 12, original, 0x8002, len(original))
    # Keep every existing gameplay/startup/death ID stable.
    from gameplay_ui import compile_pickup_ui
    pickup_asset, pickup_report = compile_pickup_ui(get, encoded_panel, rle)
    assets.append(pickup_asset)
    inventory_report['pickup'] = pickup_report
    return assets, levels, dict(sequence=['logo', 'title', 'credits', 'menu', 'selection',
                                               'biography', 'scripted_floor_7_arrival', 'gameplay'],
                                      credits_text=defines[3] + 1, biographies=biographies,
                                      arrival_cameras=INTRO_CAMERAS,
                                      death_cameras=DEATH_CAMERAS,
                                      death_picture='ITD_RESS:12',
                                      gameplay_ui=inventory_report,
                                      startup_text_case='original ENGLISH:0 casing and glyph bytes shared with gameplay TEXT',
                                      resources=provenance,
                                      image_encoding='standard raw LZ4 block, asset flag 2',
                                      arrival_image_encoding='raw 64,000-byte image, banked asset flag 0x8000',
                                      panel_encoding='raw BE16 dimensions plus count/color RLE (flag 3) or raw LZ4 (flag 4)')


def build_bank(assets):
    """Keep rendering/audio resources fixed and page-isolate banked images."""
    main = bytearray(16 + len(assets) * 16)
    if BANK_PHYSICAL_BASE + len(main) > BANK_APERTURE[0]:
        raise ValueError('asset directory overlaps mapper aperture')
    extra = bytearray()
    struct.pack_into('>4s3I', main, 0, b'A32X', 2, len(assets), 0)
    shared, manifest = {}, []
    for index, (name, kind, data, unpacked, flags) in enumerate(assets):
        # Keep every immutable fixed payload outside the temporary window, so
        # a camera mapping can safely survive script/audio/UI work as well.
        protected = not flags & 0x8000
        key = (kind, flags, data)
        offset = shared.get(key)
        if offset is None:
            if flags & 0x8000:
                if kind not in (2, 19) or flags not in (0x8000, 0x8002) or unpacked != 64000 or (kind == 19 and flags != 0x8000):
                    raise ValueError(f'unsupported banked image: {name}')
                if kind == 2 and flags == 0x8000 and len(data) != unpacked:
                    raise ValueError(f'invalid raw banked image: {name}')
                if len(data) > BANK_PAGE_BYTES:
                    raise ValueError('banked payload exceeds one mapper page')
                extra.extend(bytes((-len(extra)) % 4))
                remaining = BANK_PAGE_BYTES - (len(extra) % BANK_PAGE_BYTES)
                if len(data) > remaining:
                    extra.extend(bytes(remaining))
                offset = BANK_EXTRA_ORIGIN + len(extra)
                extra.extend(data)
            else:
                main.extend(bytes((-len(main)) % 4))
                physical = BANK_PHYSICAL_BASE + len(main)
                if protected and physical < BANK_APERTURE[1] and physical + len(data) > BANK_APERTURE[0]:
                    # A camera can remain mapped while either SH2 reads any
                    # floor's geometry, masks, poses, drawing programs or audio.
                    main.extend(bytes(BANK_APERTURE[1] - physical))
                offset = len(main)
                main.extend(data)
            shared[key] = offset
        # Rendering can hold slot 1 mapped until both SH2 row jobs complete.
        # Every source accessed then must remain in an unchanged ROM window.
        physical = BANK_PHYSICAL_BASE + offset
        if protected and physical < BANK_APERTURE[1] and physical + len(data) > BANK_APERTURE[0]:
            raise ValueError(f'rendering resource is not fixed outside mapper aperture: {name}')
        struct.pack_into('>3I2H', main, 16 + index * 16, offset, len(data), unpacked, kind, flags)
        manifest.append(dict(id=index, name=name, offset=offset, packed_size=len(data),
                             unpacked_size=unpacked, type=kind, flags=flags))
    # The BIOS copies the module immediately following this bank in longwords.
    # A final compressed asset may have an odd byte length; align the bank end
    # as well as each payload so every cartridge has an aligned module source.
    main.extend(bytes((-len(main)) % 4))
    if len(main) > BANK_EXTRA_ORIGIN:
        raise ValueError('fixed assets exceed the direct ROM area')
    size = BANK_EXTRA_ORIGIN + len(extra) if extra else len(main)
    struct.pack_into('>I', main, 12, size)
    full = main + bytes(BANK_EXTRA_ORIGIN - len(main)) + extra if extra else main
    layout = dict(physical_base=BANK_PHYSICAL_BASE, fixed_bytes=len(main),
                  fixed_physical_end=BANK_PHYSICAL_BASE + len(main), extra_origin=BANK_EXTRA_ORIGIN,
                  extra_physical_origin=0x400000, extra_bytes=len(extra), page_bytes=BANK_PAGE_BYTES,
                  banked_payloads=sum(bool(flags & 0x8000) for _, _, _, _, flags in assets))
    return bytes(full), bytes(main), bytes(extra), manifest, layout
