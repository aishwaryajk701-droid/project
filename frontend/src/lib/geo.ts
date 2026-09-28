// Client-side geodesy for display only — the backend recomputes authoritative values.

export function polygonAreaHa(coords: number[][]): number {
  const pts = closed([...coords]);
  if (pts.length < 3) return 0;
  const latAvg = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const R = 6378137;
  const xs = pts.map((p) => ((p[0] * Math.PI) / 180) * R * Math.cos((latAvg * Math.PI) / 180));
  const ys = pts.map((p) => ((p[1] * Math.PI) / 180) * R);
  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    area += xs[i] * ys[j] - xs[j] * ys[i];
  }
  return Math.abs(area) / 2 / 10000;
}

export function polygonAreaSqm(coords: number[][]): number {
  return polygonAreaHa(coords) * 10000;
}

export function bboxOf(coords: number[][]): [number, number, number, number] {
  const lngs = coords.map((p) => p[0]);
  const lats = coords.map((p) => p[1]);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

export function centroidOf(coords: number[][]): [number, number] {
  const pts = closed([...coords]);
  const lat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const lng = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  return [lat, lng];
}

export function formatHa(ha: number): string {
  if (ha >= 100) return `${ha.toFixed(0)} ha`;
  if (ha >= 1) return `${ha.toFixed(2)} ha`;
  return `${(ha * 10000).toFixed(0)} m²`;
}

function closed(coords: number[][]): number[][] {
  if (coords.length > 2) {
    const f = coords[0];
    const l = coords[coords.length - 1];
    if (f[0] === l[0] && f[1] === l[1]) coords = coords.slice(0, -1);
  }
  return coords;
}
