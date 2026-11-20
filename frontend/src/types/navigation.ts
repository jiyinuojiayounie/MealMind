export const featurePaths = {
  today: '/today',
  plan: '/plan',
  log: '/log',
  pantry: '/pantry',
  profile: '/profile',
} as const

export type Feature = keyof typeof featurePaths
