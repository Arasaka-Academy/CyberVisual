import { createState, reduce, advance } from './simulation.mjs';

export function createLessonStore() {
  let state = createState();
  let carry = 0;
  const listeners = new Set();
  const publish = next => {
    if (next === state) return;
    state = next;
    for (const listener of listeners) listener();
  };
  return {
    getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); },
    dispatch: action => { carry = 0; publish(reduce(state, action)); },
    tick: seconds => {
      carry += Math.min(.1, Math.max(0, seconds));
      let next = state;
      while (carry >= 1 / 60) { next = advance(next, 1 / 60); carry -= 1 / 60; }
      publish(next);
    },
  };
}

export const lessonStore = createLessonStore();
export const telemetry = { ready: false, fps: 0, anchors: {}, connectorGap: 0 };
