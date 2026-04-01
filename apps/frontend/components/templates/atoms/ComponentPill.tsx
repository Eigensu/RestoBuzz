interface ComponentPillProps {
  label: string;
}

export function ComponentPill({ label }: Readonly<ComponentPillProps>) {
  return (
    <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#eff2f0] text-[#24422e]">
      {label}
    </span>
  );
}
