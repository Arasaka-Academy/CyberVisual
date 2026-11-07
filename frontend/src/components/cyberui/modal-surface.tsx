// Generated from packages/react/src/modal-surface.tsx. Regenerate in CyberUI with pnpm registry:build; after installation, edit this file freely.
'use client';
import { type DialogProps } from "./dialog";
import { useCyberUI } from "./provider";
import * as A from 'react-aria-components';
import { cx } from "./shared";
import s from "./modal-surface.module.css";
import { IconButton } from "./icon-button";
export function ModalSurface({ title, trigger, children, isOpen, defaultOpen, onOpenChange, className, role = 'dialog', drawer = false, ...props }: DialogProps & {
    drawer?: boolean;
}) {
    const { t } = useCyberUI();
    const surface = <A.ModalOverlay isOpen={trigger ? undefined : isOpen} defaultOpen={trigger ? undefined : defaultOpen} onOpenChange={trigger ? undefined : onOpenChange} isDismissable className={cx(s.overlay, drawer && s.drawerOverlay)}><A.Modal className={cx(s.modal, drawer && s.drawer, className)}>
      <A.Dialog {...props} className={s.dialog} role={role}>{({ close }) => <><header className={s.dialogHead}><A.Heading slot="title">{title}</A.Heading><IconButton icon="close" aria-label={t('Close dialog', '关闭弹窗')} variant="ghost" onPress={close}/></header>{typeof children === 'function' ? children(close) : children}</>}</A.Dialog>
    </A.Modal></A.ModalOverlay>;
    return trigger ? <A.DialogTrigger isOpen={isOpen} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>{trigger}{surface}</A.DialogTrigger> : surface;
}
