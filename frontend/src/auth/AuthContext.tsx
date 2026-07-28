import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { getCurrentUser, loginUser, registerUser } from '../api/auth'
import type { LoginRequest, RegisterRequest, User } from '../types/auth'
import { AuthContext } from './authContextValue'
import type { AuthContextValue } from './authContextValue'
import {
  clearStoredAccessToken,
  getStoredAccessToken,
  setStoredAccessToken,
} from './tokenStorage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => getStoredAccessToken())
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    clearStoredAccessToken()
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    let isMounted = true

    async function restoreSession() {
      const storedToken = getStoredAccessToken()
      if (!storedToken) {
        if (isMounted) {
          setIsLoading(false)
        }
        return
      }

      try {
        const currentUser = await getCurrentUser()
        if (isMounted) {
          setToken(storedToken)
          setUser(currentUser)
        }
      } catch {
        if (isMounted) {
          logout()
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    void restoreSession()

    return () => {
      isMounted = false
    }
  }, [logout])

  const login = useCallback(async (payload: LoginRequest) => {
    const result = await loginUser(payload)
    setStoredAccessToken(result.access_token)
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  const register = useCallback(async (payload: RegisterRequest) => {
    await registerUser(payload)
    const result = await loginUser({
      username: payload.username,
      password: payload.password,
    })
    setStoredAccessToken(result.access_token)
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(user && token),
      isLoading,
      login,
      register,
      logout,
    }),
    [isLoading, login, logout, register, token, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
