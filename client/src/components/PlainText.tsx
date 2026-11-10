import { Fragment, type ReactNode } from 'react';
import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/ui/hover-card';
import { useGlossary, type Glossary, type GlossaryTerm } from '@/lib/glossary';

/** A word with a hover (and keyboard-focus) definition from the shared glossary. */
export function Term({ t, children, extra }: { t?: GlossaryTerm; children: ReactNode; extra?: string }) {
  if (!t) return extra ? <span title={extra} className="underline decoration-dotted underline-offset-2 cursor-help">{children}</span> : <>{children}</>;
  return (
    <HoverCard openDelay={150} closeDelay={50}>
      <HoverCardTrigger asChild>
        <span tabIndex={0} className="underline decoration-dotted decoration-muted-foreground/70 underline-offset-2 cursor-help">{children}</span>
      </HoverCardTrigger>
      <HoverCardContent className="w-72 p-3 text-xs leading-snug">
        <div className="font-semibold text-foreground">{t.term}</div>
        <div className="text-muted-foreground mt-0.5">{t.short}.</div>
        {t.more && <div className="text-muted-foreground mt-1">{t.more}</div>}
        {extra && extra !== t.more && <div className="text-muted-foreground mt-1 font-mono text-[10.5px]">{extra}</div>}
      </HoverCardContent>
    </HoverCard>
  );
}

/** A label (e.g. a table header or stat title) with its definition on hover, looked up by glossary key. */
export function Def({ k, children }: { k: string; children: ReactNode }) {
  const g = useGlossary();
  return <Term t={g.byKey[k]}>{children}</Term>;
}

/** A table label: the whole label gets the definition of the first glossary term it contains. */
export function AutoTerm({ text, extra }: { text: string; extra?: string }) {
  const g = useGlossary();
  let t = g.lookup(text);
  if (!t && g.re) {
    g.re.lastIndex = 0;
    const m = g.re.exec(text);
    t = m ? g.lookup(m[0]) : undefined;
  }
  return <Term t={t} extra={extra}>{text}</Term>;
}

type Src = { id: string; url?: string | null; title?: string };

/** Link glossary words in a plain string (first occurrence of each term only, to keep it calm). */
function linkTerms(s: string, g: Glossary, seen: Set<string>, keyBase: string): ReactNode[] {
  if (!g.re) return [s];
  const out: ReactNode[] = [];
  let last = 0;
  g.re.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = g.re.exec(s))) {
    const t = g.lookup(m[0]);
    if (!t || seen.has(t.key)) continue;
    seen.add(t.key);
    if (m.index > last) out.push(s.slice(last, m.index));
    out.push(<Term key={`${keyBase}-${m.index}`} t={t}>{m[0]}</Term>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

const TOKEN = /(\*\*[^*]+\*\*|\[[A-Z]{1,2}\d{1,2}\])/g;

function inline(s: string, g: Glossary, seen: Set<string>, srcs: Record<string, Src>, keyBase: string): ReactNode[] {
  return s.split(TOKEN).filter(Boolean).map((part, i) => {
    const k = `${keyBase}-${i}`;
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={k} className="font-semibold text-foreground">{linkTerms(part.slice(2, -2), g, seen, k)}</strong>;
    }
    const id = /^\[([A-Z]{1,2}\d{1,2})\]$/.exec(part);
    if (id) {
      const src = srcs[id[1]];
      const cls = 'ml-px text-[0.68em] font-mono text-primary/80 align-super';
      return src?.url
        ? <sup key={k}><a href={src.url} target="_blank" rel="noreferrer" title={src.title || id[1]} className={`${cls} hover:underline`}>{id[1]}</a></sup>
        : <sup key={k} className={cls} title={src?.title || 'Fact id — see the facts or sources below'}>{id[1]}</sup>;
    }
    return <Fragment key={k}>{linkTerms(part, g, seen, k)}</Fragment>;
  });
}

/**
 * Renders Oracle's plain-language text: paragraphs (blank line), "- " bullets, **bold**,
 * fact ids like [A1] as small superscript links, and glossary words with hover definitions.
 */
export default function PlainText({ text, sources, className = '' }: { text: string; sources?: Src[]; className?: string }) {
  const g = useGlossary();
  const seen = new Set<string>();
  const srcs: Record<string, Src> = Object.fromEntries((sources || []).map((s) => [s.id, s]));
  const blocks = (text || '').split(/\n{2,}/);
  return (
    <div className={`space-y-2 ${className}`}>
      {blocks.map((b, bi) => {
        const lines = b.split('\n');
        const bullets = lines.filter((l) => /^\s*[-•]\s+/.test(l));
        const head = lines.filter((l) => !/^\s*[-•]\s+/.test(l));
        return (
          <div key={bi}>
            {head.length > 0 && <p className="leading-relaxed">{inline(head.join(' '), g, seen, srcs, `b${bi}`)}</p>}
            {bullets.length > 0 && (
              <ul className="mt-1 space-y-1 list-disc pl-4 marker:text-muted-foreground/60">
                {bullets.map((l, li) => <li key={li} className="leading-snug">{inline(l.replace(/^\s*[-•]\s+/, ''), g, seen, srcs, `b${bi}l${li}`)}</li>)}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
