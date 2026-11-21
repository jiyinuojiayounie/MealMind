function twoDigits(value: number) {
  return String(value).padStart(2, '0')
}

export function localDateTimeValue(date: Date): string {
  const day = [String(date.getFullYear()).padStart(4, '0'), twoDigits(date.getMonth() + 1), twoDigits(date.getDate())]
  return `${day.join('-')}T${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())}`
}

export function timestampAtLocalTime(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) || value.startsWith('0000')) return null
  const date = new Date(value)
  // Reject invalid calendar dates and wall times skipped during daylight-saving transitions.
  if (!Number.isFinite(date.getTime()) || localDateTimeValue(date) !== value) return null
  const offset = -date.getTimezoneOffset()
  const minutes = Math.abs(offset)
  return `${value}:00${offset < 0 ? '-' : '+'}${twoDigits(Math.floor(minutes / 60))}:${twoDigits(minutes % 60)}`
}
