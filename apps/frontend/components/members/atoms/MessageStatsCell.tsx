interface MessageStatsCellProps {
  received?: number;
  read?: number;
  sent?: number;
  lastMessageAt?: string | null;
}

/**
 * Lifetime messaging counts for one member.
 *
 * "Read" comes from WhatsApp read receipts, which a recipient can switch off —
 * a member showing 0 reads may simply have them disabled rather than be
 * ignoring the messages. The tooltip says so, because the bare number reads as
 * a much stronger claim than it is.
 */
export function MessageStatsCell({
  received = 0,
  read = 0,
  sent = 0,
  lastMessageAt,
}: Readonly<MessageStatsCellProps>) {
  if (sent === 0 && received === 0) {
    return (
      <span className="text-[11px] text-gray-300 italic">Never messaged</span>
    );
  }

  const readRate = received > 0 ? Math.round((read / received) * 100) : 0;
  const undelivered = sent - received;

  const tooltip = [
    `${sent} sent`,
    `${received} delivered`,
    `${read} read (${readRate}% of delivered)`,
    undelivered > 0 ? `${undelivered} never confirmed delivered` : null,
    "Read counts rely on WhatsApp read receipts, which recipients can turn off.",
    lastMessageAt ? `Last sent ${new Date(lastMessageAt).toLocaleString()}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div title={tooltip} className="cursor-default select-none">
      <p className="text-sm font-black text-gray-900 leading-none">
        {received}
        <span className="ml-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
          received
        </span>
      </p>
      <p className="mt-1 text-[11px] font-bold text-[#24422e] leading-none">
        {read}
        <span className="ml-1 text-[10px] font-medium text-gray-400 normal-case tracking-normal">
          read{received > 0 ? ` · ${readRate}%` : ""}
        </span>
      </p>
    </div>
  );
}
