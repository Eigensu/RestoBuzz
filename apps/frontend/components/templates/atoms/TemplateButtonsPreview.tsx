import { List } from "lucide-react";
import {
  BUTTON_CONFIG,
  COPY_CODE_LABEL,
  INLINE_BUTTON_LIMIT,
} from "@/lib/templateButtons";
import type { ButtonDraft } from "@/lib/templateButtons";

/** WhatsApp renders the buttons inline while there are few of them; past that
 *  it keeps the first two and folds the rest behind "See all options". */
export function TemplateButtonsPreview({
  buttons,
}: Readonly<{ buttons: ButtonDraft[] }>) {
  if (buttons.length === 0) return null;

  const overflows = buttons.length > INLINE_BUTTON_LIMIT;
  const shown = overflows ? buttons.slice(0, 2) : buttons;

  return (
    <div className="border-t border-gray-100 divide-y divide-gray-100">
      {shown.map((button) => {
        const { Icon } = BUTTON_CONFIG[button.type];
        const label =
          button.type === "COPY_CODE"
            ? COPY_CODE_LABEL
            : button.text.trim() || BUTTON_CONFIG[button.type].label;
        return (
          <div
            key={button.id}
            className="flex items-center justify-center gap-1.5 py-2 text-[11px] font-semibold text-[#0a7cff]"
          >
            <Icon className="w-3 h-3 shrink-0" />
            <span className="truncate">{label}</span>
          </div>
        );
      })}

      {overflows && (
        <div className="flex items-center justify-center gap-1.5 py-2 text-[11px] font-semibold text-[#0a7cff]">
          <List className="w-3 h-3 shrink-0" />
          See all options
        </div>
      )}
    </div>
  );
}
