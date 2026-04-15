import type { InboundMessage } from "@/types";

function getQuickReplies(lastMsg: InboundMessage | undefined): string[] {
  if (lastMsg?.direction !== "inbound") return [];
  if (lastMsg.message_type === "location")
    return [
      "I can see you! Head to the main entrance ",
      "We're just 2 minutes from your location!",
      "Our team is on the way to guide you.",
    ];
  if (lastMsg.message_type === "image")
    return [
      "Thank you for sharing! Looks amazing",
      "We'd love to repost this — may we?",
      "So glad you caught that moment with us!",
    ];
  if (lastMsg.message_type === "document")
    return [
      "Got it, we'll review this shortly!",
      "Thanks for sending the document.",
      "We'll get back to you within 24 hours.",
    ];
  const body = (lastMsg.body ?? "").toLowerCase();
  if (/benefit|insurance|policy|hr|onboard/.test(body))
    return [
      "*Here's your benefits document:* https://drive.google.com/file/d/1j8bpKoDq-9T_dUT8J-fsq55rwET89e50/view?usp=drive_link",
      "Feel free to reach out if you have any questions!",
      "Let me know once you've had a chance to review it.",
    ];
  if (/table|reserv|book|seat/.test(body))
    return [
      "Yes, table confirmed! ✅",
      "Sorry, we're fully booked tonight.",
      "How many guests would you like?",
      "What time works best for you?",
    ];
  if (/menu|food|dish|eat|veg|allergi/.test(body))
    return [
      "Here's our menu",
      "We have great vegetarian options!",
      "Our chef's special tonight is the tasting menu.",
      "Any dietary requirements I should note?",
    ];
  if (/invoice|bill|receipt|payment/.test(body))
    return [
      "Sending the invoice right away! 📎",
      "Can you share the visit date?",
      "Your bill has been emailed to you.",
    ];
  if (/thank|great|love|amazing|perfect|happy/.test(body))
    return [
      "So glad you enjoyed it! 🙏",
      "You're always welcome with us!",
      "Do leave us a review — it helps a lot 🌟",
    ];
  if (/open|close|timing|time|hour/.test(body))
    return [
      "We're open 12 PM – 11 PM daily.",
      "Kitchen closes at 10:30 PM.",
      "We're open 7 days a week!",
    ];
  if (/location|where|address|find|direction/.test(body))
    return [
      "We're at Marine Drive, opposite the fountain.",
      "I'll share the Google Maps link!",
      "Nearest landmark is the Metro Station.",
    ];
  return [
    "Sure, let me check that for you!",
    "Thanks for reaching out",
    "We'll get back to you shortly.",
    "Happy to help!",
  ];
}

interface QuickRepliesProps {
  lastMessage: InboundMessage | undefined;
  onSelect: (text: string) => void;
  disabled?: boolean;
}

export function QuickReplies({
  lastMessage,
  onSelect,
  disabled,
}: Readonly<QuickRepliesProps>) {
  const suggestions = getQuickReplies(lastMessage);
  if (!suggestions.length) return null;
  return (
    <div className="px-6 pt-4 pb-2 flex flex-wrap gap-2 overflow-x-auto custom-scrollbar no-scrollbar whitespace-nowrap">
      {suggestions.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s)}
          disabled={disabled}
          className="text-[10px] font-black uppercase tracking-widest px-4 py-2 rounded-xl bg-[#eff2f0] border border-[#24422e]/5 text-[#24422e] hover:bg-[#24422e] hover:text-white hover:border-transparent transition-all shadow-sm active:scale-95 disabled:opacity-50"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
