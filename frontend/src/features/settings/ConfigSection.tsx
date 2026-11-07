import { Button } from "../../shared/controls";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { AlertCircle, Check, Save } from "lucide-react";
import { Panel, Notice, Empty } from "../../shared/components";
import type { ConfigGroup } from "./model";
import type { ConfigManager } from "./useConfigManager";
export function ConfigSection({
  manager,
  group,
  title,
  description,
  children,
  warning,
}: {
  manager: ConfigManager;
  group: ConfigGroup;
  title: string;
  description: string;
  children: ReactNode;
  warning?: string;
}) {
  const errorRef = useRef<HTMLDivElement>(null);
  const error = manager.errors[group];
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  return (
    <Panel title={title} description={description}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void manager.save(group);
        }}
      >
        <fieldset
          disabled={manager.saving !== null || !manager.applied}
          className="form-fields"
        >
          {children}
        </fieldset>
        {warning && (
          <p className="form-warning">
            <AlertCircle size={15} aria-hidden="true" />
            {warning}
          </p>
        )}
        {error && (
          <div ref={errorRef} tabIndex={-1}>
            <Notice>{error}</Notice>
          </div>
        )}
        {manager.notices[group] && (
          <div className="save-notice" role="status">
            <Check size={16} aria-hidden="true" />
            {manager.notices[group]}
          </div>
        )}
        <div className="form-footer">
          <span
            className={manager.dirtyGroup(group) ? "unsaved-label" : "muted"}
          >
            {manager.dirtyGroup(group) ? "有未保存的修改" : "与设备配置一致"}
          </span>
          <div className="button-row">
            <Button
              type="button"
              disabled={!manager.dirtyGroup(group) || manager.saving !== null}
              onClick={() => manager.reset(group)}
            >
              撤销修改
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={!manager.dirtyGroup(group) || manager.saving !== null}
            >
              <Save size={16} aria-hidden="true" />
              {manager.saving === group ? "保存中…" : "保存配置"}
            </Button>
          </div>
        </div>
      </form>
    </Panel>
  );
}
export function ConfigUnavailable({ manager }: { manager: ConfigManager }) {
  return manager.error ? (
    <Notice retry={manager.retry}>{manager.error}</Notice>
  ) : (
    <Empty title="正在读取设备配置…" />
  );
}
