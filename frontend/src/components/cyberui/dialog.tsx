// Generated from packages/react/src/dialog.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DOMProps } from "./shared";
import { type ReactElement, type ReactNode } from 'react';
import { ModalSurface } from "./modal-surface";
export interface DialogProps extends Omit<DOMProps, 'role'> {
    title: string;
    trigger?: ReactElement;
    children: ReactNode | ((close: () => void) => ReactNode);
    isOpen?: boolean;
    defaultOpen?: boolean;
    onOpenChange?: (open: boolean) => void;
    role?: 'dialog' | 'alertdialog';
}
export function Dialog(props: DialogProps) { return <ModalSurface {...props}/>; }
