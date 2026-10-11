import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownToLine, Bell, BellRing, ClipboardList, FileBarChart2, LoaderCircle, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../../api";
import { auditActionFilterValue, auditActionLabel, auditObjectTypeLabel, auditResultLabel, auditRoleScopeLabel, auditScopeLabel } from "../../localization";
import "./e11.css";

type Career = { id: string; name: string; code: string };
type Period = { id: string; name: string; code: string; careerId: string };
type ReportRow = { career: string; careerCode: string; metric: string; value: number | string; definition: string; denominator: number };
type Notice = { id: string; kind: string; title: string; message: string; targetPath: string; createdAt: string; read: boolean };
type AuditEvent = { id: string; actor: string; roleScope: string; action: string; objectType: string; objectId: string; scope: string; result: string; reason: string; occurredAt: string };
type Report = { canManage: boolean; personalView?: boolean; careers: Career[]; periods: Period[]; rows: ReportRow[]; selectedPeriod: string; source?: string; extractedAt?: string; message?: string };

const dateLabel = (value: string) => new Intl.DateTimeFormat("es-BO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/La_Paz" }).format(new Date(value));

export default function E11Page() {
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [unread, setUnread] = useState(0);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [careerId, setCareerId] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [tab, setTab] = useState<"report" | "notifications" | "audit">("report");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditFrom, setAuditFrom] = useState("");
  const [auditTo, setAuditTo] = useState("");

  async function loadReport(career = careerId, period = periodId) {
    const query = new URLSearchParams();
    if (career) query.set("career", career);
    if (period) query.set("period", period);
    const result = await api<Report>(`/api/v1/reports/${query.size ? `?${query}` : ""}`);
    setReport(result);
    if (!result.canManage && !result.personalView) setTab("notifications");
  }
  async function loadNotifications() {
    const result = await api<{ unreadCount: number; items: Notice[] }>("/api/v1/notifications/");
    setNotices(result.items); setUnread(result.unreadCount);
  }
  async function loadAudit() {
    const query = new URLSearchParams();
    if (careerId) query.set("career", careerId);
    if (auditAction) query.set("action", auditActionFilterValue(auditAction));
    if (auditFrom) query.set("from", auditFrom);
    if (auditTo) query.set("to", auditTo);
    const result = await api<{ events: AuditEvent[] }>(`/api/v1/audit/${query.size ? `?${query}` : ""}`);
    setAudit(result.events);
  }
  useEffect(() => {
    setBusy(true); setError("");
    Promise.all([loadReport("", ""), loadNotifications()]).catch((err) => setError(errorMessage(err))).finally(() => setBusy(false));
  }, []);
  useEffect(() => {
    if (report?.canManage) void loadReport(careerId, periodId).catch((err) => setError(errorMessage(err)));
  }, [careerId, periodId, report?.canManage]);
  useEffect(() => {
    if (tab === "audit" && report?.canManage) void loadAudit().catch((err) => setError(errorMessage(err)));
  }, [tab, report?.canManage, careerId]);

  const periods = useMemo(() => report?.periods.filter((row) => !careerId || row.careerId === careerId) ?? [], [report?.periods, careerId]);
  const exportPath = `/api/v1/reports/?${new URLSearchParams({ ...(careerId ? { career: careerId } : {}), ...(periodId ? { period: periodId } : {}), export: "csv" })}`;

  async function markRead(item: Notice) {
    if (!item.read) {
      try { await api(`/api/v1/notifications/${item.id}/read/`, { method: "POST" }); await loadNotifications(); }
      catch (err) { setError(errorMessage(err)); return; }
    }
    if (item.targetPath.startsWith("/trayectoria/") && !item.targetPath.startsWith("//")) navigate(item.targetPath);
  }

  if (busy) return <div className="e11-loading" role="status"><LoaderCircle className="spin" size={20} /> Preparando informes y notificaciones…</div>;
  return <div className="page-stack e11-page">
    <section className="welcome-hero">
      <div className="welcome-copy"><span className="eyebrow hero-eyebrow"><FileBarChart2 size={14} /> GESTIÓN ACADÉMICA</span><h1>Gestión y <span className="wave">análisis.</span></h1><p>Indicadores claros para dar seguimiento a cada carrera, junto con una bandeja de avisos y una bitácora consultable por ámbito autorizado.</p><div className="hero-note"><span className="hero-note-icon"><ShieldCheck size={15} /></span><span><strong>Información según tu rol.</strong> Los informes se calculan en servidor y respetan carrera y periodo.</span></div></div>
      <div className="hero-art" aria-hidden="true"><div className="hero-art-ring ring-a"/><div className="hero-art-ring ring-b"/><div className="hero-art-ring ring-c"/><div className="hero-art-core"><Activity size={32}/></div><span className="art-star star-a">✳</span><span className="art-star star-b">✦</span><span className="art-orbit-label label-a">OBSERVA</span><span className="art-orbit-label label-b">ANALIZA</span><span className="art-orbit-label label-c">MEJORA</span></div>
    </section>
    {error && <div className="error-banner" role="alert">{error}<button className="text-button" onClick={() => { setError(""); void Promise.all([loadNotifications(), loadReport()]).catch((err) => setError(errorMessage(err))); }}>Reintentar</button></div>}
    <nav className="e11-tabs" aria-label="Gestión y análisis">
      <button className={tab === "report" ? "active" : ""} onClick={() => setTab("report")}><FileBarChart2 size={17}/>Informes</button>
      <button className={tab === "notifications" ? "active" : ""} onClick={() => setTab("notifications")}><Bell size={17}/>Notificaciones{unread > 0 && <span>{unread}</span>}</button>
      {report?.canManage && <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}><ClipboardList size={17}/>Bitácora</button>}
    </nav>

    {tab === "report" && <>
      {report?.canManage && <section className="e11-panel e11-filters"><div><span className="eyebrow">ÁMBITO AUTORIZADO</span><h2>Indicadores de carrera</h2><p>Selecciona el alcance que necesitas revisar. El denominador y la definición se muestran junto a cada resultado.</p></div><div className="e11-filter-controls"><label>Carrera<select value={careerId} onChange={(e) => { setCareerId(e.target.value); setPeriodId(""); }}><option value="">Todas mis carreras</option>{report.careers.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label><label>Periodo<select value={periodId} onChange={(e) => setPeriodId(e.target.value)}><option value="">Todos los periodos</option>{periods.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label><a className="button button-primary e11-export" href={exportPath}><ArrowDownToLine size={16}/> Exportar CSV</a><button className="button button-secondary" onClick={() => window.print()}>Imprimir informe</button></div></section>}
      {(report?.canManage || report?.personalView) ? <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">{report.personalView ? "RESUMEN PERSONAL" : "RESUMEN CUANTITATIVO"}</span><h2>{report.personalView ? "Mi trayectoria en cifras" : "Estado de la trayectoria"}</h2></div><span className="e11-update">Actualizado {report.extractedAt ? dateLabel(report.extractedAt) : "ahora"}</span></div>
        <div className="e11-metric-grid" aria-label="Resumen visual de indicadores">{report.rows.map((row, index) => <article className="e11-metric-card" key={`${row.careerCode}-${row.metric}-${index}`}><span>{report.canManage && report.careers.length > 1 ? `${row.careerCode} · ` : ""}{row.metric}</span><strong>{row.value}</strong><small>Denominador: {row.denominator}</small></article>)}</div>
        <p className="e11-source">Fuente: {report.source} Las tarjetas describen indicadores con sus propias unidades; no sugieren relaciones causales ni dan acceso a expedientes privados.</p>
        <div className="e11-table-wrap"><table><caption>Tabla accesible equivalente al resumen visual</caption><thead><tr><th>{report.personalView ? "Alcance" : "Carrera"}</th><th>Indicador</th><th>Valor</th><th>Denominador</th><th>Definición</th></tr></thead><tbody>{report.rows.map((row, index) => <tr key={`${row.careerCode}-${row.metric}-${index}`}><td>{report.personalView ? "Mi trayectoria" : `${row.careerCode} · ${row.career}`}</td><td>{row.metric}</td><td>{row.value}</td><td>{row.denominator}</td><td>{row.definition}</td></tr>)}</tbody></table></div>
      </section> : <section className="e11-panel e11-empty"><div><ShieldCheck size={23}/></div><h2>Informes restringidos por ámbito</h2><p>{report?.message ?? "Tu rol no tiene acceso a informes agregados de carrera."} La bandeja de notificaciones sigue disponible.</p></section>}
    </>}

    {tab === "notifications" && <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">BANDEJA PERSONAL</span><h2>Avisos recientes</h2><p>El enlace vuelve a validar tu permiso al abrir cada módulo.</p></div><span className="e11-unread"><BellRing size={15}/>{unread} sin leer</span></div>{notices.length ? <div className="e11-notices">{notices.map((item) => <button className={`e11-notice ${item.read ? "is-read" : "is-unread"}`} key={item.id} onClick={() => void markRead(item)}><span className="e11-notice-icon"><Bell size={17}/></span><span className="e11-notice-copy"><strong>{item.title}</strong><span>{item.message}</span><small>{dateLabel(item.createdAt)}</small></span><span className="e11-notice-state">{item.read ? "Leída" : "Nueva"}</span></button>)}</div> : <div className="e11-empty-inline"><Bell size={23}/><strong>No tienes avisos nuevos</strong><span>Las actualizaciones de tus trámites aparecerán aquí.</span></div>}</section>}

    {tab === "audit" && report?.canManage && <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">SOLO LECTURA</span><h2>Bitácora de operaciones</h2><p>Máximo 200 eventos recientes del ámbito autorizado. Las respuestas individuales de evaluación no se registran ni se consultan aquí.</p></div><span className="e11-readonly"><ShieldCheck size={15}/>Inmutable</span></div><div className="e11-audit-filters"><label>Acción<input value={auditAction} onChange={(e) => setAuditAction(e.target.value)} placeholder="Ej. Evidencia aprobada"/></label><label>Desde<input type="date" value={auditFrom} onChange={(e) => setAuditFrom(e.target.value)}/></label><label>Hasta<input type="date" value={auditTo} onChange={(e) => setAuditTo(e.target.value)}/></label><button className="button button-secondary" onClick={() => void loadAudit().catch((err) => setError(errorMessage(err)))}>Aplicar filtros</button></div><div className="e11-table-wrap"><table><caption>Eventos recientes de auditoría dentro de tu ámbito</caption><thead><tr><th>Fecha</th><th>Actor y rol</th><th>Acción</th><th>Objeto</th><th>Ámbito</th><th>Resultado y motivo</th></tr></thead><tbody>{audit.map((item) => <tr key={item.id}><td>{dateLabel(item.occurredAt)}</td><td>{item.actor}<small>{auditRoleScopeLabel(item.roleScope)}</small></td><td><code>{auditActionLabel(item.action)}</code></td><td>{auditObjectTypeLabel(item.objectType)}<small>{item.objectId}</small></td><td>{auditScopeLabel(item.scope)}</td><td>{auditResultLabel(item.result)}<small>{item.reason || "—"}</small></td></tr>)}</tbody></table>{audit.length === 0 && <p className="e11-no-events">No hay eventos para esos filtros.</p>}</div></section>}
  </div>;
}
