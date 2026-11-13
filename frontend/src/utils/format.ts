export const RUN_COLORS = [
  "#4f46e5", // indigo-600
  "#d97706", // amber-600
  "#059669", // emerald-600
  "#dc2626", // red-600
  "#7c3aed", // violet-600
  "#0284c7", // sky-600
  "#db2777", // pink-600
  "#0d9488", // teal-600
  "#ea580c", // orange-600
  "#2563eb", // blue-600
  "#65a30d", // lime-600
  "#475569", // slate-600
];

export const RUN_SYMBOLS = [
  "circle",
  "diamond",
  "square",
  "triangle-up",
  "cross",
  "star",
  "hexagon",
  "triangle-down",
  "pentagon",
  "x",
  " hourglass",
  "bowtie",
].map((s) => s.trim());

export function fmtFloat(val: number | null | undefined, digits = 4): string {
  if (val === null || val === undefined || Number.isNaN(val)) return "—";
  return Number(val).toFixed(digits);
}

export function fmtPct(val: number | null | undefined, digits = 2): string {
  if (val === null || val === undefined || Number.isNaN(val)) return "—";
  return `${(Number(val) * 100).toFixed(digits)}%`;
}

export function fmtInt(val: number | null | undefined): string {
  if (val === null || val === undefined) return "0";
  return Number(val).toLocaleString();
}
