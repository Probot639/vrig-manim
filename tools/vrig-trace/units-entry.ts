// Unit and lesson titles for the overview videos.
//   node dist/vrig-units.mjs > traces/units.json

import { UNITS, TRACKS, getExercise } from '@/exercises/registry';
import { imagineRitExercises } from '@/exercises/imagine-rit';

const strip = (s: string) => s.replace(/<[^>]+>/g, '');

// imagine-rit is a standalone workshop, not a registry unit, so add it by hand
const extra = [{
  id: 'imagine-rit',
  name: 'Imagine RIT',
  exerciseIds: imagineRitExercises.map(e => e.id),
}];

const units = [...UNITS, ...extra].map(u => ({
  id: u.id,
  name: u.name,
  track: TRACKS.find(t => t.unitIds.includes(u.id))?.name ?? (u.id === 'imagine-rit' ? 'Workshop' : null),
  lessons: u.exerciseIds.map(id => {
    const ex = getExercise(id)!;
    return { id, title: strip(ex.title), winTitle: strip(ex.winTitle ?? '') };
  }),
}));

console.log(JSON.stringify({ units }, null, 1));
