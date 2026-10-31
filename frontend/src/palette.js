// Palette Hinova : teal, doré néon, bougies verte / rouge.
export const C = {
  teal: [25, 227, 200], gold: [255, 206, 77], red: [255, 77, 94], green: [46, 229, 157], grey: [120, 150, 160],
}
export const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`
export const STATE_COLOR = { idle: C.teal, setup: C.gold, stop: C.red, offline: C.grey }
