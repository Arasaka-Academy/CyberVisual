// Generated from packages/react/src/table.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type ReactNode } from 'react';
import { type DOMProps, cx } from "./shared";
import { useCyberUI } from "./provider";
import s from "./table.module.css";
export interface TableColumn<T> {
    key: keyof T & string;
    label: string;
    render?: (value: T[keyof T], row: T) => ReactNode;
    sortable?: boolean;
}
export interface TableProps<T extends {
    id: string;
}> extends DOMProps {
    label: string;
    rows: T[];
    columns: TableColumn<T>[];
    emptyMessage?: string;
}
export function Table<T extends {
    id: string;
}>({ label, rows, columns, className, emptyMessage, ...props }: TableProps<T>) {
    const { t } = useCyberUI();
    return <div {...props} className={cx(s.tableWrap, className)}><table aria-label={label} className={s.table}><thead><tr>{columns.map(c => <th scope="col" key={c.key}>{c.label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}>{columns.map(c => <td key={c.key}>{c.render ? c.render(row[c.key], row) : String(row[c.key] ?? '')}</td>)}</tr>)}{!rows.length && <tr><td colSpan={columns.length}>{emptyMessage ?? t('No results', '没有结果')}</td></tr>}</tbody></table></div>;
}
