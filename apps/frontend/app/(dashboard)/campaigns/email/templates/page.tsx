"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function EmailTemplatesRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/templates");
  }, [router]);

  return (
    <div className="h-screen flex flex-col items-center justify-center gap-4 text-gray-400">
      <Loader2 className="w-8 h-8 animate-spin text-[#24422e]" />
      <p className="text-sm font-medium">Redirecting to Templates Hub...</p>
    </div>
  );
}
