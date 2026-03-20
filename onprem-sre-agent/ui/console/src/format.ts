/** Display helpers for incident monitoring (ASCII only). */

export function formatRelativeTime(iso: string | undefined): string {
  if (!iso) {
    return "";
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return "";
  }
  const diff = Date.now() - t;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) {
    return "just now";
  }
  const min = Math.floor(sec / 60);
  if (min < 60) {
    return `${min}m ago`;
  }
  const hr = Math.floor(min / 60);
  if (hr < 48) {
    return `${hr}h ago`;
  }
  const d = Math.floor(hr / 24);
  return `${d}d ago`;
}

export function formatDateTime(iso: string | undefined): string {
  if (!iso) {
    return "—";
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

export function humanizeState(state: string): string {
  return state.replace(/_/g, " ");
}

export function humanizeSeverity(sev: string): string {
  const map: Record<string, string> = {
    sev1: "Sev 1",
    sev2: "Sev 2",
    sev3: "Sev 3",
    sev4: "Sev 4"
  };
  return map[sev] ?? sev;
}
