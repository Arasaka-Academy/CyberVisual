// Generated from packages/react/src/segmented-control.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DOMProps, useControllableState, cx } from "./shared";
import { type Option } from "./option";
import * as A from 'react-aria-components';
import s from "./segmented-control.module.css";
export interface SegmentedControlProps extends DOMProps {
    label: string;
    options: Option[];
    value?: string;
    defaultValue?: string;
    onChange?: (value: string) => void;
}
export function SegmentedControl({ label, options, value, defaultValue, onChange, className, ...props }: SegmentedControlProps) {
    const [selected, setSelected] = useControllableState(value, defaultValue ?? options.find(option => !option.disabled)?.id ?? '', onChange);
    return <A.ToggleButtonGroup {...props} aria-label={label} selectionMode="single" disallowEmptySelection selectedKeys={new Set(selected ? [selected] : [])} onSelectionChange={keys => { const key = Array.from(keys)[0]; if (key !== undefined)
        setSelected(String(key)); }} className={cx(s.segmented, className)}>
    {options.map(o => <A.ToggleButton key={o.id} id={o.id} isDisabled={o.disabled} className={s.segment}>{o.label}</A.ToggleButton>)}
  </A.ToggleButtonGroup>;
}
