interface ComponentPillProps {
  label: string;
}

export function ComponentPill({ label }: Readonly<ComponentPillProps>) {
  return (
    <span className="text-[9px] font-black px-2 py-1 rounded-lg bg-[#eff2f0] text-[#24422e] uppercase tracking-widest">
      {label}
    </span>
  );
}
