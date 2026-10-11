"""Original AITD1 inventory frames and scrolling arrows.

The fixed panels are precomposed offline and losslessly compressed. The item
models and palette already belong to the gameplay bank; no preview bitmap or
new model allocation is required at runtime.
"""
import hashlib
import struct

from books import sprite


def original_panel(graphics, width, height):
    """Reproduce AffBigCadre's 20-pixel tiling and original plaque position."""
    if width % 20 or height % 20 or width < 40 or height < 40:
        raise ValueError('original inventory frame must use 20-pixel tiles')
    pixels = bytearray(width * height)

    def put(index, x, y):
        w, h, image = sprite(graphics, index)
        if x < 0 or y < 0 or x + w > width or y + h > height:
            raise ValueError('original inventory sprite exceeds panel bounds')
        for row in range(h):
            start = (y + row) * width + x
            pixels[start:start + w] = image[row * w:(row + 1) * w]

    put(0, 0, 0)
    for x in range(20, width - 20, 20):
        put(4, x, 0)
    put(1, width - 20, 0)
    for y in range(20, height - 20, 20):
        put(6, 0, y)
        put(7, width - 8, y)
    put(2, 0, height - 20)
    for x in range(20, width - 20, 20):
        put(5, x, height - 8)
    put(3, width - 20, height - 20)
    put(8, width // 2 - 20, height - 8)
    # AffRect uses inclusive coordinates inside the assembled original rails.
    for y in range(8, height - 8):
        start = y * width + 8
        pixels[start:start + width - 16] = bytes(width - 16)
    return struct.pack('>HH', width, height) + pixels


def compile_gameplay_ui(get, encode_panel, rle):
    graphics = get('ITD_RESS', 4)
    assets, resources = [], []
    for name, width, height in [('UI_ORIGINAL_INVENTORY_LIST', 320, 100),
                                ('UI_ORIGINAL_INVENTORY_SECTION', 160, 100)]:
        raw = original_panel(graphics, width, height)
        packed, flags = encode_panel(raw, rle)
        assets.append((name, 13, packed, len(raw), flags))
        resources.append(dict(name=name, source='ITD_RESS:4',
                              source_sha256=hashlib.sha256(graphics).hexdigest(),
                              packed_bytes=len(packed), unpacked_bytes=len(raw),
                              flags=flags, width=width, height=height))
    for name, index in [('UI_INVENTORY_UP', 10), ('UI_INVENTORY_DOWN', 9)]:
        width, height, pixels = sprite(graphics, index)
        raw = struct.pack('>HH', width, height) + pixels
        assets.append((name, 13, raw, len(raw), 0))
        resources.append(dict(name=name, source=f'ITD_RESS:4 sprite {index}',
                              source_sha256=hashlib.sha256(graphics).hexdigest(),
                              packed_bytes=len(raw), unpacked_bytes=len(raw),
                              flags=0, width=width, height=height))
    report = dict(layout=dict(list=[0, 0, 320, 100],
                              preview=[0, 100, 160, 100],
                              actions=[160, 100, 160, 100]),
                  list_rows=5, line_height=16, resources=resources,
                  palette='GAME_PALETTE',
                  models='existing selected-character MODEL bank, object O_FOUND_BODY')
    return assets, report


def compile_pickup_ui(get, encode_panel, rle):
    """Original FoundObjet's centered 240×120 window, appended to old IDs."""
    graphics = get('ITD_RESS', 4)
    raw = original_panel(graphics, 240, 120)
    packed, flags = encode_panel(raw, rle)
    return ('UI_ORIGINAL_PICKUP', 13, packed, len(raw), flags), dict(
        name='UI_ORIGINAL_PICKUP', source='ITD_RESS:4',
        source_sha256=hashlib.sha256(graphics).hexdigest(),
        packed_bytes=len(packed), unpacked_bytes=len(raw), flags=flags,
        layout=[40, 40, 240, 120], interior=[48, 48, 271, 151],
        projection=[160, 100, 128, 300, 298], distance=15000,
        controls='Left: Leave; Right: Take; A: confirm; C/B: leave')
