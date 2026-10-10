#!/usr/bin/env python3
"""Build the pinned FITD gameplay oracle with presentation stubs, no SDL deps."""
import sys,shutil,subprocess,json,hashlib
from pathlib import Path
PIN='543e22bc78b64405537ae545ecd382dcdf2c12b2'
SOURCES='vars main mainLoop floor pak unpack hqr life evalVar track anim animAction actorList object zv cosTable gameTime fileAccess AITD1 AITD2 anim2d hybrid room renderer tatou sprite palette oracle'.split()
def main():
 if len(sys.argv)!=3:raise SystemExit('Usage: build_reference.py /path/to/FITD /path/to/reference-build')
 checkout=Path(sys.argv[1]).resolve();dest=Path(sys.argv[2]).resolve();here=Path(__file__).resolve().parent
 manifest=json.loads((here/'source-sha256.json').read_text())
 for name,digest in manifest['files'].items():
  path=checkout/'FitdLib'/name
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
   raise SystemExit('FITD source does not match the pinned revision: '+name)
 if dest.exists():raise SystemExit('Choose a new, empty reference-build directory')
 shutil.copytree(checkout/'FitdLib',dest)
 for name in ('config.h','main.cpp','tatou.cpp'):
  path=dest/name;path.write_text(path.read_text())
 subprocess.run(['patch','-p1','-i',str(here/'headless.patch')],cwd=dest,check=True)
 for name in ('oracle.cpp','prefix.hpp'):shutil.copy2(here/name,dest/name)
 (dest/'build').mkdir()
 for source in SOURCES:
  subprocess.run(['g++','-std=c++20','-O1','-g','-ffunction-sections','-fdata-sections','-DAITD_UE4','-DUNIX','-D_DEBUG','-include','prefix.hpp','-c',source+'.cpp','-o','build/'+source+'.o'],cwd=dest,check=True)
 subprocess.run(['g++','-no-pie','-Wl,--gc-sections']+['build/'+s+'.o' for s in SOURCES]+['-lz','-o','build/fitd-headless'],cwd=dest,check=True)
 print(dest/'build/fitd-headless')
if __name__=='__main__':main()
