export const TOKEN_KEY = "qizhi_access_token";
export const KB_ADMIN_TOKEN_KEY = "qizhi_kb_admin_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getKbAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(KB_ADMIN_TOKEN_KEY);
}

export function setKbAdminToken(token: string): void {
  sessionStorage.setItem(KB_ADMIN_TOKEN_KEY, token);
}

export function clearKbAdminToken(): void {
  sessionStorage.removeItem(KB_ADMIN_TOKEN_KEY);
}

export function clearAllAuth(): void {
  clearAccessToken();
  clearKbAdminToken();
}
