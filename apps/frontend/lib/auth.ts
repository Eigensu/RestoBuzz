import { api } from "./api";

export interface User {
  id: string;
  email: string;
  role: "super_admin" | "admin" | "viewer";
  first_name?: string;
  last_name?: string;
  phone?: string;
  is_active: boolean;
  created_at: string;
}

export async function login(email: string, password: string): Promise<User> {
  const { data } = await api.post("/auth/login", { email, password });
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  const me = await api.get("/auth/me");
  return me.data;
}

export async function registerUser(payload: {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  password: string;
  confirmPassword: string;
  agreeToTerms: boolean;
}): Promise<User> {
  // 1. Create the account
  await api.post("/auth/register", payload);

  // 2. Automatically log them in
  return login(payload.email, payload.password);
}

export async function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export async function getMe(): Promise<User | null> {
  try {
    const { data } = await api.get("/auth/me");
    return data;
  } catch {
    return null;
  }
}
