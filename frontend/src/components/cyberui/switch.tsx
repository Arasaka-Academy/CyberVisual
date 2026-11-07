// Generated from packages/react/src/switch.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import * as A from 'react-aria-components';
import { forwardRef } from 'react';
import { cx } from "./shared";
import s from "./switch.module.css";
export interface SwitchProps extends Omit<A.SwitchProps, 'children' | 'className'> {
    label: string;
    className?: string;
}
export const Switch = forwardRef<HTMLLabelElement, SwitchProps>(function Switch({ label, className, ...props }, ref) {
    return <A.Switch {...props} ref={ref} className={cx(s.choice, className)}><span aria-hidden className={s.switchTrack}><span className={s.switchKnob}/></span><span>{label}</span></A.Switch>;
});
