import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** T_SEC.7 — a screen talking to the server is not idle.
 *
 *  The idle timer used to watch the pointer and the keyboard only, so somebody
 *  reading a deal — a screen that polls on its own — was counted as doing
 *  nothing. Announced as a DOM event rather than by calling the store: the auth
 *  store imports the API layer, and importing it back would close the circle.
 */
api.interceptors.response.use(
  (response) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('api-activity'))
    }
    return response
  },
  (error) => {
    /* T_SEC.7 — «24h+ → reauth». The server says so in the detail rather than
       with a bare 401, because the two answers lead to different screens: this
       one is «докажи, что это ты» and the account is still the account, so the
       token is kept and the sign-in page is told why it is being shown. */
    const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })
      .response
    if (
      typeof window !== 'undefined' &&
      response?.status === 401 &&
      response.data?.detail === 'reauth_required' &&
      !window.location.pathname.startsWith('/login')
    ) {
      // `returnUrl` is the name the sign-in page reads, and it validates it
      // before using it — a different spelling here would land everybody on the
      // dashboard after proving themselves.
      const back = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.replace(`/login?reason=reauth&returnUrl=${back}`)
    }
    return Promise.reject(error)
  },
)

export default api
