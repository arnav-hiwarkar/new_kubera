import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAppAuth } from "@/contexts/AppAuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function CompanyLoginPage() {
  const { login } = useAppAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [serverError, setServerError] = useState<string | null>(null);

  const returnTo =
    (location.state as { returnTo?: string } | null)?.returnTo ?? "/app";

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(data: LoginFormValues) {
    setServerError(null);
    try {
      await login(data.email, data.password);
      navigate(returnTo, { replace: true });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setServerError(err.message);
      } else {
        setServerError("Login failed. Please check your credentials.");
      }
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[hsl(225,20%,11%)] px-4">
      <div className="w-full max-w-sm rounded-[6px] border border-[hsl(42,35%,35%)] bg-[hsl(225,18%,15%)] p-8">
        {/* Brand */}
        <div className="mb-8 text-center">
          <h1 className="font-heading text-3xl tracking-wide text-[hsl(42,65%,55%)]">
            KUBERA
          </h1>
          <p className="mt-1 text-sm text-[hsl(225,10%,55%)]">
            Company Portal
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          {/* Email */}
          <div className="space-y-1.5">
            <Label
              htmlFor="email"
              className="text-[hsl(225,10%,88%)]"
            >
              Email
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="you@company.com"
              autoComplete="email"
              aria-invalid={!!errors.email}
              className="h-9 border-[hsl(42,35%,35%)]/40 bg-[hsl(225,15%,20%)] text-[hsl(225,10%,88%)] placeholder:text-[hsl(225,10%,55%)]/60 focus-visible:border-[hsl(42,65%,55%)] focus-visible:ring-[hsl(42,65%,55%)]/30"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-xs text-destructive">{errors.email.message}</p>
            )}
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <Label
              htmlFor="password"
              className="text-[hsl(225,10%,88%)]"
            >
              Password
            </Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              aria-invalid={!!errors.password}
              className="h-9 border-[hsl(42,35%,35%)]/40 bg-[hsl(225,15%,20%)] text-[hsl(225,10%,88%)] placeholder:text-[hsl(225,10%,55%)]/60 focus-visible:border-[hsl(42,65%,55%)] focus-visible:ring-[hsl(42,65%,55%)]/30"
              {...register("password")}
            />
            {errors.password && (
              <p className="text-xs text-destructive">
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Server error */}
          {serverError && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {serverError}
            </p>
          )}

          {/* Submit */}
          <Button
            type="submit"
            disabled={isSubmitting}
            className="h-9 w-full bg-[hsl(42,65%,55%)] text-[hsl(225,25%,7%)] hover:bg-[hsl(42,65%,50%)] focus-visible:ring-[hsl(42,65%,55%)]/40"
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        {/* Footer link */}
        <p className="mt-6 text-center text-sm text-[hsl(225,10%,55%)]">
          Auditor?{" "}
          <Link
            to="/auditor/login"
            className="text-[hsl(42,65%,55%)] underline-offset-4 hover:underline"
          >
            Sign in here
          </Link>
        </p>
      </div>
    </div>
  );
}
