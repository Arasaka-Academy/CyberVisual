// Generated from packages/react/src/theme-swatch.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type ButtonHTMLAttributes, type Ref, type CSSProperties } from 'react';
import { type Scheme, schemes } from "./tokens";
import { cx } from "./shared";
import s from "./theme-swatch.module.css";
export interface ThemeSwatchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onSelect'> {
    ref?: Ref<HTMLButtonElement>;
    scheme: Scheme;
    mode?: 'dark' | 'light';
    selected?: boolean;
    onSelect?: () => void;
    className?: string;
}
export function ThemeSwatch({ scheme, mode = 'dark', selected, onSelect, className, ...props }: ThemeSwatchProps) {
    const palette = schemes[scheme][mode];
    return <button {...props} type="button" aria-label={scheme} className={cx(s.themeSwatch, className)} onClick={onSelect} aria-pressed={selected} style={{ ...props.style, '--swatch-bg': palette.bg, '--swatch-ink': palette.ink, '--swatch-accent': palette.accent } as CSSProperties}><span className={s.swatchColors} aria-hidden><i /><i /><i /></span><span>{scheme}</span><span aria-hidden>{selected ? '■' : '□'}</span></button>;
}
