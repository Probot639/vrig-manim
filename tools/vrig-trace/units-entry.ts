// Unit and lesson titles for the overview videos.
//   node dist/vrig-units.mjs > traces/units.json

import { UNITS, TRACKS, getExercise } from '@/exercises/registry';

const strip = (s: string) => s.replace(/<[^>]+>/g, '');

const units = UNITS.map(u => ({
  id: u.id,
  name: u.name,
  track: TRACKS.find(t => t.unitIds.includes(u.id))?.name ?? null,
  lessons: u.exerciseIds.map(id => {
    const ex = getExercise(id)!;
    return { id, title: strip(ex.title), winTitle: strip(ex.winTitle ?? '') };
  }),
}));

console.log(JSON.stringify({ units }, null, 1));
