// Generated from packages/react/src/pagination.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DOMProps, useControllableState, cx } from "./shared";
import { useCyberUI } from "./provider";
import s from "./pagination.module.css";
import { IconButton } from "./icon-button";
export interface PaginationProps extends DOMProps<HTMLElement> {
    page?: number;
    defaultPage?: number;
    totalPages: number;
    onChange?: (page: number) => void;
}
export function Pagination({ page, defaultPage = 1, totalPages, onChange, className, ...props }: PaginationProps) {
    const [current, setCurrent] = useControllableState(page, defaultPage, onChange);
    const { t } = useCyberUI();
    const count = Math.max(1, totalPages);
    const shown = Math.min(count, Math.max(1, current));
    return <nav {...props} aria-label={props['aria-label'] ?? t('Pagination', '分页')} className={cx(s.nav, className)}>
    <IconButton icon="first" size="sm" aria-label={t('First page', '第一页')} isDisabled={shown <= 1} onPress={() => setCurrent(1)}/>
    <IconButton icon="back" size="sm" aria-label={t('Previous page', '上一页')} isDisabled={shown <= 1} onPress={() => setCurrent(shown - 1)}/>
    <span aria-live="polite" style={{ fontFamily: 'var(--cyber-font-mono)', fontSize: 13, padding: '0 8px' }}>{String(shown).padStart(2, '0')} / {String(count).padStart(2, '0')}</span>
    <IconButton icon="forward" size="sm" aria-label={t('Next page', '下一页')} isDisabled={shown >= count} onPress={() => setCurrent(shown + 1)}/>
    <IconButton icon="last" size="sm" aria-label={t('Last page', '最后一页')} isDisabled={shown >= count} onPress={() => setCurrent(count)}/>
  </nav>;
}
