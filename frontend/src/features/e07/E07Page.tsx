import { useEffect, useState, type FormEvent } from "react";
import { Award, ArrowRight, BadgeCheck, BriefcaseBusiness, CalendarDays, Check, CheckCircle2, CircleAlert, Clock3, FileCheck2, LoaderCircle, Plus, RefreshCw, ShieldCheck, Sparkles, UsersRound, XCircle } from "lucide-react";
import { api, errorMessage } from "../../api";
import { applicationStatusLabel, opportunityStatusLabel, requirementStatusLabel } from "../../localization";
import "./e07.css";

type Requirement = { id: string; field: string; label: string; operator: string; target: string | null; courseCode: string; periodCode: string };
type EligibilityRow = { id: string; label: string; field: string; operator: string; target: string | null; value: string | number | null; status: "meets" | "does_not_meet" | "insufficient"; source: string };
type Evaluation = { id: string; overall: "eligible" | "ineligible" | "insufficient"; computedAt: string; requirements: EligibilityRow[] };
type Application = { id: string; versionId: string; title: string; newVersionId: string | null; newVersionTitle: string | null; status: string; statusLabel: string; submittedAt: string; student: string; studentNumber: string; career: string; period: string; initialEligibility: EligibilityRow[]; initialOverall: string; currentEligibility: EligibilityRow[]; eligibilityChanged: boolean; latestDecision: null | { decision: string; reason: string; actor: string; at: string; previousStatus: string } };
type Version = { id: string; versionId: string; version: number; title: string; kind: string; kindLabel: string; description: string; benefits: string; instructions: string; opensAt: string; closesAt: string; capacity: number; status: string; publishedAt: string | null; careers: Array<{ id: string; code: string; name: string }>; requirements: Requirement[]; eligibility?: Evaluation; applications?: Application[] };
type Enrollment = { id: string; career: string; careerName: string; period: string; periodName: string; semester: number };
type Dataset = { opportunities: Version[]; enrollments: Enrollment[]; applications: Application[]; managed: Version[]; careers: Array<{ id: string; code: string; name: string }>; periods: Array<{ id: string; code: string; name: string; career: string }> };
type RequirementInput = { field: string; label: string; target?: string; courseCode?: string; periodCode?: string };
const numericRequirements = new Set(["average", "own_points", "semester"]);
const requirementLabels: Record<string, string> = {
  average: "Promedio simple verificado mínimo", own_points: "Puntos SPD propios mínimos",
  semester: "Semestre mínimo", period: "Periodo académico", validated_project: "Participación en al menos un proyecto validado",
  validated_activity: "Participación en al menos una actividad verificada",
  approved_course: "Curso aprobado", validated_skill: "Al menos una habilidad validada",
};
const researchRequirements: RequirementInput[] = [
  { field: "average", label: requirementLabels.average, target: "70" },
  { field: "own_points", label: requirementLabels.own_points, target: "100" },
  { field: "validated_project", label: requirementLabels.validated_project },
  { field: "approved_course", label: "Curso de investigación aprobado", courseCode: "MET201" },
];

const fmt = (value: string) => new Intl.DateTimeFormat("es-BO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
const localInput = (value?: string, days = 1) => {
  const date = value ? new Date(value) : new Date(Date.now() + days * 86400000);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16);
};

export default function E07Page() {
  const [data, setData] = useState<Dataset | null>(null);
  const [enrollmentId, setEnrollmentId] = useState("");
  const [selected, setSelected] = useState<Version | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [editing, setEditing] = useState<Version | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState<"discover" | "manage">("discover");

  async function load() {
    setError("");
    try {
      const result = await api<Dataset>("/api/v1/opportunities/");
      setData(result);
      setEnrollmentId((current) => current && result.enrollments.some((e) => e.id === current) ? current : result.enrollments[0]?.id ?? "");
      if (selected) setSelected(result.opportunities.find((o) => o.versionId === selected.versionId) ?? null);
    } catch (err) { setError(errorMessage(err)); }
  }
  useEffect(() => { void load(); }, []);

  const enrollment = data?.enrollments.find((row) => row.id === enrollmentId);
  const submitted = data?.applications.length ?? 0;
  const openCount = data?.opportunities.filter((o) => o.status === "published" && Date.now() < new Date(o.closesAt).getTime()).length ?? 0;

  async function inspect(opportunity: Version) {
    setSelected(opportunity); setEvaluation(null); setError("");
    if (!enrollmentId) return;
    setBusy(true);
    try { const result = await api<Evaluation>(`/api/v1/opportunity-versions/${opportunity.versionId}/eligibility/`, { method: "POST", body: JSON.stringify({ enrollmentId }) }); setEvaluation(result); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function apply(opportunity: Version) {
    if (!enrollmentId) return;
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/v1/opportunity-versions/${opportunity.versionId}/apply/`, { method: "POST", body: JSON.stringify({ enrollmentId }) }); setNotice("Tu postulación quedó registrada con esta versión de los requisitos."); await load(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function withdraw(id: string) {
    setBusy(true); setError("");
    try { await api(`/api/v1/applications/${id}/withdraw/`, { method: "POST", body: "{}" }); await load(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function saveOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const form = new FormData(event.currentTarget);
    const selectedCareers = [...event.currentTarget.querySelectorAll<HTMLInputElement>('input[name="careerIds"]:checked')].map((input) => input.value);
    const requirementRows = [...event.currentTarget.querySelectorAll<HTMLElement>("[data-requirement-row]")];
    const requirements: RequirementInput[] = requirementRows.map((row) => {
      const field = row.querySelector<HTMLSelectElement>(".requirement-field")?.value ?? "";
      const label = row.querySelector<HTMLInputElement>(".requirement-label")?.value ?? "";
      const target = row.querySelector<HTMLInputElement>(".requirement-target")?.value;
      const courseCode = row.querySelector<HTMLInputElement>(".requirement-course")?.value.trim().toUpperCase();
      const periodCode = row.querySelector<HTMLSelectElement>(".requirement-period")?.value;
      return { field, label, ...(target ? { target } : {}), ...(courseCode ? { courseCode } : {}), ...(periodCode ? { periodCode } : {}) };
    });
    const payload = {
      title: form.get("title"), kind: form.get("kind"), description: form.get("description"), benefits: form.get("benefits"), instructions: form.get("instructions"),
      opensAt: new Date(String(form.get("opensAt"))).toISOString(), closesAt: new Date(String(form.get("closesAt"))).toISOString(),
      capacity: Number(form.get("capacity")), careerIds: selectedCareers, requirements, publish: true,
    };
    try {
      const path = editing ? `/api/v1/opportunities/${editing.id}/versions/` : "/api/v1/opportunities/create/";
      await api(path, { method: "POST", body: JSON.stringify(payload) });
      setNotice(editing ? "Nueva versión publicada. Las postulaciones anteriores conservan sus requisitos." : "Oportunidad publicada y visible para estudiantes de las carreras seleccionadas.");
      setShowForm(false); setEditing(null); await load();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  if (!data && !error) return <div className="e07-loading"><LoaderCircle className="spin" /> Cargando oportunidades…</div>;
  const canManage = Boolean(data?.careers.length);
  const displayed = tab === "manage" ? data?.managed ?? [] : data?.opportunities ?? [];
  return <div className="page-stack e07-page">
    <section className="e07-hero"><div className="e07-hero-copy"><span className="e07-kicker"><Sparkles size={14} /> CRECIMIENTO ACADÉMICO</span><h1>Oportunidades que<br /><em>abren camino.</em></h1><p>Becas, proyectos y experiencias para llevar tu talento más lejos. Conoce las condiciones y verifica tu perfil con datos académicos validados.</p><div className="e07-hero-meta"><span><ShieldCheck size={15} /> Requisitos transparentes</span><span><BadgeCheck size={15} /> Decisiones con revisión humana</span></div></div><div className="e07-hero-art" aria-hidden="true"><div className="e07-art-orbit orbit-a" /><div className="e07-art-orbit orbit-b" /><div className="e07-art-core"><Award size={62} strokeWidth={1.35} /></div><span className="e07-art-tag tag-top">TU SIGUIENTE PASO</span><span className="e07-art-tag tag-bottom">TALENTO EN ACCIÓN</span></div></section>
    {error && <div className="e07-alert e07-alert-error" role="alert"><CircleAlert size={18} /><span>{error}</span><button aria-label="Cerrar" onClick={() => setError("")}><XCircle size={17} /></button></div>}
    {notice && <div className="e07-alert e07-alert-success" role="status"><CheckCircle2 size={18} /><span>{notice}</span><button aria-label="Cerrar" onClick={() => setNotice("")}><XCircle size={17} /></button></div>}
    <div className="e07-stats"><div><span className="e07-stat-icon"><BriefcaseBusiness size={18} /></span><strong>{String(openCount).padStart(2, "0")}</strong><span>Convocatorias abiertas</span></div><div><span className="e07-stat-icon stat-mint"><FileCheck2 size={18} /></span><strong>{String(data?.enrollments.length ? submitted : data?.opportunities.length ?? 0).padStart(2, "0")}</strong><span>{data?.enrollments.length ? "Mis postulaciones" : "Convocatorias de carrera"}</span></div><div className="e07-enrollment">{data?.enrollments.length ? <><label htmlFor="e07-enrollment">Mi matrícula activa</label><select id="e07-enrollment" value={enrollmentId} onChange={(event) => { setEnrollmentId(event.target.value); setEvaluation(null); setSelected(null); }}>{data.enrollments.map((row) => <option key={row.id} value={row.id}>{row.career} · {row.period} · {row.semester}.º semestre</option>)}</select>{enrollment && <small>{enrollment.careerName} · {enrollment.periodName}</small>}</> : <><strong>Vista docente</strong><small>Convocatorias publicadas para las carreras de tus grupos.</small></>}</div></div>
    {canManage && <div className="e07-toolbar"><div className="e07-tabs" role="tablist"><button role="tab" aria-selected={tab === "discover"} className={tab === "discover" ? "active" : ""} onClick={() => setTab("discover")}>Explorar</button><button role="tab" aria-selected={tab === "manage"} className={tab === "manage" ? "active" : ""} onClick={() => setTab("manage")}>Gestionar <span>{data?.managed.length}</span></button></div>{tab === "manage" && <button className="button button-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> Crear convocatoria</button>}</div>}
    <div className="e07-section-head"><div><span className="eyebrow">{tab === "manage" ? "ÁMBITO AUTORIZADO" : "DESCUBRE Y POSTULA"}</span><h2>{tab === "manage" ? "Convocatorias a tu cargo" : "Encuentra tu próxima oportunidad"}</h2><p>{tab === "manage" ? "Publica requisitos verificables y revisa cada postulación con trazabilidad." : "Cada requisito tiene un origen claro. Ser elegible permite postular, pero la adjudicación la realiza un responsable."}</p></div><button className="e07-refresh" onClick={() => void load()} aria-label="Actualizar oportunidades"><RefreshCw size={16} /></button></div>
    {showForm && <OpportunityForm careers={data?.careers ?? []} periods={data?.periods ?? []} editing={editing} busy={busy} onCancel={() => { setShowForm(false); setEditing(null); }} onSubmit={saveOpportunity} />}
    {displayed.length ? <div className="e07-grid">{displayed.map((opportunity) => <OpportunityCard key={opportunity.versionId} opportunity={opportunity} managed={tab === "manage"} application={data?.applications.find((app) => app.versionId === opportunity.versionId && app.status !== "withdrawn")} onInspect={() => void inspect(opportunity)} onVersion={() => { setEditing(opportunity); setShowForm(true); }} />)}</div> : <div className="e07-empty"><span><BriefcaseBusiness size={25} /></span><h3>{tab === "manage" ? "Aún no tienes convocatorias" : "No hay convocatorias disponibles"}</h3><p>{tab === "manage" ? "Crea una convocatoria para una o varias carreras de tu ámbito." : "Cuando se publiquen nuevas oportunidades para tu carrera, aparecerán aquí."}</p>{tab === "manage" && <button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={16} /> Crear convocatoria</button>}</div>}
    {selected && !showForm && tab === "discover" && <section className="e07-detail" aria-live="polite"><div className="e07-detail-head"><div><span className="eyebrow">EVALUACIÓN EXPLICABLE · VERSIÓN {selected.version}</span><h2>{selected.title}</h2><p>Convocatoria de {selected.kindLabel.toLowerCase()} · cierre {fmt(selected.closesAt)}</p></div><button className="e07-close" aria-label="Cerrar detalle" onClick={() => { setSelected(null); setEvaluation(null); }}><XCircle size={19} /></button></div><div className="e07-instructions"><strong>Cómo postular</strong><p>{selected.instructions || "Envía tu postulación desde UPEA Talent+ dentro del plazo publicado."}</p></div><div className="e07-requirement-list">{evaluation?.requirements.map((row) => <RequirementResult key={row.id} row={row} />) ?? <div className="e07-checking">{busy ? <><LoaderCircle className="spin" size={18} /> Consultando datos verificados…</> : data?.enrollments.length ? "Selecciona una matrícula para consultar los requisitos." : "Vista informativa: elegibilidad y postulación están disponibles para estudiantes con matrícula activa."}</div>}</div>{evaluation && <div className={`e07-outcome outcome-${evaluation.overall}`}><div><span className="eyebrow">RESULTADO DE ELEGIBILIDAD</span><strong>{evaluation.overall === "eligible" ? "Cumples los requisitos publicados" : evaluation.overall === "ineligible" ? "Hay requisitos que aún no cumples" : "Faltan datos verificados"}</strong><small>Evaluado {fmt(evaluation.computedAt)} · La selección final es una decisión humana.</small></div><div className="e07-apply-actions">{data?.applications.some((a) => a.versionId === selected.versionId && a.status !== "withdrawn") ? <span className="e07-already"><CheckCircle2 size={17} /> Postulación registrada</span> : <button className="button button-primary" disabled={busy || evaluation.overall !== "eligible" || selected.status !== "published" || new Date(selected.closesAt) < new Date()} onClick={() => void apply(selected)}>{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />} Postular ahora</button>}<small>La elegibilidad no garantiza adjudicación.</small></div></div>}</section>}
    {data?.applications.length ? <section className="e07-my-applications"><div className="e07-section-head"><div><span className="eyebrow">SEGUIMIENTO</span><h2>Mis postulaciones</h2><p>Consulta el estado y las condiciones congeladas al momento de enviar.</p></div></div><div className="e07-application-list">{data.applications.map((application) => <article className="e07-my-app" key={application.id}><div className="e07-my-app-icon"><FileCheck2 size={18} /></div><div className="e07-my-app-copy"><strong>{application.title}</strong><span>{application.career} · {application.period} · {fmt(application.submittedAt)}</span>{application.latestDecision && <small>Resolución: {application.latestDecision.reason}</small>}{application.newVersionId && <button className="e07-version-notice" onClick={() => { const next = data.opportunities.find((row) => row.versionId === application.newVersionId); if (next) void inspect(next); }}>Se publicó {application.newVersionTitle} con nuevas condiciones · revisar <ArrowRight size={13} /></button>}</div><span className={`e07-status status-${application.status}`}>{application.statusLabel}</span>{["submitted", "in_review"].includes(application.status) && <button className="e07-text-action" disabled={busy} onClick={() => { if (window.confirm("¿Retirar esta postulación? La acción quedará registrada.")) void withdraw(application.id); }}>Retirar</button>}</article>)}</div></section> : null}
    {tab === "manage" && data?.managed.map((opportunity) => <section className="e07-manage-panel" key={`review-${opportunity.versionId}`}><div className="e07-manage-heading"><div><span className="eyebrow">POSTULACIONES · VERSIÓN {opportunity.version}</span><h3>{opportunity.title}</h3><p>{opportunity.applications?.length ?? 0} recibidas · cupo {opportunity.capacity} · {opportunity.careers.map((c) => c.code).join(", ")}</p></div><span className={`e07-status status-${opportunity.status}`}>{opportunityStatusLabel(opportunity.status)}</span></div>{opportunity.status === "published" && <OpportunityLifecycle opportunityId={opportunity.id} busy={busy} onAction={async (action, reason) => { setBusy(true); setError(""); try { await api(`/api/v1/opportunities/${opportunity.id}/close/`, { method: "POST", body: JSON.stringify({ action, reason }) }); setNotice(action === "close" ? "Convocatoria cerrada. Las postulaciones recibidas pueden resolverse." : "Convocatoria cancelada con motivo registrado."); await load(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }} />}{opportunity.applications?.length ? <div className="e07-applicants">{opportunity.applications.map((app) => <ReviewApplication key={app.id} application={app} capacityReached={(opportunity.applications ?? []).filter((a) => a.status === "selected").length >= opportunity.capacity} busy={busy} onDecision={async (decision, reason) => { setBusy(true); setError(""); try { await api(`/api/v1/applications/${app.id}/decision/`, { method: "POST", body: JSON.stringify({ decision, reason }) }); setNotice("Resolución registrada con el estado anterior, responsable y motivo."); await load(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }} />)}</div> : <p className="e07-no-apps">Aún no se han recibido postulaciones.</p>}</section>)}
  </div>;
}

function OpportunityCard({ opportunity, managed, application, onInspect, onVersion }: { opportunity: Version; managed: boolean; application?: Application; onInspect: () => void; onVersion: () => void }) {
  const open = opportunity.status === "published" && Date.now() >= new Date(opportunity.opensAt).getTime() && Date.now() <= new Date(opportunity.closesAt).getTime();
  const availability = open ? "Abierta" : opportunity.status === "published" ? "Próximamente / cerrada" : opportunityStatusLabel(opportunity.status);
  return <article className="e07-card"><div className={`e07-card-ribbon ${open ? "ribbon-open" : ""}`}><span>{opportunity.kindLabel}</span><span className="e07-live"><i />{availability}</span></div><div className="e07-card-content"><div className="e07-card-meta"><span><UsersRound size={14} />{opportunity.careers.map((c) => c.code).join(" · ")}</span><span><Clock3 size={14} />{opportunity.capacity} cupos</span></div><h3>{opportunity.title}</h3><p>{opportunity.description}</p>{opportunity.benefits && <div className="e07-benefit"><Award size={16} /><span>{opportunity.benefits}</span></div>}<div className="e07-date-line"><CalendarDays size={15} /><span>Postulación hasta <strong>{fmt(opportunity.closesAt)}</strong></span></div><div className="e07-card-footer">{managed ? <button className="e07-card-link" disabled={opportunity.status === "draft"} onClick={onVersion}><RefreshCw size={15} /> Crear versión <ArrowRight size={15} /></button> : application ? <span className="e07-already"><CheckCircle2 size={16} /> {application.statusLabel}</span> : <button className="e07-card-link" onClick={onInspect}>Ver requisitos y elegibilidad <ArrowRight size={16} /></button>}</div></div></article>;
}

function RequirementResult({ row }: { row: EligibilityRow }) {
  const meets = row.status === "meets";
  const missing = row.status === "insufficient";
  return <article className={`e07-requirement requirement-${row.status}`}><span className="e07-req-icon">{meets ? <Check size={16} /> : missing ? <CircleAlert size={16} /> : <XCircle size={16} />}</span><div className="e07-req-main"><strong>{row.label}</strong><small>{row.source}</small></div><div className="e07-req-value"><span>{missing ? "Sin datos" : row.value ?? "—"}</span><small>{requirementStatusLabel(row.status)}</small></div></article>;
}

function OpportunityLifecycle({ opportunityId, busy, onAction }: { opportunityId: string; busy: boolean; onAction: (action: "close" | "cancel", reason: string) => void }) {
  const [action, setAction] = useState<"close" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  if (!action) return <div className="e07-lifecycle-actions"><button className="e07-close-action" disabled={busy} onClick={() => setAction("close")}>Cerrar convocatoria</button><button className="e07-cancel-action" disabled={busy} onClick={() => setAction("cancel")}>Cancelar convocatoria</button></div>;
  return <form className={`e07-lifecycle-confirm ${action === "cancel" ? "is-cancelling" : ""}`} onSubmit={(event) => { event.preventDefault(); onAction(action, reason.trim()); }}>
    <label htmlFor={`close-reason-${opportunityId}`}>{action === "close" ? "Motivo para cerrar admisiones" : "Motivo para cancelar la convocatoria"}<textarea id={`close-reason-${opportunityId}`} required minLength={5} maxLength={1000} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Describe brevemente la causa" /></label>
    <div><button type="button" className="button button-secondary" disabled={busy} onClick={() => { setAction(null); setReason(""); }}>Volver</button><button className="button button-primary" disabled={busy || reason.trim().length < 5}>{busy ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}{action === "close" ? "Confirmar cierre" : "Confirmar cancelación"}</button></div>
  </form>;
}

function OpportunityForm({ careers, periods, editing, busy, onCancel, onSubmit }: { careers: Array<{ id: string; code: string; name: string }>; periods: Array<{ id: string; code: string; name: string; career: string }>; editing: Version | null; busy: boolean; onCancel: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const base = editing;
  const [requirements, setRequirements] = useState<RequirementInput[]>(() => base?.requirements.map((item) => ({
    field: item.field, label: item.label, ...(item.target ? { target: item.target } : {}), ...(item.courseCode ? { courseCode: item.courseCode } : {}), ...(item.periodCode ? { periodCode: item.periodCode } : {}),
  })) ?? researchRequirements.map((item) => ({ ...item })));
  function updateRequirement(index: number, values: Partial<RequirementInput>) {
    setRequirements((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...values } : item));
  }
  function changeField(index: number, field: string) {
    updateRequirement(index, {
      field, label: requirementLabels[field],
      target: numericRequirements.has(field) ? field === "average" ? "70" : "1" : undefined,
      courseCode: field === "approved_course" ? "MET201" : undefined,
      periodCode: field === "period" ? periods[0]?.code ?? "" : undefined,
    });
  }
  return <form className="e07-form" onSubmit={onSubmit}>
    <div className="e07-form-title"><div><span className="eyebrow">PUBLICACIÓN VERSIONADA</span><h2>{base ? `Nueva versión de ${base.title}` : "Crear oportunidad"}</h2><p>Las condiciones publicadas quedan congeladas para todas las postulaciones anteriores.</p></div><span className="e07-form-step">01 <small>Convocatoria</small></span></div>
    <div className="e07-form-grid">
      <label>Título de la oportunidad<input name="title" required maxLength={160} defaultValue={base?.title ?? ""} placeholder="Ej. Beca de Investigación" /></label>
      <label>Tipo<select name="kind" defaultValue={base?.kind ?? "scholarship"}><option value="scholarship">Beca</option><option value="internship">Pasantía</option><option value="course">Curso</option><option value="contest">Concurso</option><option value="project">Proyecto</option><option value="exchange">Intercambio</option></select></label>
      <label className="span-two">Descripción<textarea name="description" required maxLength={4000} rows={3} defaultValue={base?.description ?? ""} placeholder="Propósito, perfil y alcance de la oportunidad" /></label>
      <label className="span-two">Beneficios<textarea name="benefits" maxLength={2000} rows={2} defaultValue={base?.benefits ?? ""} placeholder="Ej. Apoyo económico, mentoría y acceso a laboratorio" /></label>
      <label>Fecha y hora de apertura<input name="opensAt" type="datetime-local" required defaultValue={localInput(base?.opensAt, 1)} /></label>
      <label>Fecha y hora de cierre<input name="closesAt" type="datetime-local" required defaultValue={localInput(base?.closesAt, 8)} /></label>
      <label>Cupos disponibles<input name="capacity" type="number" min="1" max="10000" required defaultValue={base?.capacity ?? 3} /></label>
      <label className="span-two">Canal e instrucciones para postular<textarea name="instructions" maxLength={2000} rows={2} defaultValue={base?.instructions ?? "Postula desde UPEA Talent+ dentro del plazo publicado."} /></label>
    </div>
    <fieldset className="e07-careers"><legend>Carreras habilitadas</legend><div>{careers.map((career) => <label key={career.id}><input type="checkbox" name="careerIds" value={career.id} defaultChecked={base ? base.careers.some((c) => c.id === career.id) : true} /><span><strong>{career.code}</strong>{career.name}</span></label>)}</div><small>Se publican solo en carreras de tu ámbito autorizado.</small></fieldset>
    <fieldset className="e07-criteria-builder"><legend>Requisitos verificables</legend><p>Elige campos tipados. Solo promedio, puntos y semestre necesitan un umbral; el curso requiere su código académico.</p>
      <div className="e07-criteria-rows">{requirements.map((requirement, index) => <div className="e07-criterion-row" data-requirement-row key={`requirement-${index}`}>
        <label>Tipo de criterio<select className="requirement-field" value={requirement.field} onChange={(event) => changeField(index, event.target.value)}><option value="average">Promedio verificado</option><option value="own_points">Puntos SPD propios</option><option value="semester">Semestre mínimo</option><option value="period">Periodo académico</option><option value="validated_project">Proyecto validado</option><option value="validated_activity">Actividad verificada</option><option value="validated_skill">Habilidad validada</option><option value="approved_course">Curso aprobado</option></select></label>
        <label>Nombre visible<input className="requirement-label" required maxLength={180} value={requirement.label} onChange={(event) => updateRequirement(index, { label: event.target.value })} /></label>
        {numericRequirements.has(requirement.field) && <label>{requirement.field === "average" ? "Mínimo en escala 100" : requirement.field === "semester" ? "Semestre mínimo" : "Puntos mínimos"}<input className="requirement-target" required type="number" min={requirement.field === "semester" ? 1 : 0} max={requirement.field === "average" ? 100 : undefined} step={requirement.field === "average" ? "0.01" : "1"} value={requirement.target ?? ""} onChange={(event) => updateRequirement(index, { target: event.target.value })} /></label>}
        {requirement.field === "approved_course" && <label>Código de asignatura<input className="requirement-course" required maxLength={24} value={requirement.courseCode ?? ""} onChange={(event) => updateRequirement(index, { courseCode: event.target.value.toUpperCase() })} placeholder="MET201" /></label>}
        {requirement.field === "period" && <label>Periodo de convocatoria<select className="requirement-period" required value={requirement.periodCode ?? ""} onChange={(event) => updateRequirement(index, { periodCode: event.target.value })}><option value="">Selecciona un periodo</option>{periods.map((period) => <option key={period.id} value={period.code}>{period.code} · {period.career} · {period.name}</option>)}</select></label>}
        <button className="e07-remove-criterion" type="button" aria-label={`Quitar requisito ${index + 1}`} disabled={requirements.length === 1} onClick={() => setRequirements((current) => current.filter((_row, rowIndex) => rowIndex !== index))}><XCircle size={17} /></button>
      </div>)}</div>
      <button className="e07-add-criterion" type="button" onClick={() => setRequirements((current) => [...current, { field: "validated_skill", label: requirementLabels.validated_skill }])}><Plus size={15} /> Añadir requisito tipado</button>
    </fieldset>
    <div className="e07-example-note"><ShieldCheck size={18} /><p>Los datos se evalúan en el servidor desde notas verificadas, registros validados y el libro SPD. Los puntos transferidos no cuentan como mérito propio.</p></div>
    <div className="e07-form-actions"><button type="button" className="button button-secondary" onClick={onCancel}>Cancelar</button><button className="button button-primary" disabled={busy || !careers.length}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} Publicar convocatoria</button></div>
  </form>;
}

function ReviewApplication({ application, capacityReached, busy, onDecision }: { application: Application; capacityReached: boolean; busy: boolean; onDecision: (decision: string, reason: string) => void }) {
  const [reason, setReason] = useState("");
  const terminal = ["selected", "not_selected", "withdrawn"].includes(application.status);
  const eligible = application.currentEligibility.every((row) => row.status === "meets");
  return <article className="e07-review-row">
    <div className="e07-review-person"><span className="e07-review-avatar">{application.student.split(" ").slice(0, 2).map((part) => part[0]).join("")}</span><div><strong>{application.student}</strong><span>{application.studentNumber} · {application.career} · {application.period}</span><small>Postuló {fmt(application.submittedAt)}</small></div><span className={`e07-status status-${application.status}`}>{application.statusLabel}</span></div>
    <details className="e07-review-detail"><summary>Ver criterios y datos al resolver <ArrowRight size={14} /></summary>
      {application.eligibilityChanged && <p className="e07-changed"><CircleAlert size={15} /> Los datos verificados cambiaron desde la última resolución. Se conserva el historial de la decisión.</p>}
      <div className="e07-review-criteria">{application.currentEligibility.map((row) => <div key={row.id}><span>{row.status === "meets" ? <Check size={14} /> : row.status === "insufficient" ? <CircleAlert size={14} /> : <XCircle size={14} />}{row.label}</span><small>{row.source}</small></div>)}</div>
      <div className="e07-review-criteria e07-historical"><strong>Foto inicial de postulación</strong>{application.initialEligibility.map((row) => <div key={row.id}><span>{row.label}</span><small>{row.value ?? "Sin datos"} · {requirementStatusLabel(row.status)}</small></div>)}</div>
    </details>
    {application.latestDecision && <div className="e07-decision-history"><ShieldCheck size={15} /> Estado anterior: {applicationStatusLabel(application.latestDecision.previousStatus)} · {application.latestDecision.actor}: “{application.latestDecision.reason}”</div>}
    {terminal && application.status !== "withdrawn" && application.eligibilityChanged && <div className="e07-reopen-review"><label htmlFor={`reopen-${application.id}`}>Motivo para reabrir la revisión<textarea id={`reopen-${application.id}`} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} placeholder="Explica el cambio de datos que requiere revisar la resolución" /></label><button className="button button-secondary" disabled={busy || reason.trim().length < 5} onClick={() => onDecision("in_review", reason)}>Reabrir revisión</button></div>}
    {!terminal && <div className="e07-decision-form"><label htmlFor={`reason-${application.id}`}>Motivo de decisión<input id={`reason-${application.id}`} value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} placeholder="Explica la resolución institucional" /></label><div><button className="button button-secondary" disabled={busy || reason.trim().length < 5} onClick={() => onDecision("in_review", reason)}>Mantener en revisión</button><button className="button button-secondary" disabled={busy || reason.trim().length < 5} onClick={() => onDecision("not_selected", reason)}>No seleccionar</button><button className="button button-primary" disabled={busy || reason.trim().length < 5 || !eligible || capacityReached} title={!eligible ? "Los requisitos deben estar cumplidos con datos verificados" : capacityReached ? "Cupo alcanzado" : undefined} onClick={() => onDecision("selected", reason)}><Check size={15} /> Seleccionar</button></div></div>}
  </article>;
}
