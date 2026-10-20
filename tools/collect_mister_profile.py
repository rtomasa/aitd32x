#!/usr/bin/env python3
"""Collect lossless profiler screenshots through an existing SSH connection.

Authenticate separately with ssh -M -S PATH first; this tool stores no password.
It only requests screenshots and downloads its own captures. It does not load
cores, change settings, inspect arbitrary memory, or access battery files.
"""
import argparse
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path

from check_mister_profile import decode, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--ssh-control', required=True)
    parser.add_argument('--seconds', type=int, default=100)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--rom', type=Path)
    parser.add_argument('--variant', type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = args.project.resolve() if args.project else root / 'build/mister-profile'
    output = project / 'mister'
    output.mkdir(parents=True, exist_ok=True)
    options = ['-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
               '-o', 'ControlPath='+args.ssh_control]
    rows, stop, serial = {}, time.monotonic()+args.seconds, str(time.time_ns())
    index = 0
    while time.monotonic() < stop:
        name = f'aitd-profile-{serial}-{index}'
        remote = ('import glob,time,os\n'
                  'fd=os.open("/dev/MiSTer_cmd",os.O_WRONLY|os.O_NONBLOCK)\n'
                  f'os.write(fd,b"screenshot {name}\\n")\n'
                  'os.close(fd)\n'
                  'time.sleep(0.6)\n'
                  f'files=glob.glob("/media/fat/screenshots/S32X/*-{name}.png")\n'
                  'print(files[-1] if files else "")\n')
        try:
            path = subprocess.check_output(['ssh', *options, args.host,
                    'python3 -c '+shlex.quote(remote)], text=True, timeout=8).strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Core reloads replace the command FIFO. An opener can otherwise
            # wait forever on the old inode after its last reader disappears.
            time.sleep(1)
            continue
        if path:
            local = output / f'capture-{index}.png'
            subprocess.run(['scp', '-q', '-O', *options, args.host+':'+path, str(local)], check=True)
            try:
                row = result(decode(local))
            except ValueError:
                pass  # A scene is still running, or a report is being swapped.
            else:
                if row['variant'] == args.variant and row['case'] not in rows:
                    row['screenshot'] = str(local.relative_to(root))
                    rows[row['case']] = row
                    print(json.dumps(row), flush=True)
                    if len(rows) == 6:
                        break
        index += 1
        time.sleep(1.4)
    rom = args.rom if args.rom else root / 'build/AITD32X-mister-profile-v1.32x'
    report = dict(platform='MiSTer S32X_20260603', rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                  cases=[rows[i] for i in sorted(rows)], complete=len(rows) == 6)
    (output.parent / 'mister.json').write_text(json.dumps(report, indent=2)+'\n')
    if len(rows) != 6:
        raise RuntimeError('incomplete capture: '+str(sorted(rows)))


if __name__ == '__main__':
    main()
