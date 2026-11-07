import { useEffect, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  User,
  Car,
} from "lucide-react";
import { getRecentEvents } from "./api";
import {
  Badge,
  Empty,
  Field,
  Freshness,
  Notice,
  Panel,
} from "../../shared/components";
import { usePoll } from "../../shared/hooks";
import type { CameraEvent } from "./types";

const formatTime = (stamp: number) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(new Date(stamp * 1000));
function eventLabel(event: CameraEvent) {
  return event.category === "analytics"
    ? event.state
      ? "分析恢复"
      : "分析中断"
    : event.state
      ? "出现"
      : "消失";
}
export default function Events({
  visible,
  now,
}: {
  visible: boolean;
  now: number;
}) {
  const recent = usePoll(getRecentEvents, 2000, visible);
  const [category, setCategory] = useState("all");
  const [page, setPage] = useState(0);
  const data = recent.data;
  const stale =
    !recent.updatedAt || now - recent.updatedAt > 5000 || !!recent.error;
  const online = !stale && !!data?.status.online;
  const events = [...(data?.events || [])]
    .reverse()
    .sort((a, b) => b.frame_ts - a.frame_ts)
    .filter((event) => category === "all" || event.category === category);
  const pages = Math.max(1, Math.ceil(events.length / 20));
  useEffect(() => {
    setPage((value) => Math.min(value, pages - 1));
  }, [pages]);
  return (
    <div className="page-stack">
      <div className="page-action-row">
        <p className="page-description">
          记录人物、车辆存在状态的变化，以及分析源的中断与恢复。
        </p>
        <Freshness
          updatedAt={recent.updatedAt}
          now={now}
          error={!!recent.error}
        />
      </div>
      {recent.error && <Notice retry={recent.refresh}>{recent.error}</Notice>}
      <div className="event-status-grid">
        {[
          { category: "person", label: "人物存在", icon: User },
          { category: "vehicle", label: "车辆存在", icon: Car },
        ].map(({ category: key, label, icon: Icon }) => (
          <section className="presence-card" key={key}>
            <span className="service-icon">
              <Icon size={22} aria-hidden="true" />
            </span>
            <div>
              <span className="muted">{label}</span>
              <h2>
                {!online
                  ? "状态未知"
                  : data?.status.presence[key]
                    ? "当前存在"
                    : "当前未检出"}
              </h2>
              <p>
                {!online
                  ? data
                    ? `最近已知：${data.status.presence[key] ? "存在" : "未检出"}；等待分析恢复`
                    : "正在读取分析状态"
                  : "连续正常推理 2 秒未检出后，记录消失"}
              </p>
            </div>
            <Badge
              tone={online && data?.status.presence[key] ? "good" : "neutral"}
            >
              {online ? "在线" : "未知"}
            </Badge>
          </section>
        ))}
        <section className="presence-card">
          <span className="service-icon">
            <Activity size={22} aria-hidden="true" />
          </span>
          <div>
            <span className="muted">分析源</span>
            <h2>
              {stale
                ? "等待更新"
                : data?.status.online
                  ? "分析在线"
                  : "分析离线"}
            </h2>
            <p>{data?.status.last_error || "使用当前检测阈值与类别过滤配置"}</p>
          </div>
        </section>
      </div>
      <Panel
        title="近期事件"
        description="仅保留本次服务运行的最近 200 条，服务重启后清空"
        action={
          <span className="muted">{data?.events.length ?? 0} 条记录</span>
        }
      >
        <div className="event-filters">
          <Field label="事件类别">
            <select
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setPage(0);
              }}
            >
              <option value="all">全部事件</option>
              <option value="person">人物</option>
              <option value="vehicle">车辆</option>
              <option value="analytics">分析源</option>
            </select>
          </Field>
          <span className="muted">按时间倒序 · 每页 20 条</span>
        </div>
        {!data ? (
          <Empty title="正在读取事件记录…" />
        ) : !events.length ? (
          <Empty title="暂无匹配事件">
            正常状态变化后会自动记录，无需保持页面打开。
          </Empty>
        ) : (
          <div className="event-table">
            <div className="event-table-heading" aria-hidden="true">
              <span>时间</span>
              <span>事件</span>
              <span>来源</span>
              <span>详情</span>
            </div>
            {events.slice(page * 20, page * 20 + 20).map((event) => (
              <div className="event-record" key={event.id}>
                <time dateTime={new Date(event.frame_ts * 1000).toISOString()}>
                  {formatTime(event.frame_ts)}
                </time>
                <div className="event-name">
                  <span
                    className={`event-marker ${event.category === "analytics" && !event.state ? "bad" : event.state ? "good" : "neutral"}`}
                    aria-hidden="true"
                  />
                  <strong>
                    {event.category === "person"
                      ? "人物"
                      : event.category === "vehicle"
                        ? "车辆"
                        : ""}
                    {eventLabel(event)}
                  </strong>
                </div>
                <code>{event.source}</code>
                <details className="event-details">
                  <summary>
                    <span>查看详情</span>
                    <ChevronDown size={14} aria-hidden="true" />
                  </summary>
                  <dl>
                    <div>
                      <dt>UTC 时间</dt>
                      <dd>{new Date(event.frame_ts * 1000).toISOString()}</dd>
                    </div>
                    <div>
                      <dt>主题</dt>
                      <dd>{event.topic}</dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>{String(event.state)}</dd>
                    </div>
                    <div>
                      <dt>事件 ID</dt>
                      <dd>{event.id}</dd>
                    </div>
                  </dl>
                </details>
              </div>
            ))}
          </div>
        )}
        <div className="pagination">
          <span>
            第 {page + 1} / {pages} 页
          </span>
          <div className="button-row">
            <button
              className="button"
              aria-label="上一页事件"
              disabled={page === 0}
              onClick={() => setPage((value) => value - 1)}
            >
              <ChevronLeft size={16} aria-hidden="true" />
              上一页
            </button>
            <button
              className="button"
              aria-label="下一页事件"
              disabled={page + 1 >= pages}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </Panel>
      <Panel
        title="ONVIF 事件主题"
        description="供 NVR 与 CyberOS 发现和订阅的事件契约"
      >
        <p className="topic-namespace">
          命名空间 <code>urn:cybervisual:onvif:topics:1</code>
        </p>
        <div className="topic-grid">
          {[
            ["Analytics/PersonPresence", "人物存在状态"],
            ["Analytics/VehiclePresence", "车辆存在状态"],
            ["Device/AnalyticsOnline", "视频分析源在线状态"],
          ].map(([topic, label]) => (
            <div key={topic}>
              <strong>{label}</strong>
              <code>{topic}</code>
            </div>
          ))}
        </div>
        <p className="muted panel-note">
          车辆合并汽车、卡车、公交车、摩托车与自行车。视频或推理中断单独记录故障，不将中断时间视为无人或无车。
        </p>
      </Panel>
    </div>
  );
}
