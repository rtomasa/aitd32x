"""Complete original floor resources without changing established asset IDs."""
import hashlib
import struct


def compile_floors(assets, get, offsets, native_room, native_camera):
    """Replace cinematic subsets in place, then append absent game resources.

    Every camera stays raw and page-isolated. This keeps background repairs and
    foreground masks on the same direct-copy path throughout the house, without
    another RAM image or a decoder on room transitions.
    """
    ids = {asset[0]: index for index, asset in enumerate(assets)}
    levels, provenance = [], []

    def store(name, kind, data, pak, entry, original, flags=0):
        asset = (name, kind, data, len(data), flags)
        if name in ids:
            assets[ids[name]] = asset
        else:
            ids[name] = len(assets)
            assets.append(asset)
        provenance.append(dict(name=name, source=f'{pak}:{entry}',
                               source_sha256=hashlib.sha256(original).hexdigest(),
                               source_bytes=len(original), native_bytes=len(data),
                               flags=flags))

    for floor in range(8):
        counts = []
        for kind, entry, convert in [('ROOM', 0, native_room),
                                     ('CAMERA', 1, native_camera)]:
            pak = f'ETAGE{floor:02}'
            source = get(pak, entry)
            entries = offsets(source)
            counts.append(len(entries))
            for index, position in enumerate(entries):
                end = entries[index + 1] if index + 1 < len(entries) else len(source)
                original = source[position:end]
                store(f'{kind}_{floor}_{index}', 4 if kind == 'ROOM' else 3,
                      convert(original), pak, entry, original)
        levels.append(tuple(counts))
        for index in range(counts[1]):
            pak = f'CAMERA{floor:02}'
            original = get(pak, index)
            if len(original) != 64000:
                raise ValueError(f'{pak}:{index}: background is not 320x200')
            store(f'BACKGROUND_{floor}_{index}', 2, original, pak, index,
                  original, 0x8000)
    return levels, dict(floors=levels, rooms=sum(nr for nr, _ in levels),
                        cameras=sum(nc for _, nc in levels), resources=provenance,
                        camera_encoding='raw 64,000-byte images; one mapper page per payload',
                        asset_ids='existing IDs retained; missing resources appended')


def compile_ending(get, end_count, lz4):
    """Prepare the original ending movie as bounded native drawing spans.

    The original delta stream treats color zero as a skip, rather than black.
    Native commands retain that meaning without decoding or restoring an entire
    64,000-byte picture for each of the small early frames. Type 19 starts with a
    BE32 command count, followed by (BE16 pixel, BE16 count, color, padding).
    All writes are applied to the existing RAM background by the presentation
    renderer; no additional image buffer is required at runtime.
    """
    assets, report = [], dict(movie_frames=[], delta_format=19)

    def image(data, source):
        if len(data) != 64770 or data[:2] != b'VP':
            raise ValueError(f'{source}: invalid original VP image')
        palette = b''.join(struct.pack('>H', (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10))
                           for r, g, b in zip(data[2:770:3], data[3:770:3], data[4:770:3]))
        return palette, data[770:]

    original = get('ENDSEQ', 0)
    palette, pixels = image(original, 'ENDSEQ:0')
    assets.append(('ENDING_PALETTE', 1, palette, len(palette), 0))
    packed = lz4(pixels)
    assets.append(('ENDING_FRAME_0', 2, packed, 64000, 0x8002))
    report['movie_frames'].append(dict(index=0, source='ENDSEQ:0',
                                       source_sha256=hashlib.sha256(original).hexdigest(),
                                       packed_bytes=len(packed), changed_pixels=64000))
    previous = bytearray(pixels)
    for frame in range(1, end_count):
        source = get('ENDSEQ', frame)
        position = destination = 0
        commands = []
        while position < len(source):
            code = source[position]
            position += 1
            if code == 0:
                break
            if code in (1, 2):
                count = code
            elif code == 3:
                if position >= len(source):
                    raise ValueError(f'ENDSEQ:{frame}: truncated byte run')
                count = source[position]
                position += 1
            else:
                if position + 2 > len(source):
                    raise ValueError(f'ENDSEQ:{frame}: truncated word run')
                count = struct.unpack_from('<H', source, position)[0]
                position += 2
            if position >= len(source) or not count or destination + count > 64000:
                raise ValueError(f'ENDSEQ:{frame}: invalid delta run')
            color = source[position]
            position += 1
            if color:
                previous[destination:destination + count] = bytes((color,)) * count
                if commands and commands[-1][0] + commands[-1][1] == destination and commands[-1][2] == color:
                    start, length, _ = commands[-1]
                    commands[-1] = (start, length + count, color)
                else:
                    commands.append((destination, count, color))
            destination += count
        if destination != 64000 or position != len(source) or not source or source[-1] != 0:
            raise ValueError(f'ENDSEQ:{frame}: incomplete delta frame')
        payload = struct.pack('>I', len(commands)) + b''.join(
            struct.pack('>2H2B', start, count, color, 0) for start, count, color in commands)
        assets.append((f'ENDING_FRAME_{frame}', 19, payload, 64000, 0x8000))
        report['movie_frames'].append(dict(index=frame, source=f'ENDSEQ:{frame}',
                                           source_sha256=hashlib.sha256(source).hexdigest(),
                                           native_bytes=len(payload), commands=len(commands),
                                           changed_pixels=sum(count for _, count, _ in commands),
                                           decoded_sha256=hashlib.sha256(previous).hexdigest()))
    return assets, report
