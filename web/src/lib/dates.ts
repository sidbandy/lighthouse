/** Today as yyyy-mm-dd in the viewer's timezone, which is the one they mean when
 *  they say "I applied yesterday". `toISOString()` is UTC and can be a day off
 *  either side of midnight. */
export function today(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** A yyyy-mm-dd from a date input, as an instant the API can store. Midday local
 *  keeps the date from shifting when it is converted to UTC. */
export function atMidday(day: string): string {
  return new Date(`${day}T12:00:00`).toISOString();
}
