#!/usr/bin/env python3
"""Exercise the actual PWM ISR body against faulty/partial FIFO status.

The production body is compiled with private host I/O/sample stubs. This is
an algorithmic fault-injection check, not SH2, MiSTer or console validation.
"""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
source = (root / 'src/platform/audio.cpp').read_text()
start = source.index('extern "C" void Audio_PWMInterrupt() {')
body = source[start:source.index('\n#else', start)]
assert 'SH2Wait' not in body, 'PWM ISR must never busy-wait for hardware'
body = body.replace('*(volatile uint8_t *)0x20004001', 'irq_mask')
state = source[source.index('static uint16_t cycle,previous_width;'):source.index('static const int16_t steps')]
prefix = r'''
#include <cstdint>
#include <cassert>
#include <cstdio>
#include <algorithm>
struct Voice { unsigned count,pos; };
static Voice voices[2];
static uint8_t irq_mask;
static unsigned used,reads,writes,decoded;
static uint16_t control;
static bool force_full;
static int Sample(Voice &v) {
    if(!v.count) return 0;
    if(v.pos==v.count) { v.count=0;return 0; }
    ++v.pos;++decoded;return 10000;
}
static int Clamp(int v,int low,int high) { return std::min(high,std::max(low,v)); }
struct Register {
    unsigned address;
    operator uint16_t() const {
        assert(address==0x20004038);++reads;
        // Deliberately never report EMPTY, even after every pulse is consumed.
        return force_full || used==3 ? 0x8000 : 0;
    }
    void operator=(uint16_t value) const {
        if(address==0x20004038) { assert(!force_full && used<3);++used;++writes; }
        else if(address==0x20004030) control=value;
        else assert(address==0x2000401c);
    }
};
#define REG16(address) Register{address}
'''
tests = r'''
static void Reset() {
    voices[0]={3,0};voices[1]={0,0};cycle=960;previous_width=480;
    first_width=0;third_width=0;pending=0;draining=false;running=true;
    irq_mask=1;control=0x0305;used=reads=writes=decoded=0;force_full=false;
}
static void IRQ() {
    unsigned before=reads;Audio_PWMInterrupt();assert(reads-before<=4);
}
static void Tick() { used=0;IRQ(); }
int main() {
    Reset();IRQ();for(int i=0;i<4;++i) Tick();
    assert(decoded==3 && !running && !control && !irq_mask);
    Reset();force_full=true;unsigned drawing_work=0;
    for(int i=0;i<10000;++i) { IRQ();++drawing_work; }
    assert(drawing_work==10000 && !writes && !decoded && voices[0].pos==0);
    voices[0].count=0;IRQ();assert(draining);IRQ();
    assert(!running && !control && !irq_mask); // Stop still finishes with FULL stuck.
    Reset();used=2;IRQ();assert(decoded==1 && pending==2 && used==3);
    Tick();assert(decoded==1 && !pending && used==2);
    Tick();assert(decoded==2 && !pending);
    Reset();voices[0].count=1;IRQ();Tick();assert(draining);
    voices[0]={2,0};Tick();assert(running && !draining && voices[0].pos==1);
    puts("{\"stuck_full_returns\":true,\"missing_empty_stops\":true,\"partial_group_preserved\":true,\"restart_during_drain\":true}");
}
'''
path = root / 'build/pwm-irq-faults.cpp'
path.write_text(prefix + state + body + tests)
binary = path.with_suffix('')
subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', str(path), '-o', str(binary)], check=True)
result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=3)
(root / 'build/pwm-irq-faults.json').write_text(result.stdout)
print(result.stdout, end='')
