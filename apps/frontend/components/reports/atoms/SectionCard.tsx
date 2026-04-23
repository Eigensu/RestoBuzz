export function SectionCard({
  title,
  children,
}: {
  readonly title: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
      <h3 className="text-sm font-black text-gray-700 uppercase tracking-widest mb-4">
        {title}
      </h3>
      {children}
    </div>
  );
}
