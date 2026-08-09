export type UserRole = 'user' | 'admin' | 'super_admin'

export interface User {
  id: string
  username: string
  display_name: string | null
  role: UserRole
  tenant_id?: string | null
  is_active: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  password: string
  display_name?: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}
