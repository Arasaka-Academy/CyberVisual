// Generated from packages/react/src/alert.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DOMProps, cx } from "./shared";
import { type ReactNode } from 'react';
import s from "./alert.module.css";
import { Icon } from "./icon";
export interface AlertProps extends DOMProps {
    title: string;
    children?: ReactNode;
    tone?: 'info' | 'success' | 'warning' | 'danger';
}
export function Alert({ title, children, tone = 'info', className, ...props }: AlertProps) {
    return <div {...props} role={tone === 'danger' ? 'alert' : 'status'} className={cx(s.alert, className)} data-tone={tone}><Icon name={tone === 'success' ? 'check' : 'warning'}/><div><strong>{title}</strong>{children && <p>{children}</p>}</div></div>;
}
