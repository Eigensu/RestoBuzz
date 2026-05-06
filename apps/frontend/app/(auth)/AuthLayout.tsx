"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { login, registerUser } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";
import { Eye, EyeOff, Utensils } from "lucide-react";

/* ─── Schemas ─────────────────────────────────────────────── */

const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

const registerSchema = z
  .object({
    firstName: z.string().min(1, "First name is required"),
    lastName: z.string().min(1, "Last name is required"),
    email: z.string().email("Invalid email address"),
    phone: z.string().min(1, "Phone number is required"),
    password: z.string().min(6, "Password must be at least 6 characters"),
    confirmPassword: z.string().min(6),
    agreeToTerms: z.boolean().refine((val) => val === true, {
      message: "You must agree to the Terms & Privacy Policy",
    }),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

type LoginFormData = z.infer<typeof loginSchema>;
type RegisterFormData = z.infer<typeof registerSchema>;

/* ─── Shared field style ───────────────────────────────────── */
const fieldWrap = "bg-[#eff2f0] px-3 py-2";
const fieldLabel = "block text-[10px] text-gray-400 font-medium mb-0.5";
const fieldInput =
  "w-full bg-transparent outline-none text-sm text-[#24422e] placeholder-gray-400";

/* ─── Logo ────────────────────────────────────────────────── */
function Logo() {
  return (
    <div className="flex items-center gap-2 mb-5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo-final.webp"
        alt="DishPatch"
        className="w-8 h-8 rounded object-cover shrink-0"
      />
      <span className="text-lg font-semibold text-[#24422e]">DishPatch</span>
    </div>
  );
}

/* ─── Component ───────────────────────────────────────────── */
export default function AuthLayout({
  initialMode,
}: {
  readonly initialMode: "login" | "register";
}) {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);
  const [mode, setMode] = useState<"login" | "register">(initialMode);

  const [showLoginPw, setShowLoginPw] = useState(false);
  const [showRegPw, setShowRegPw] = useState(false);
  const [showRegCf, setShowRegCf] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [regLoading, setRegLoading] = useState(false);

  const toggle = (m: "login" | "register") => {
    setMode(m);
  };

  const loginForm = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });
  const registerForm = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const onLoginSubmit = async (data: LoginFormData) => {
    setLoginLoading(true);
    try {
      const user = await login(data.email, data.password);
      setUser(user);
      router.push("/select-restaurant");
    } catch (e) {
      toast.error(parseApiError(e).message);
    } finally {
      setLoginLoading(false);
    }
  };

  const onRegisterSubmit = async (data: RegisterFormData) => {
    setRegLoading(true);
    try {
      await registerUser(data);
      toggle("login");
      toast.success("Account created! Please log in.");
    } catch (e) {
      toast.error(parseApiError(e).message || "Registration failed");
    } finally {
      setRegLoading(false);
    }
  };

  /* ─── Render ───────────────────────────────────────────────── */
  return (
    /*
     * Outer shell: full viewport, no scroll ever.
     * Dark-green background fills any gap on large monitors.
     */
    <div className="h-screen w-screen overflow-hidden bg-[#24422e] flex items-center justify-center">
      {/*
       * White card – capped at 1200 px wide, 95 vh tall.
       * overflow-hidden keeps the sliding image inside.
       */}
      <div className="relative bg-white w-full h-full max-w-[1200px] max-h-[95vh] rounded-2xl overflow-hidden shadow-2xl flex">
        {/* ── LOGIN PANEL (left half on desktop) ──────────────── */}
        <div
          className={[
            "absolute top-0 bottom-0 left-0 w-full lg:w-1/2",
            "flex flex-col justify-center px-8 md:px-14 lg:px-16",
            "transition-all duration-700 z-10",
            mode === "login"
              ? "opacity-100 pointer-events-auto"
              : "opacity-0 pointer-events-none",
          ].join(" ")}
        >
          <Logo />

          <h1 className="text-2xl md:text-3xl font-light text-[#24422e] leading-snug mb-1">
            Log In To Your DishPatch Account
          </h1>
          <p className="text-xs text-gray-500 mb-5 leading-relaxed">
            Welcome back — enter your email and password to continue.
          </p>

          <form
            onSubmit={loginForm.handleSubmit(onLoginSubmit)}
            className="space-y-3 w-full max-w-md"
          >
            {/* Email */}
            <div>
              <div className={fieldWrap}>
                <label htmlFor="login-email" className={fieldLabel}>
                  Email Address
                </label>
                <input
                  {...loginForm.register("email")}
                  id="login-email"
                  type="email"
                  placeholder="admin@example.com"
                  className={fieldInput}
                  suppressHydrationWarning
                />
              </div>
              {loginForm.formState.errors.email && (
                <p className="text-red-500 text-xs mt-0.5">
                  {loginForm.formState.errors.email.message}
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <div className={`${fieldWrap} flex items-center gap-2`}>
                <div className="flex-1">
                  <label htmlFor="login-password" className={fieldLabel}>
                    Password
                  </label>
                  <input
                    {...loginForm.register("password")}
                    id="login-password"
                    type={showLoginPw ? "text" : "password"}
                    placeholder="••••••••••••••••"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setShowLoginPw(!showLoginPw)}
                  className="text-[#24422e] shrink-0"
                  suppressHydrationWarning
                >
                  {showLoginPw ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {loginForm.formState.errors.password && (
                <p className="text-red-500 text-xs mt-0.5">
                  {loginForm.formState.errors.password.message}
                </p>
              )}
            </div>

            {/* Submit */}
            <div className="pt-1">
              <button
                type="submit"
                disabled={loginLoading}
                className="w-full bg-[#24422e] hover:bg-[#1a3022] text-white py-3 text-sm font-medium transition-colors disabled:opacity-60"
                suppressHydrationWarning
              >
                {loginLoading ? "Logging in…" : "Log In"}
              </button>
            </div>

            <p className="text-center text-xs text-gray-500 pt-1">
              Don&apos;t have an account?{" "}
              <button
                type="button"
                onClick={() => toggle("register")}
                className="text-[#24422e] font-bold hover:underline"
                suppressHydrationWarning
              >
                Sign Up
              </button>
            </p>
          </form>
        </div>

        {/* ── SIGNUP PANEL (right half on desktop) ─────────────── */}
        <div
          className={[
            "absolute top-0 bottom-0 right-0 w-full lg:w-1/2",
            "flex flex-col justify-center px-8 md:px-14 lg:px-16",
            "transition-all duration-700 z-10",
            mode === "register"
              ? "opacity-100 pointer-events-auto"
              : "opacity-0 pointer-events-none",
          ].join(" ")}
        >
          <Logo />

          <h1 className="text-2xl md:text-3xl font-light text-[#24422e] leading-snug mb-1">
            Create Your DishPatch Account
          </h1>
          <p className="text-xs text-gray-500 mb-4 leading-relaxed">
            Sign up to manage your restaurant effortlessly.
          </p>

          <form
            onSubmit={registerForm.handleSubmit(onRegisterSubmit)}
            className="space-y-2.5 w-full max-w-md"
          >
            {/* First Name + Last Name side by side */}
            <div className="flex gap-3">
              <div className="flex-1">
                <div className={fieldWrap}>
                  <label htmlFor="reg-firstName" className={fieldLabel}>
                    First Name
                  </label>
                  <input
                    {...registerForm.register("firstName")}
                    id="reg-firstName"
                    type="text"
                    placeholder="John"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                {registerForm.formState.errors.firstName && (
                  <p className="text-red-500 text-xs mt-0.5">
                    {registerForm.formState.errors.firstName.message}
                  </p>
                )}
              </div>
              <div className="flex-1">
                <div className={fieldWrap}>
                  <label htmlFor="reg-lastName" className={fieldLabel}>
                    Last Name
                  </label>
                  <input
                    {...registerForm.register("lastName")}
                    id="reg-lastName"
                    type="text"
                    placeholder="Doe"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                {registerForm.formState.errors.lastName && (
                  <p className="text-red-500 text-xs mt-0.5">
                    {registerForm.formState.errors.lastName.message}
                  </p>
                )}
              </div>
            </div>

            {/* Email + Phone side by side */}
            <div className="flex gap-3">
              <div className="flex-1">
                <div className={fieldWrap}>
                  <label htmlFor="reg-email" className={fieldLabel}>
                    Email Address
                  </label>
                  <input
                    {...registerForm.register("email")}
                    id="reg-email"
                    type="email"
                    placeholder="admin@example.com"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                {registerForm.formState.errors.email && (
                  <p className="text-red-500 text-xs mt-0.5">
                    {registerForm.formState.errors.email.message}
                  </p>
                )}
              </div>
              <div className="flex-1">
                <div className={fieldWrap}>
                  <label htmlFor="reg-phone" className={fieldLabel}>
                    Phone Number
                  </label>
                  <input
                    {...registerForm.register("phone")}
                    id="reg-phone"
                    type="tel"
                    placeholder="0123456789"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                {registerForm.formState.errors.phone && (
                  <p className="text-red-500 text-xs mt-0.5">
                    {registerForm.formState.errors.phone.message}
                  </p>
                )}
              </div>
            </div>

            {/* Password */}
            <div>
              <div className={`${fieldWrap} flex items-center gap-2`}>
                <div className="flex-1">
                  <label htmlFor="reg-password" className={fieldLabel}>
                    Password
                  </label>
                  <input
                    {...registerForm.register("password")}
                    id="reg-password"
                    type={showRegPw ? "text" : "password"}
                    placeholder="••••••••••••••••"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setShowRegPw(!showRegPw)}
                  className="text-[#24422e] shrink-0"
                  suppressHydrationWarning
                >
                  {showRegPw ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {registerForm.formState.errors.password && (
                <p className="text-red-500 text-xs mt-0.5">
                  {registerForm.formState.errors.password.message}
                </p>
              )}
            </div>

            {/* Confirm Password */}
            <div>
              <div className={`${fieldWrap} flex items-center gap-2`}>
                <div className="flex-1">
                  <label htmlFor="reg-confirmPassword" className={fieldLabel}>
                    Confirm Password
                  </label>
                  <input
                    {...registerForm.register("confirmPassword")}
                    id="reg-confirmPassword"
                    type={showRegCf ? "text" : "password"}
                    placeholder="••••••••••••••••"
                    className={fieldInput}
                    suppressHydrationWarning
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setShowRegCf(!showRegCf)}
                  className="text-[#24422e] shrink-0"
                  suppressHydrationWarning
                >
                  {showRegCf ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {registerForm.formState.errors.confirmPassword && (
                <p className="text-red-500 text-xs mt-0.5">
                  {registerForm.formState.errors.confirmPassword.message}
                </p>
              )}
            </div>

            {/* Terms */}
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  {...registerForm.register("agreeToTerms")}
                  className="w-4 h-4 accent-[#24422e] cursor-pointer"
                />
                <span className="text-xs text-[#24422e] font-medium">
                  I agree to the Terms &amp; Privacy Policy
                </span>
              </label>
              {registerForm.formState.errors.agreeToTerms && (
                <p className="text-red-500 text-xs mt-0.5">
                  {registerForm.formState.errors.agreeToTerms.message}
                </p>
              )}
            </div>

            {/* Submit */}
            <div className="pt-1">
              <button
                type="submit"
                disabled={regLoading}
                className="w-full bg-[#24422e] hover:bg-[#1a3022] text-white py-3 text-sm font-medium transition-colors disabled:opacity-60"
                suppressHydrationWarning
              >
                {regLoading ? "Signing up…" : "Sign Up"}
              </button>
            </div>

            <p className="text-center text-xs text-gray-500 pt-0.5">
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => toggle("login")}
                className="text-[#24422e] font-bold hover:underline"
                suppressHydrationWarning
              >
                Log In
              </button>
            </p>
          </form>
        </div>

        {/* ── SLIDING IMAGE PANEL (desktop only) ───────────────── */}
        {/*
          Login  → image sits on the RIGHT  (left: 50%)
          Signup → image slides to the LEFT (left: 0)
          Uses CSS background-image so no next/image fill quirks.
        */}
        <div
          className={[
            "hidden lg:block absolute top-0 bottom-0 w-1/2 z-20",
            "transition-all duration-700 ease-in-out shadow-2xl",
            mode === "login" ? "left-1/2" : "left-0",
          ].join(" ")}
          style={{
            backgroundImage: "url('/images/auth_side_image.png')",
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        >
          {/* subtle dark-green overlay */}
          <div className="absolute inset-0 bg-[#24422e]/10" />
        </div>
      </div>
    </div>
  );
}
