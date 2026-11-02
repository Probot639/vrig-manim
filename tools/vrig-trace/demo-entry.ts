// Runs VRIG's booth demo logic (src/demo/challenges.ts) over the inputs the
// demo videos show, and dumps what VRIG says happens for each one.
//
//   node dist/vrig-demo.mjs > traces/demo.json

import {
  DEMO_CHALLENGES, evaluateCounter, evaluateStack, symbolsFor, withDestination,
} from '@/demo/challenges';
import { SLIDES } from '@/demo/slideshow';

const NAME = 'Taylor';             // same as slideshow.ts
const LONG_NAME = NAME.padEnd(24, '!');
const ADDR_OFFSET = 0x2a000;       // newAddressOffset() is random, pin one for video

function stack(id: 'overflow' | 'addresses', input: any, offset = 0x1000) {
  const r = evaluateStack(id, input, offset);
  return {
    text: input.text,
    ending: input.ending,
    payload: r.payload,
    memory: Array.from(r.sim.memory),
    written: Array.from(r.sim.written),
    overflow: Array.from(r.sim.overflowAt),
    destination: r.destination,
    outcome: r.outcome,
    symbols: r.symbols,
  };
}

const plain = (text: string) => ({ text, ending: null, requested: 8 });

// overflow: walk the slideshow's own beats
const overflowAdmin = symbolsFor('overflow', 0x1000).admin;
const overflow = {
  ...DEMO_CHALLENGES.overflow,
  slides: SLIDES,
  states: {
    empty: stack('overflow', plain('')),
    name: stack('overflow', plain(NAME)),
    full: stack('overflow', plain(NAME.padEnd(16, '!'))),
    spill: stack('overflow', plain(NAME.padEnd(20, '!'))),
    crash: stack('overflow', plain(LONG_NAME)),
    admin: stack('overflow', withDestination(plain(LONG_NAME.slice(0, 20)), overflowAdmin)),
  },
};

// addresses: old exploit vs moved admin(), then aim at the leak
const moved = symbolsFor('addresses', ADDR_OFFSET);
const pad = 'A'.repeat(20);  // initialDraft('addresses')
const addresses = {
  ...DEMO_CHALLENGES.addresses,
  offset: ADDR_OFFSET,
  before: symbolsFor('addresses', 0),
  after: moved,
  states: {
    oldAim: stack('addresses', withDestination(plain(pad), symbolsFor('addresses', 0).admin), ADDR_OFFSET),
    leakAim: stack('addresses', withDestination(plain(pad), moved.admin), ADDR_OFFSET),
  },
};

const counter = {
  ...DEMO_CHALLENGES.counter,
  runs: [100, 247, 248, 250].map(n => evaluateCounter(n)),
};

console.log(JSON.stringify({ overflow, addresses, counter }, null, 1));
