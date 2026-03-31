import { ImageIcon, Smartphone, ExternalLink } from "lucide-react";
import type { Template } from "@/types";

import { BRAND_GRADIENT } from "@/lib/brand";

interface WizardTemplatePreviewProps {
  template: Template | null;
  variables: Record<string, string>;
  mediaUrl: string;
}

export function WizardTemplatePreview({
  template,
  variables,
  mediaUrl,
}: WizardTemplatePreviewProps) {
  if (!template) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <Smartphone className="w-10 h-10 opacity-30" />
        <p className="text-sm">Select a template to preview</p>
      </div>
    );
  }

  const header = template.components.find((c) => c.type === "HEADER");
  const body = template.components.find((c) => c.type === "BODY");
  const footer = template.components.find((c) => c.type === "FOOTER");
  const buttons = template.components.find((c) => c.type === "BUTTONS") as
    | { type: string; buttons?: { type: string; text: string }[] }
    | undefined;

  const resolveBody = (text: string) =>
    text.replaceAll(/\{\{(\d+)\}\}/g, (_, k) => variables[k] ?? `{{${k}}}`);

  return (
    <div className="flex flex-col items-stretch h-full pt-2">
      <p className="text-xs text-gray-400 mb-3 font-medium tracking-wide uppercase text-center">
        WhatsApp Preview
      </p>
      <div className="w-full bg-[#e5ddd5] rounded-2xl overflow-hidden shadow-xl border border-gray-200 flex flex-col">
        <div
          className="h-8 flex items-center px-4 gap-2 shrink-0"
          style={{ background: BRAND_GRADIENT }}
        >
          <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-white text-[8px] font-bold">R</span>
          </div>
          <span className="text-white text-[10px] font-medium flex-1">
            RestoBuzz
          </span>
        </div>
        <div className="p-3 flex-1 overflow-y-auto">
          <div className="bg-white rounded-xl rounded-tl-sm shadow-sm overflow-hidden">
            {header?.format === "IMAGE" && (
              <div className="bg-gray-100 h-36 flex items-center justify-center">
                {mediaUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaUrl}
                    alt="header"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <ImageIcon className="w-10 h-10 text-gray-300" />
                )}
              </div>
            )}
            {header?.text && (
              <div className="px-3 pt-2.5">
                <p className="text-sm font-bold text-gray-900">{header.text}</p>
              </div>
            )}
            {body?.text && (
              <div className="px-3 py-2">
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap break-words">
                  {resolveBody(body.text)}
                </p>
              </div>
            )}
            {footer?.text && (
              <div className="px-3 pb-2">
                <p className="text-xs text-gray-400">{footer.text}</p>
              </div>
            )}
            <div className="px-3 pb-1.5 flex justify-end">
              <span className="text-[10px] text-gray-400">10:30 AM ✓✓</span>
            </div>
            {buttons?.buttons && buttons.buttons.length > 0 && (
              <div className="border-t divide-y">
                {buttons.buttons.map((btn) => (
                  <div
                    key={btn.text}
                    className="flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium"
                    style={{ color: "#24422e" }}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    {btn.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
