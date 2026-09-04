import { Copy, ExternalLink, Phone, Reply } from "lucide-react";

/** WhatsApp template button types the editor can author.
 *
 *  Meta supports more (FLOW, CATALOG, MPM, OTP…) but each needs extra plumbing
 *  at send time. Templates that already carry them keep them: the backend's
 *  edit path preserves BUTTONS components the editor cannot express.
 */
export type ButtonType = "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | "COPY_CODE";

// Meta's template-button caps. Mirrored by _normalize_buttons in the backend's
// templates router — change both together.
export const MAX_BUTTONS = 10;
export const MAX_BUTTON_TEXT = 25;
export const MAX_BUTTON_URL = 2000;
export const MAX_OFFER_CODE = 15;

/** Above this count WhatsApp stops rendering buttons inline and folds them
 *  into a "See all options" list. Only affects the preview. */
export const INLINE_BUTTON_LIMIT = 3;

export const BUTTON_CONFIG = {
  QUICK_REPLY: {
    label: "Quick reply",
    hint: "Sends the button text back to you as a reply",
    max: 10,
    Icon: Reply,
  },
  URL: {
    label: "Visit website",
    hint: "Opens a link — your menu, booking page or offer",
    max: 2,
    Icon: ExternalLink,
  },
  PHONE_NUMBER: {
    label: "Call phone number",
    hint: "Dials your restaurant",
    max: 1,
    Icon: Phone,
  },
  COPY_CODE: {
    label: "Copy offer code",
    hint: "Copies a coupon code to the customer's clipboard",
    max: 1,
    Icon: Copy,
  },
} as const satisfies Record<
  ButtonType,
  { label: string; hint: string; max: number; Icon: typeof Copy }
>;

/** Call-to-action types, in the order the "Add button" menu offers them. */
export const CTA_TYPES = ["URL", "PHONE_NUMBER", "COPY_CODE"] as const;

/** WhatsApp renders COPY_CODE with its own fixed label — the text is not ours
 *  to set, so the editor hides the field and the preview hardcodes this. */
export const COPY_CODE_LABEL = "Copy offer code";

export const DIAL_CODES = [
  { iso: "IN", dial: "+91" },
  { iso: "US", dial: "+1" },
  { iso: "GB", dial: "+44" },
  { iso: "AE", dial: "+971" },
  { iso: "SG", dial: "+65" },
  { iso: "AU", dial: "+61" },
  { iso: "CA", dial: "+1" },
  { iso: "DE", dial: "+49" },
  { iso: "FR", dial: "+33" },
  { iso: "ES", dial: "+34" },
  { iso: "IT", dial: "+39" },
  { iso: "NL", dial: "+31" },
  { iso: "ID", dial: "+62" },
  { iso: "MY", dial: "+60" },
  { iso: "TH", dial: "+66" },
  { iso: "PH", dial: "+63" },
  { iso: "SA", dial: "+966" },
  { iso: "QA", dial: "+974" },
  { iso: "ZA", dial: "+27" },
  { iso: "BR", dial: "+55" },
] as const;

export const DEFAULT_DIAL = "+91";

/** One button as the editor holds it. `id` is a stable React key — buttons are
 *  reorderable and deletable, so the array index is not one. */
export interface ButtonDraft {
  id: string;
  type: ButtonType;
  /** Visible label. Unused by COPY_CODE, which WhatsApp labels itself. */
  text: string;
  /** URL buttons only. */
  url: string;
  /** PHONE_NUMBER only — dial code and national number are kept apart so the
   *  country picker can change one without reparsing the other. */
  dial: string;
  phone: string;
  /** COPY_CODE only: the coupon code WhatsApp copies. */
  code: string;
}

export const isCallToAction = (type: ButtonType) => type !== "QUICK_REPLY";

let seq = 0;

export function newButton(
  type: ButtonType,
  text = "",
): ButtonDraft {
  seq += 1;
  return {
    id: `btn_${seq}`,
    type,
    text,
    url: "",
    dial: DEFAULT_DIAL,
    phone: "",
    code: "",
  };
}

export const countOfType = (buttons: ButtonDraft[], type: ButtonType) =>
  buttons.filter((b) => b.type === type).length;

/** True when another button of `type` would exceed Meta's cap. `ignoreId` lets
 *  a row's own type select offer the type it is already using. */
export function isTypeFull(
  buttons: ButtonDraft[],
  type: ButtonType,
  ignoreId?: string,
) {
  const pool = ignoreId ? buttons.filter((b) => b.id !== ignoreId) : buttons;
  return (
    pool.length >= MAX_BUTTONS || countOfType(pool, type) >= BUTTON_CONFIG[type].max
  );
}

/** Validation message for one button, or null when it is ready to submit. */
export function buttonError(button: ButtonDraft): string | null {
  if (button.type === "COPY_CODE") {
    if (!button.code.trim()) return "Add the offer code customers will copy";
    if (button.code.length > MAX_OFFER_CODE) {
      return `Offer code must be ${MAX_OFFER_CODE} characters or fewer`;
    }
    return null;
  }

  if (!button.text.trim()) return "Button text is required";
  if (button.text.length > MAX_BUTTON_TEXT) {
    return `Button text must be ${MAX_BUTTON_TEXT} characters or fewer`;
  }

  if (button.type === "URL") {
    const url = button.url.trim();
    if (!url) return "Add the link this button opens";
    if (!/^https?:\/\//i.test(url)) return "Link must start with https://";
    if (url.length > MAX_BUTTON_URL) return "Link is too long";
    // Dynamic URLs need a per-recipient parameter on every send, which the
    // campaign send path does not emit — the link would resolve to the raw
    // placeholder for every customer.
    if (url.includes("{{")) return "Variables in links aren't supported yet";
  }

  if (button.type === "PHONE_NUMBER") {
    const digits = button.phone.replace(/\D/g, "");
    if (!digits) return "Add the number this button dials";
    if (digits.length < 4 || digits.length > 15) {
      return "Enter a valid phone number";
    }
  }

  return null;
}

/** Validation message covering the set as a whole, or null when it is valid. */
export function buttonsError(buttons: ButtonDraft[]): string | null {
  if (buttons.length === 0) return null;
  if (buttons.length > MAX_BUTTONS) {
    return `A template can have at most ${MAX_BUTTONS} buttons`;
  }

  for (const type of Object.keys(BUTTON_CONFIG) as ButtonType[]) {
    const { max, label } = BUTTON_CONFIG[type];
    if (countOfType(buttons, type) > max) {
      return `Only ${max} "${label}" button${max > 1 ? "s" : ""} allowed`;
    }
  }

  // Meta rejects a template whose buttons share a label — the tap would be
  // ambiguous in the delivery report.
  const labels = buttons
    .filter((b) => b.type !== "COPY_CODE")
    .map((b) => b.text.trim().toLowerCase())
    .filter(Boolean);
  if (new Set(labels).size !== labels.length) {
    return "Each button needs different text";
  }

  return buttons.map(buttonError).find(Boolean) ?? null;
}

/** The phone number a PHONE_NUMBER button dials, in E.164. */
export const buttonPhoneE164 = (button: ButtonDraft) =>
  `${button.dial}${button.phone.replace(/\D/g, "")}`;

type ButtonPayload = {
  type: ButtonType;
  text?: string;
  url?: string;
  phone_number?: string;
  example?: string;
};

/** Build the BUTTONS component for the Meta payload, or null when there is
 *  nothing to send. Call-to-action buttons come first so the quick replies end
 *  up grouped, which is what Meta requires of a mixed button set. */
export function buildButtonsComponent(
  buttons: ButtonDraft[],
): { type: "BUTTONS"; buttons: ButtonPayload[] } | null {
  if (buttons.length === 0) return null;

  const ordered = [
    ...buttons.filter((b) => isCallToAction(b.type)),
    ...buttons.filter((b) => !isCallToAction(b.type)),
  ];

  const payload = ordered.map((b): ButtonPayload => {
    switch (b.type) {
      case "URL":
        return { type: "URL", text: b.text.trim(), url: b.url.trim() };
      case "PHONE_NUMBER":
        return {
          type: "PHONE_NUMBER",
          text: b.text.trim(),
          phone_number: buttonPhoneE164(b),
        };
      case "COPY_CODE":
        return { type: "COPY_CODE", example: b.code.trim() };
      default:
        return { type: "QUICK_REPLY", text: b.text.trim() };
    }
  });

  return { type: "BUTTONS", buttons: payload };
}
