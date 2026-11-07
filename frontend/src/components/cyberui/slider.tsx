// Generated from packages/react/src/slider.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import * as A from 'react-aria-components';
import { type Ref } from 'react';
import { cx } from "./shared";
import s from "./slider.module.css";
import fieldStyles from "./field.module.css";
export interface SliderProps extends Omit<A.SliderProps<number>, 'children' | 'className'> {
    label: string;
    className?: string;
    ref?: Ref<HTMLDivElement>;
}
export function Slider({ label, className, ...props }: SliderProps) {
    return <A.Slider {...props} className={cx(fieldStyles.field, className)}><div className={s.sliderHead}><A.Label className={fieldStyles.label}>{label}</A.Label><A.SliderOutput /></div><A.SliderTrack className={s.sliderTrack}><A.SliderThumb className={s.sliderThumb}/></A.SliderTrack></A.Slider>;
}
