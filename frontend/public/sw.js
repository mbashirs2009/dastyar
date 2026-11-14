/* دستیار — service worker.
 *
 * Strategy
 *   - App shell: precached on install, refreshed on every successful "/" navigation.
 *   - Navigations (any SPA route, e.g. /chat/123): network-first, offline shell fallback.
 *   - API reads (/auth, /chat, /conversations, /profile, /health): network-first,
 *     never written to Cache Storage — they are per-user and must not outlive a logout.
 *   - Everything else, same-origin GET: cache-first, then network + cache.
 *
 * Bump CACHE when the shell changes: activate() drops every other cache.
 */
const CACHE = 'dastyar-v1'
const SHELL_URL = '/index.html'
const PRECACHE = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']
const NETWORK_FIRST_PREFIXES = ['/auth', '/chat', '/conversations', '/profile', '/health']

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE)
      // allSettled, not addAll: one missing optional asset must not block activation.
      await Promise.allSettled(
        PRECACHE.map((url) => cache.add(new Request(url, { cache: 'reload' }))),
      )
      await self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
      await self.clients.claim()
    })(),
  )
})

function isNetworkFirstPath(url) {
  return NETWORK_FIRST_PREFIXES.some(
    (prefix) => url.pathname === prefix || url.pathname.startsWith(prefix + '/'),
  )
}

async function handleNavigation(request) {
  const cache = await caches.open(CACHE)
  try {
    const response = await fetch(request)
    // Keep the offline shell close to the deployed build.
    if (response.ok && new URL(request.url).pathname === '/') {
      await cache.put(SHELL_URL, response.clone()).catch(() => {})
    }
    return response
  } catch (error) {
    const shell = (await cache.match(SHELL_URL)) || (await cache.match('/'))
    if (shell) return shell
    throw error
  }
}

async function handleApiRead(request) {
  try {
    return await fetch(request)
  } catch (error) {
    const cache = await caches.open(CACHE)
    const cached = await cache.match(request)
    if (cached) return cached
    throw error
  }
}

async function handleAsset(request) {
  const cache = await caches.open(CACHE)
  const cached = await cache.match(request)
  if (cached) return cached

  const response = await fetch(request)
  if (response.ok && response.type === 'basic') {
    await cache.put(request, response.clone()).catch(() => {})
  }
  return response
}

self.addEventListener('fetch', (event) => {
  const { request } = event

  // Mutations (POST /chat, auth, profile PATCH) always go straight to the network.
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  // Range requests (audio/video/PDF) cannot be stored as a whole response.
  if (request.headers.has('range')) return

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigation(request))
    return
  }

  if (isNetworkFirstPath(url)) {
    event.respondWith(handleApiRead(request))
    return
  }

  event.respondWith(handleAsset(request))
})
