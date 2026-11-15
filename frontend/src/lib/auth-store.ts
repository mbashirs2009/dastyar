// Access token فقط در حافظه — refresh در کوکی HttpOnly
let accessToken: string | null = null

export const getAccess = (): string | null => accessToken
export const setAccess = (token: string): void => {
  accessToken = token
}
export const clearAccess = (): void => {
  accessToken = null
}
