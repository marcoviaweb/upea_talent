import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownToLine, Bell, BellRing, ClipboardList, FileBarChart2, LoaderCircle, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../../api";
import { auditActionFilterValue, auditActionLabel, auditObjectTypeLabel, auditResultLabel, auditRoleScopeLabel, auditScopeLabel } from "../../localization";
import { StatisticalBarChart, StatisticalLineChart, StatisticalPieChart } from "../../components/StatisticalCharts";
import "./e11.css";

type Career = { id: string; name: string; code: string; institutionId?: string };
type Period = { id: string; name: string; code: string; careerId: string };
type ReportRow = { career: string; careerCode: string; metric: string; value: number | string; definition: string; denominator: number };
type Notice = { id: string; kind: string; title: string; message: string; targetPath: string; createdAt: string; read: boolean };
type AuditEvent = { id: string; actor: string; roleScope: string; action: string; objectType: string; objectId: string; scope: string; result: string; reason: string; occurredAt: string };
type ChartPoint = { label: string; detail?: string; value: number };
type CareerCharts = { career: string; careerCode: string; activityByPeriod: ChartPoint[]; pointsDistribution: ChartPoint[]; evidenceStatuses: ChartPoint[]; opportunityStatuses: ChartPoint[]; applicationsByPeriod: ChartPoint[] };
type Report = { canManage: boolean; groupView?: boolean; personalView?: boolean; careers: Career[]; periods: Period[]; rows: ReportRow[]; charts?: CareerCharts[]; selectedPeriod: string; source?: string; extractedAt?: string; message?: string };
type AdminData = { careers: Career[]; gradeCareerIds:string[]; studentCareerIds:string[]; periods: Array<{id:string;careerId:string;careerCode:string;code:string;name:string;startsOn:string;endsOn:string;status:string}>; courses:Array<{id:string;careerId:string;careerCode:string;code:string;name:string;credits:number}>; offerings:Array<{id:string;courseId:string;periodId:string;label:string;status:string}>; students:Array<{id:string;institutionId:string;institution:string;studentNumber:string;name:string}>; enrollments:Array<{id:string;careerId:string;periodId:string;studentId:string;studentNumber:string;student:string;semester:number;status:string}> };

const dateLabel = (value: string) => new Intl.DateTimeFormat("es-BO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/La_Paz" }).format(new Date(value));

export default function E11Page() {
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [unread, setUnread] = useState(0);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [careerId, setCareerId] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [tab, setTab] = useState<"report" | "notifications" | "audit" | "admin">("report");
  const [adminData,setAdminData]=useState<AdminData|null>(null);
  const [adminKind,setAdminKind]=useState("period");
  const [adminCareer,setAdminCareer]=useState("");
  const [adminMessage,setAdminMessage]=useState("");
  const [adminBusy,setAdminBusy]=useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditFrom, setAuditFrom] = useState("");
  const [auditTo, setAuditTo] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPages, setAuditPages] = useState(1);

  async function loadReport(career = careerId, period = periodId) {
    const query = new URLSearchParams();
    if (career) query.set("career", career);
    if (period) query.set("period", period);
    const result = await api<Report>(`/api/v1/reports/${query.size ? `?${query}` : ""}`);
    setReport(result);
    if (!result.canManage && !result.personalView && !result.groupView) setTab("notifications");
  }
  async function loadNotifications() {
    const result = await api<{ unreadCount: number; items: Notice[] }>("/api/v1/notifications/");
    setNotices(result.items); setUnread(result.unreadCount);
  }
  async function loadAudit(page = auditPage) {
    const query = new URLSearchParams();
    if (careerId) query.set("career", careerId);
    if (auditAction) query.set("action", auditActionFilterValue(auditAction));
    if (auditFrom) query.set("from", auditFrom);
    if (auditTo) query.set("to", auditTo);
    query.set("page", String(page)); query.set("pageSize", "25");
    const result = await api<{ events: AuditEvent[]; pages: number }>(`/api/v1/audit/?${query}`);
    setAudit(result.events); setAuditPages(result.pages);
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
  }, [tab, report?.canManage, careerId, auditPage]);
  useEffect(()=>{if(tab==="admin"&&report?.canManage)void api<AdminData>("/api/v1/academic-admin/").then((data)=>{setAdminData(data);setAdminCareer((current)=>current||data.careers[0]?.id||"")}).catch((err)=>setError(errorMessage(err)))},[tab,report?.canManage]);

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
      {report?.canManage && <button className={tab === "admin" ? "active" : ""} onClick={() => setTab("admin")}><ShieldCheck size={17}/>Administración académica</button>}
    </nav>

    {tab === "report" && <>
      {report?.canManage && <section className="e11-panel e11-filters"><div><span className="eyebrow">ÁMBITO AUTORIZADO</span><h2>Indicadores de carrera</h2><p>Selecciona el alcance que necesitas revisar. El denominador y la definición se muestran junto a cada resultado.</p></div><div className="e11-filter-controls"><label>Carrera<select value={careerId} onChange={(e) => { setCareerId(e.target.value); setPeriodId(""); }}><option value="">Todas mis carreras</option>{report.careers.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label><label>Periodo<select value={periodId} onChange={(e) => setPeriodId(e.target.value)}><option value="">Todos los periodos</option>{periods.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label><a className="button button-primary e11-export" href={exportPath}><ArrowDownToLine size={16}/> Exportar CSV</a><button className="button button-secondary" onClick={() => window.print()}>Imprimir informe</button></div></section>}
      {(report?.canManage || report?.personalView || report?.groupView) ? <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">{report.personalView ? "RESUMEN PERSONAL" : report.groupView ? "RESUMEN DOCENTE" : "RESUMEN CUANTITATIVO"}</span><h2>{report.personalView ? "Mi trayectoria en cifras" : report.groupView ? "Indicadores de mis grupos" : "Estado de la trayectoria"}</h2></div><span className="e11-update">Actualizado {report.extractedAt ? dateLabel(report.extractedAt) : "ahora"}</span></div>
        {(report.canManage || report.groupView) && <div className="e11-chart-grid">{(report.charts ?? []).map((career) => <div className="e11-career-charts" key={career.careerCode}><h3>{career.careerCode} · {career.career}</h3><div className="e11-visuals"><StatisticalBarChart title="Actividad por periodo" description="Cantidad de evidencias registradas en cada periodo académico." data={career.activityByPeriod}/><StatisticalPieChart title="Distribución de puntos por nivel" description="Cantidad de matrículas en cada nivel de trayectoria." data={career.pointsDistribution}/><StatisticalPieChart title="Estado de evidencias" description="Proporción de evidencias según su estado actual." data={career.evidenceStatuses}/><StatisticalPieChart title={report.groupView ? "Estado de postulaciones" : "Estado de oportunidades"} description={report.groupView ? "Postulaciones asociadas a estudiantes de tus grupos." : "Proporción de oportunidades según su estado."} data={career.opportunityStatuses}/><StatisticalLineChart title="Evolución de postulaciones" description="Cantidad de postulaciones presentadas en cada periodo." data={career.applicationsByPeriod}/></div></div>)}</div>}
        <div className="e11-metric-grid" aria-label="Resumen visual de indicadores">{report.rows.map((row, index) => <article className="e11-metric-card" key={`${row.careerCode}-${row.metric}-${index}`}><span>{report.canManage && report.careers.length > 1 ? `${row.careerCode} · ` : ""}{row.metric}</span><strong>{row.value}</strong><small>Denominador: {row.denominator}</small></article>)}</div>
        <p className="e11-source">Fuente: {report.source} Las tarjetas describen indicadores con sus propias unidades; no sugieren relaciones causales ni dan acceso a expedientes privados.</p>
        <div className="e11-table-wrap"><table><caption>Tabla accesible equivalente al resumen visual</caption><thead><tr><th>{report.personalView ? "Alcance" : "Carrera"}</th><th>Indicador</th><th>Valor</th><th>Denominador</th><th>Definición</th></tr></thead><tbody>{report.rows.map((row, index) => <tr key={`${row.careerCode}-${row.metric}-${index}`}><td>{report.personalView ? "Mi trayectoria" : `${row.careerCode} · ${row.career}`}</td><td>{row.metric}</td><td>{row.value}</td><td>{row.denominator}</td><td>{row.definition}</td></tr>)}</tbody></table></div>
      </section> : <section className="e11-panel e11-empty"><div><ShieldCheck size={23}/></div><h2>Informes restringidos por ámbito</h2><p>{report?.message ?? "Tu rol no tiene acceso a informes agregados de carrera."} La bandeja de notificaciones sigue disponible.</p></section>}
    </>}

    {tab === "notifications" && <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">BANDEJA PERSONAL</span><h2>Avisos recientes</h2><p>El enlace vuelve a validar tu permiso al abrir cada módulo.</p></div><span className="e11-unread"><BellRing size={15}/>{unread} sin leer</span></div>{notices.length ? <div className="e11-notices">{notices.map((item) => <button className={`e11-notice ${item.read ? "is-read" : "is-unread"}`} key={item.id} onClick={() => void markRead(item)}><span className="e11-notice-icon"><Bell size={17}/></span><span className="e11-notice-copy"><strong>{item.title}</strong><span>{item.message}</span><small>{dateLabel(item.createdAt)}</small></span><span className="e11-notice-state">{item.read ? "Leída" : "Nueva"}</span></button>)}</div> : <div className="e11-empty-inline"><Bell size={23}/><strong>No tienes avisos nuevos</strong><span>Las actualizaciones de tus trámites aparecerán aquí.</span></div>}</section>}

    {tab === "admin" && report?.canManage && <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">OPERACIÓN ACADÉMICA</span><h2>Administración de carrera</h2><p>Registra estudiantes, periodos, asignaturas, grupos, matrículas y notas verificadas dentro de tu ámbito. Cada acción queda en bitácora.</p></div></div>{adminMessage&&<p className="e11-admin-message" role="status">{adminMessage}</p>}<form className="e11-admin-form" onSubmit={async(event)=>{event.preventDefault();const formNode=event.currentTarget;const form=new FormData(formNode);setAdminBusy(true);setAdminMessage("");const payload:Record<string,unknown>={kind:adminKind,careerId:adminCareer,reason:String(form.get("reason")||"")};for(const key of ["code","name","startsOn","endsOn","status","gradeScale","passThreshold","credits","courseId","periodId","groupCode","studentId","semester","validFrom","firstName","lastName","username","email","studentNumber","password","enrollmentId","gradeValue","source","sourceReference"])if(form.has(key)&&form.get(key))payload[key]=form.get(key);try{await api("/api/v1/academic-admin/",{method:"POST",body:JSON.stringify(payload)});setAdminMessage("El registro se guardó y quedó asentado en la bitácora.");const data=await api<AdminData>("/api/v1/academic-admin/");setAdminData(data);formNode.reset()}catch(err){setAdminMessage(errorMessage(err))}finally{setAdminBusy(false)}}}>
      <label>Tipo de registro<select value={adminKind} onChange={(e)=>setAdminKind(e.target.value)}><option value="period">Periodo académico</option><option value="course">Asignatura</option><option value="offering">Grupo de asignatura</option>{adminData?.studentCareerIds.includes(adminCareer)&&<option value="student">Alta de estudiante</option>}<option value="enrollment">Matrícula</option>{adminData?.gradeCareerIds.includes(adminCareer)&&<option value="grade">Nota académica</option>}</select></label><label>Carrera<select required value={adminCareer} onChange={(e)=>{const id=e.target.value;setAdminCareer(id);if(adminKind==="student"&&!adminData?.studentCareerIds.includes(id)||adminKind==="grade"&&!adminData?.gradeCareerIds.includes(id))setAdminKind("period")}}>{(adminData?.careers??[]).map(c=><option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></label>
      {adminKind==="period"&&<><label>Código<input required name="code" maxLength={32}/></label><label>Nombre<input required name="name" maxLength={120}/></label><label>Inicio<input required name="startsOn" type="date"/></label><label>Fin<input required name="endsOn" type="date"/></label><label>Estado<select name="status"><option value="planned">Planificado</option><option value="open">Abierto</option><option value="closed">Cerrado</option></select></label><label>Escala de notas<input name="gradeScale" type="number" min="1" step="0.01" defaultValue="100"/></label><label>Nota mínima<input name="passThreshold" type="number" min="0" step="0.01" defaultValue="51"/></label></>}
      {adminKind==="course"&&<><label>Código<input required name="code" maxLength={24}/></label><label>Nombre<input required name="name" maxLength={180}/></label><label>Créditos<input name="credits" type="number" min="0" max="32767" defaultValue="0"/></label></>}
      {adminKind==="student"&&<><label>Nombres<input required name="firstName" maxLength={150}/></label><label>Apellidos<input required name="lastName" maxLength={150}/></label><label>Usuario institucional<input required name="username" maxLength={150}/></label><label>Correo institucional<input required name="email" type="email" maxLength={254}/></label><label>Número de estudiante<input required name="studentNumber" maxLength={32}/></label><label>Contraseña inicial<input required name="password" type="password" autoComplete="new-password" minLength={10}/><small>Se validará con la política de contraseñas del sistema.</small></label></>}
      {adminKind==="offering"&&<><label>Asignatura<select required name="courseId">{(adminData?.courses??[]).filter(c=>c.careerId===adminCareer).map(c=><option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></label><label>Periodo<select required name="periodId">{(adminData?.periods??[]).filter(p=>p.careerId===adminCareer).map(p=><option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select></label><label>Código de grupo<input required name="groupCode" maxLength={24}/></label><label>Estado<select name="status"><option value="planned">Planificado</option><option value="open">Abierto</option><option value="closed">Cerrado</option></select></label></>}
      {adminKind==="enrollment"&&<><label>Estudiante<select required name="studentId">{(adminData?.students??[]).filter(s=>s.institutionId===adminData?.careers.find(c=>c.id===adminCareer)?.institutionId).map(s=><option key={s.id} value={s.id}>{s.studentNumber} · {s.name}</option>)}</select><small>La selección se valida nuevamente en el servidor.</small></label><label>Periodo<select required name="periodId">{(adminData?.periods??[]).filter(p=>p.careerId===adminCareer).map(p=><option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select></label><label>Semestre<input name="semester" type="number" min="1" max="30" defaultValue="1"/></label><label>Fecha de vigencia<input name="validFrom" type="date"/></label></>}
      {adminKind==="grade"&&<><label>Matrícula<select required name="enrollmentId">{(adminData?.enrollments??[]).filter(e=>e.careerId===adminCareer).map(e=><option key={e.id} value={e.id}>{e.studentNumber} · {e.student} · {e.periodId}</option>)}</select></label><label>Grupo / asignatura<select required name="offeringId">{(adminData?.offerings??[]).filter(o=>adminData?.courses.some(c=>c.id===o.courseId&&c.careerId===adminCareer)).map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select></label><label>Calificación<input required name="gradeValue" type="number" min="0" step="0.01"/></label><label>Origen verificable<input required name="source" maxLength={120} placeholder="Acta o registro académico"/></label><label>Referencia del documento<input name="sourceReference" maxLength={160}/></label></>}
      <label className="e11-admin-reason">Motivo del registro<input name="reason" maxLength={300} placeholder="Describe brevemente el motivo"/></label><button className="button button-primary" disabled={adminBusy||!adminCareer}>{adminBusy?"Guardando…":"Registrar"}</button></form><div className="e11-admin-inventory"><h3>Registros en tu ámbito</h3><p>{adminData?.periods.length??0} periodos · {adminData?.courses.length??0} asignaturas · {adminData?.offerings.length??0} grupos · {adminData?.students.length??0} estudiantes · {adminData?.enrollments.length??0} matrículas</p></div></section>}

    {tab === "audit" && report?.canManage && <section className="e11-panel"><div className="e11-section-heading"><div><span className="eyebrow">SOLO LECTURA</span><h2>Bitácora de operaciones</h2><p>Eventos autorizados con filtros, descarga y paginación. Las respuestas individuales de evaluación permanecen anónimas.</p></div><span className="e11-readonly"><ShieldCheck size={15}/>Inmutable</span></div><div className="e11-audit-filters"><label>Acción<input value={auditAction} onChange={(e) => setAuditAction(e.target.value)} placeholder="Ej. Evidencia aprobada"/></label><label>Desde<input type="date" value={auditFrom} onChange={(e) => setAuditFrom(e.target.value)}/></label><label>Hasta<input type="date" value={auditTo} onChange={(e) => setAuditTo(e.target.value)}/></label><button className="button button-secondary" onClick={() => {setAuditPage(1);void loadAudit(1).catch((err) => setError(errorMessage(err)));}}>Aplicar filtros</button><a className="button button-secondary" href={`/api/v1/audit/?${new URLSearchParams({ ...(careerId?{career:careerId}:{}), ...(auditAction?{action:auditActionFilterValue(auditAction)}:{}), ...(auditFrom?{from:auditFrom}:{}), ...(auditTo?{to:auditTo}:{}), export:"csv" })}`}><ArrowDownToLine size={15}/> Exportar bitácora</a></div><div className="e11-table-wrap"><table><caption>Eventos de auditoría dentro de tu ámbito</caption><thead><tr><th>Fecha</th><th>Actor y rol</th><th>Acción</th><th>Objeto</th><th>Ámbito</th><th>Resultado y motivo</th></tr></thead><tbody>{audit.map((item) => <tr key={item.id}><td>{dateLabel(item.occurredAt)}</td><td>{item.actor}<small>{auditRoleScopeLabel(item.roleScope)}</small></td><td><code>{auditActionLabel(item.action)}</code></td><td>{auditObjectTypeLabel(item.objectType)}<small>{item.objectId}</small></td><td>{auditScopeLabel(item.scope)}</td><td>{auditResultLabel(item.result)}<small>{item.reason || "—"}</small></td></tr>)}</tbody></table>{audit.length === 0 && <p className="e11-no-events">No hay eventos para esos filtros.</p>}</div><div className="e11-pagination"><span>Página {auditPage} de {auditPages}</span><div><button className="button button-secondary" disabled={auditPage<=1} onClick={()=>setAuditPage((p)=>p-1)}>Anterior</button><button className="button button-secondary" disabled={auditPage>=auditPages} onClick={()=>setAuditPage((p)=>p+1)}>Siguiente</button></div></div></section>}
  </div>;
}

