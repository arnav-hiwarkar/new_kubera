export function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex h-full min-h-[50vh] items-center justify-center">
      <h2 className="text-xl font-medium text-muted-foreground">{title}</h2>
    </div>
  );
}
