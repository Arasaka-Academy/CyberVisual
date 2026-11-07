// Generated from packages/react/src/select.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DOMProps, cx } from "./shared";
import { type Option } from "./option";
import { type Ref } from 'react';
import * as A from 'react-aria-components';

import { Icon } from "./icon";
import fieldStyles from "./field.module.css";
import choiceStyles from "./choice.module.css";
import popoverStyles from "./popover.module.css";
export interface SelectProps extends DOMProps {
    label: string;
    options: Option[];
    value?: string;
    defaultValue?: string;
    onChange?: (value: string) => void;
    placeholder?: string;
    isDisabled?: boolean;
    name?: string;
    description?: string;
    buttonRef?: Ref<HTMLButtonElement>;
}
export function Select({ label, options, value, defaultValue, onChange, placeholder, isDisabled, name, description, className, buttonRef, ...props }: SelectProps) {
    return <A.Select {...props} disabledKeys={options.filter(o => o.disabled).map(o => o.id)} selectedKey={value} defaultSelectedKey={defaultValue} onSelectionChange={key => onChange?.(String(key))} isDisabled={isDisabled} name={name} placeholder={placeholder} className={cx(fieldStyles.field, className)}>
    <A.Label className={fieldStyles.label}>{label}</A.Label><A.Button ref={buttonRef} className={choiceStyles.selectButton}><A.SelectValue /><Icon name="down" size={16}/></A.Button>
    <A.Popover className={popoverStyles.popover}><A.ListBox items={options} className={choiceStyles.listBox}>{o => <A.ListBoxItem id={o.id} textValue={o.label} className={choiceStyles.listItem}>{o.label}</A.ListBoxItem>}</A.ListBox></A.Popover>
    {description && <A.Text slot="description" className={fieldStyles.helper}>{description}</A.Text>}
  </A.Select>;
}
