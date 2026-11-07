import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../shared/api";
import { usePoll, errorMessage } from "../../shared/hooks";
import { getConfig, updateConfig } from "./api";
import {
  GROUPS,
  groupDirty,
  mergePatch,
  normalizeConfig,
  selectGroup,
} from "./model";
import type { ConfigGroup } from "./model";
import type { RuntimeConfig, ConfigPatch } from "./types";
export function useConfigManager(visible: boolean) {
  const [applied, setApplied] = useState<RuntimeConfig | null>(null);
  const [draft, setDraft] = useState<RuntimeConfig | null>(null);
  const appliedRef = useRef<RuntimeConfig | null>(null);
  const pending = useRef(false);
  // A read started before a mutation must never replace the confirmed result.
  const writeVersion = useRef(0);
  const [saving, setSaving] = useState<ConfigGroup | null>(null);
  const [errors, setErrors] = useState<Partial<Record<ConfigGroup, string>>>(
    {},
  );
  const [notices, setNotices] = useState<Partial<Record<ConfigGroup, string>>>(
    {},
  );
  const readConfig = useCallback(async (signal?: AbortSignal) => {
    const version = writeVersion.current;
    const config = await getConfig(signal);
    return { version, config };
  }, []);
  const remote = usePoll(readConfig, 0, visible && saving === null);
  const apply = useCallback((value: RuntimeConfig, saved?: ConfigGroup) => {
    const next = normalizeConfig(value);
    const previous = appliedRef.current;
    appliedRef.current = next;
    setApplied(next);
    setDraft((current) => {
      if (!current || !previous) return next;
      return GROUPS.reduce(
        (result, group) =>
          saved === group || !groupDirty(current, previous, group)
            ? mergePatch(result, selectGroup(next, group))
            : result,
        current,
      );
    });
  }, []);
  useEffect(() => {
    if (
      remote.data &&
      remote.data.version === writeVersion.current &&
      !pending.current
    )
      apply(remote.data.config);
  }, [remote.data, apply]);
  const edit = (patch: ConfigPatch) =>
    setDraft((current) => (current ? mergePatch(current, patch) : current));
  const reset = (group: ConfigGroup) => {
    if (applied)
      setDraft((current) =>
        current ? mergePatch(current, selectGroup(applied, group)) : current,
      );
    setErrors((current) => ({ ...current, [group]: "" }));
    setNotices((current) => ({ ...current, [group]: "" }));
  };
  const save = async (group: ConfigGroup) => {
    if (!draft || pending.current) return;
    pending.current = true;
    writeVersion.current += 1;
    setSaving(group);
    setErrors((current) => ({ ...current, [group]: "" }));
    setNotices((current) => ({ ...current, [group]: "" }));
    const patch = selectGroup(draft, group);
    try {
      apply(await updateConfig(patch), group);
      setNotices((current) => ({
        ...current,
        [group]:
          group === "network" || group === "ptz"
            ? "配置已保存，运行结果请查看协议与云台状态。"
            : "配置已保存并应用。",
      }));
    } catch (failure) {
      if (failure instanceof ApiError && failure.timeout) {
        try {
          const confirmed = normalizeConfig(await getConfig());
          const matches =
            JSON.stringify(selectGroup(confirmed, group)) ===
            JSON.stringify(patch);
          apply(confirmed, matches ? group : undefined);
          if (matches)
            setNotices((current) => ({
              ...current,
              [group]: "已重新读取设备，确认配置保存成功。",
            }));
          else
            setErrors((current) => ({
              ...current,
              [group]:
                "写入超时；已读取当前配置，草稿尚未应用，请检查后再保存。",
            }));
        } catch {
          setErrors((current) => ({
            ...current,
            [group]: "写入结果尚未确认。草稿已保留，请恢复连接后重新读取配置。",
          }));
        }
      } else
        setErrors((current) => ({
          ...current,
          [group]: errorMessage(failure),
        }));
    } finally {
      pending.current = false;
      setSaving(null);
      remote.refresh();
    }
  };
  const dirty = GROUPS.some((group) => groupDirty(draft, applied, group));
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return {
    applied,
    draft,
    saving,
    errors,
    notices,
    edit,
    reset,
    save,
    dirty,
    dirtyGroup: (group: ConfigGroup) => groupDirty(draft, applied, group),
    error: remote.error,
    loading: !applied && remote.loading,
    retry: remote.refresh,
  };
}
export type ConfigManager = ReturnType<typeof useConfigManager>;
