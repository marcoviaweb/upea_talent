import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ArrowUpRight, BadgeCheck, BookOpen, Check, Clock3, FileCheck2, FileText, LoaderCircle, Plus, ShieldCheck, Sparkles, UploadCloud, WalletCards, X } from "lucide-react";
import { api, dateLabel, errorMessage, type Enrollment } from "../../api";
import "./e06.css";
import "./transfers.css";
import TransferPanel from "./TransferPanel";

type Category = { id: string; code: string; name: string; criterion: string; points: number; transferable: boolean };
type Regulation = { id: string; career: string; careerCode: string; version: number; title: string; effectiveFrom: string; effectiveTo: string | null; categories: Category[] };
type Review = { outcome: string; note: string; reviewer: string; createdAt: string };
type Activity = { id: string; title: string; description: string; occurredOn: string; source: string; status: string; statusLabel: string; category: Category; student: string; career: string; period: string; createdAt: string; reviewedAt: string | null; reviewedBy: string | null; isOwner: boolean; canReview: boolean; canRevoke: boolean; files: Array<{ id: string; name: string; size: number; url: string; version: number }>; reviews: Review[] };
type Points = { enrollment: string; career: string; careerCode?: string; period: string; points: number; level: string; student?: string; studentNumber?: string; movements: Array<{ id: string; points: number; reason: string; category: string; regulationVersion: number; date: string }> };
type AdminCandidate = { id: string; student: string; studentNumber: string; career: string; careerCode: string; period: string };
type Data = { regulations: Regulation[]; totals: Points[]; groupView?: boolean; levelThresholds: Array<{ name: string; from: number; to: number | null }> };

const labels: Record<string, string> = {
  in_review: "En revisión", observed: "Necesita ajustes", approved: "Aprobada", rejected: "No aprobada", revoked: "Revocada",
  approve: "Aprobada", observe: "Observada", reject: "Rechazada", revoke: "Revocada",
};
const needsReviewCount = (rows: Activity[]) => rows.filter((activity) => activity.canReview && ["in_review", "observed"].includes(activity.status)).length;

const levelInsignias: Record<string, { image: string; description: string }> = {
  Explorador: { image: new URL("./assets/insignias/explorador.png", import.meta.url).href, description: "Iniciaste tu recorrido de desarrollo." },
  Participante: { image: new URL("./assets/insignias/participante.png", import.meta.url).href, description: "Participas activamente en tu desarrollo." },
  Desarrollador: { image: new URL("./assets/insignias/desarrollador.png", import.meta.url).href, description: "Construyes experiencias y capacidades." },
  Líder: { image: new URL("./assets/insignias/lider.png", import.meta.url).href, description: "Tu trayectoria refleja liderazgo." },
  "Talento destacado": { image: new URL("./assets/insignias/destacado.png", import.meta.url).href, description: "Alcanzaste el nivel más alto de la escala." },
};

function LevelInsignia({ name, compact = false }: { name: string; compact?: boolean }) {
  const insignia = levelInsignias[name] ?? { image: levelInsignias.Explorador.image, description: `Nivel ${name}.` };
  return <span className={`e06-insignia${compact ? " is-compact" : ""}`} title={insignia.description}>
    <img className="e06-insignia-image" src={insignia.image} alt="" />
    <span className="e06-insignia-name">{name}</span>
  </span>;
}

export default function E06Page({ enrollments, canRegisterVerifiedActivity = false }: { enrollments: Enrollment[]; canRegisterVerifiedActivity?: boolean }) {
  const location = useLocation();
  const [data, setData] = useState<Data | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showVerifiedForm, setShowVerifiedForm] = useState(false);
  const [candidates, setCandidates] = useState<AdminCandidate[]>([]);
  const [busyId, setBusyId] = useState("");
  const announce = `${activities.length} evidencias registradas. ${needsReviewCount(activities)} pendientes para revisión.`;
  const reload = async () => {
    setLoading(true); setError("");
    try { const [spd, evidence, candidateData] = await Promise.all([api<Data>("/api/v1/spd/"), api<{ activities: Activity[] }>("/api/v1/evidence/"), canRegisterVerifiedActivity ? api<{ enrollments: AdminCandidate[] }>("/api/v1/evidence/candidates/") : Promise.resolve({ enrollments: [] })]); setData(spd); setActivities(evidence.activities); setCandidates(candidateData.enrollments); }
    catch (err) { setError(errorMessage(err)); } finally { setLoading(false); }
  };
  useEffect(() => { void reload(); }, []);
  const needsReview = activities.filter((activity) => activity.canReview && ["in_review", "observed"].includes(activity.status));
  return <div className="page-stack">
    <section className="welcome-hero e06-page-hero">
      <div className="welcome-copy"><span className="eyebrow hero-eyebrow"><Sparkles size={14} /> DESARROLLO Y RECONOCIMIENTO</span><h1>Evidencias y <span className="wave">SPD.</span></h1><p>Presenta tus logros y consulta cómo cada validación construye tu trayectoria profesional.</p><div className="hero-note"><span className="hero-note-icon"><ShieldCheck size={15} /></span><span><strong>Validación transparente.</strong> Cada mérito sigue criterios y deja un historial verificable.</span></div></div>
      <div className="hero-art" aria-hidden="true"><div className="hero-art-ring ring-a" /><div className="hero-art-ring ring-b" /><div className="hero-art-ring ring-c" /><div className="hero-art-core"><FileCheck2 size={31} strokeWidth={1.6} /></div><span className="art-star star-a">✳</span><span className="art-star star-b">✦</span><span className="art-orbit-label label-a">EVIDENCIA</span><span className="art-orbit-label label-b">VALIDACIÓN</span><span className="art-orbit-label label-c">MÉRITO</span></div>
    </section>
    {error && <div className="error-banner" role="alert">{error} <button className="text-button" onClick={() => void reload()}>Reintentar</button></div>}
    <nav className="e06-tabs" aria-label="Sección de evidencias y puntos"><NavLink end to="/trayectoria/evidencias/" className={({ isActive }) => `e06-tab ${isActive ? "active" : ""}`}><FileCheck2 size={17} /> Evidencias <span>{activities.length}</span></NavLink><NavLink to="/trayectoria/puntos/" className={({ isActive }) => `e06-tab ${isActive ? "active" : ""}`}><WalletCards size={17} /> {data?.groupView ? "SPD de mis grupos" : "Mi SPD"}</NavLink><NavLink to="/trayectoria/transferencias/" className={({ isActive }) => `e06-tab ${isActive ? "active" : ""}`}><ArrowUpRight size={16} /> Transferencias</NavLink></nav><span className="sr-only" aria-live="polite">{announce}</span>
    {location.pathname === "/trayectoria/transferencias/" ? <TransferPanel /> : loading ? <div className="loading-state"><LoaderCircle size={20} className="spin" /> Cargando evidencias y reglamento…</div> : location.pathname === "/trayectoria/evidencias/" ? <>
      <div className="e06-summary-grid"><article className="e06-summary-card e06-summary-main"><div className="e06-summary-icon"><ShieldCheck size={19} /></div><div><strong>Validación transparente</strong><p>Cada actividad muestra su criterio, responsable y el resultado de revisión.</p></div>{enrollments.some((item) => item.status === "active") && <button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={17} /> Presentar evidencia</button>}{canRegisterVerifiedActivity && <button className="button button-secondary" onClick={() => setShowVerifiedForm(true)}><BadgeCheck size={17} /> Registrar mérito verificado</button>}</article><article className="e06-summary-card"><div className="e06-summary-icon amber"><Clock3 size={19} /></div><div><span className="e06-metric">{needsReview.length}</span><span className="muted"> pendientes para revisar</span><p>Solo aparecen casos de grupos asignados a tu cuenta.</p></div></article></div>
      <section className="e06-section"><div className="section-title-row"><div><span className="eyebrow">REGISTRO Y VALIDACIÓN</span><h2>Actividad reciente</h2></div><span className="e06-count">{activities.length} registros</span></div>
        {!activities.length ? <div className="e06-empty"><div className="e06-empty-icon"><FileCheck2 size={22} /></div><h3>Aún no hay evidencias</h3><p>Registra un curso, proyecto, concurso u otra actividad reconocida por el reglamento.</p><button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={17} /> Presentar la primera</button></div> : <div className="e06-activity-list">{activities.map((activity) => <article className="e06-activity-card" key={activity.id}><div className="e06-activity-icon"><FileCheck2 size={18} /></div><div className="e06-activity-body"><div className="e06-activity-top"><div><span className="e06-category-label">{activity.category.name} · {activity.career}</span><h3>{activity.title}</h3></div><span className={`e06-status status-${activity.status}`}>{labels[activity.status] || activity.statusLabel}</span></div><p>{activity.description}</p>{activity.canReview && <p className="e06-criterion-line"><strong>Criterio:</strong> {activity.category.criterion}</p>}<div className="e06-meta"><span>{activity.student}</span><span>{dateLabel(activity.occurredOn)}</span>{activity.source && <span>Fuente: {activity.source}</span>}<span className="e06-point-value">+{activity.category.points} pts si se aprueba</span></div>
          <details className="e06-details"><summary>Ver criterio, archivo e historial</summary><p><strong>Criterio:</strong> {activity.category.criterion}</p>{activity.files.map((file) => <a className="e06-file-link" href={file.url} key={file.id} target="_blank" rel="noreferrer"><FileText size={15} /> {file.name} · versión {file.version} <ArrowUpRight size={14} /></a>)}{activity.reviews.map((review, index) => <div className="e06-review-note" key={`${activity.id}-${index}`}><strong>{labels[review.outcome] || review.outcome} · {review.reviewer}</strong><span>{review.note || "Criterio satisfecho."}</span></div>)}</details>
          {activity.canReview && ["in_review", "observed"].includes(activity.status) && <ReviewActions title={activity.title} busy={busyId === activity.id} onAct={async (outcome, note) => { setBusyId(activity.id); try { await api(`/api/v1/evidence/${activity.id}/review/`, { method: "POST", body: JSON.stringify({ outcome, note }) }); await reload(); } catch (err) { setError(errorMessage(err)); } finally { setBusyId(""); } }} />}
          {activity.isOwner && activity.status === "observed" && <ResubmitEvidence activity={activity} onDone={() => void reload()} />}
          {activity.canRevoke && <RevokeAction activity={activity} onDone={() => void reload()} />}
        </div></article>)}</div>}
      </section>
      {showForm && <EvidenceForm enrollments={enrollments.filter((row) => row.status === "active")} regulations={data?.regulations ?? []} onClose={() => setShowForm(false)} onCreated={() => { setShowForm(false); void reload(); }} />}
      {showVerifiedForm && <VerifiedEvidenceForm candidates={candidates} regulations={data?.regulations ?? []} onClose={() => setShowVerifiedForm(false)} onCreated={() => { setShowVerifiedForm(false); void reload(); }} />}
    </> : <PointsPanel data={data} />}
  </div>;
}

function ReviewActions({ title, busy, onAct }: { title: string; busy: boolean; onAct: (outcome: string, note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  return <div className="e06-review-actions"><input name="reviewNote" aria-label={`Nota de revisión para ${title}`} placeholder="Motivo u observación para observar o rechazar…" value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} /><button aria-label={`Aprobar ${title}`} className="button button-primary button-small" disabled={busy} onClick={() => void onAct("approve", note)}>{busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Aprobar</button><button aria-label={`Observar ${title}`} className="button button-secondary button-small" disabled={busy || !note.trim()} onClick={() => void onAct("observe", note)}><FileText size={15} /> Observar</button><button aria-label={`Rechazar ${title}`} className="button button-quiet button-small" disabled={busy || !note.trim()} onClick={() => void onAct("reject", note)}><X size={15} /> Rechazar</button></div>;
}

function ResubmitEvidence({ activity, onDone }: { activity: Activity; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit() { if (!file) return; const form = new FormData(); form.append("file", file); setBusy(true); setError(""); try { await api(`/api/v1/evidence/${activity.id}/resubmit/`, { method: "POST", body: form }); onDone(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }
  return <div className="e06-resubmit"><label>Adjunta una nueva versión tras la observación<input name="file" type="file" accept="application/pdf,image/jpeg,image/png" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><button className="button button-primary button-small" disabled={!file || busy} onClick={() => void submit()}>{busy ? <LoaderCircle size={15} className="spin" /> : <UploadCloud size={15} />} Reenviar evidencia</button>{error && <span role="alert">{error}</span>}</div>;
}

function RevokeAction({ activity, onDone }: { activity: Activity; onDone: () => void }) {
  const [reason, setReason] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit() { if (!window.confirm(`¿Revocar la aprobación de “${activity.title}”? Se registrará una contrapartida en el libro SPD.`)) return; setBusy(true); setError(""); try { await api(`/api/v1/evidence/${activity.id}/revoke/`, { method: "POST", body: JSON.stringify({ reason }) }); onDone(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }
  return <div className="e06-resubmit e06-revoke"><label>Motivo administrativo para revocar esta aprobación<input name="revokeReason" value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} /></label><button className="button button-quiet button-small" disabled={!reason.trim() || busy} onClick={() => void submit()}>{busy && <LoaderCircle size={15} className="spin" />} Revocar aprobación</button>{error && <span role="alert">{error}</span>}</div>;
}

function VerifiedEvidenceForm({ candidates, regulations, onClose, onCreated }: { candidates: AdminCandidate[]; regulations: Regulation[]; onClose: () => void; onCreated: () => void }) {
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const [enrollmentId, setEnrollmentId] = useState(candidates[0]?.id ?? "");
  const selected = candidates.find((candidate) => candidate.id === enrollmentId);
  const regulation = regulations.find((item) => item.careerCode === selected?.careerCode);
  const [categoryId, setCategoryId] = useState(regulation?.categories[0]?.id ?? "");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { setCategoryId(regulation?.categories[0]?.id ?? ""); }, [regulation?.id]);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>(".e06-verified-modal");
    dialog?.querySelector<HTMLElement>("select, input, textarea, button")?.focus();
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") closeRef.current(); }
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previouslyFocused?.focus(); };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try { await api("/api/v1/evidence/verified/", { method: "POST", body: JSON.stringify({ enrollment: enrollmentId, category: categoryId, title: form.get("title"), description: form.get("description"), occurredOn: form.get("occurredOn"), source: form.get("source") }) }); onCreated(); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  return <div className="e06-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="e06-modal e06-verified-modal" role="dialog" aria-modal="true" aria-labelledby="e06-verified-title"><div className="e06-modal-head"><div><span className="eyebrow">REGISTRO ADMINISTRATIVO</span><h2 id="e06-verified-title">Registrar mérito verificado</h2><p>Deja constancia de la fuente y del responsable de validación.</p></div><button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={19} /></button></div><form className="e06-form" onSubmit={submit} autoComplete="off">
    <label>Estudiante y matrícula<select name="enrollment" value={enrollmentId} onChange={(event) => setEnrollmentId(event.target.value)} required>{candidates.map((item) => <option key={item.id} value={item.id}>{item.student} · {item.studentNumber} · {item.career} · {item.period}</option>)}</select></label>
    <label>Categoría SPD<select name="category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)} required>{regulation?.categories.map((item) => <option key={item.id} value={item.id}>{item.name} · +{item.points} pts</option>)}</select></label>
    <label>Nombre de la actividad<input name="title" required maxLength={160} placeholder="Ej. Participación en feria científica…" /></label>
    <label>Descripción verificada<textarea name="description" required maxLength={3000} rows={3} placeholder="Describe el mérito y la participación reconocida…" /></label>
    <div className="e06-form-row"><label>Fecha de realización<input name="occurredOn" type="date" required max={new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "America/La_Paz" }).format(new Date())} /></label><label>Fuente documental<input name="source" required maxLength={200} placeholder="Acta, certificado o referencia…" /></label></div>
    {error && <div className="error-banner" role="alert">{error}</div>}<div className="e06-form-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button className="button button-primary" disabled={busy || !categoryId}>{busy ? <LoaderCircle size={16} className="spin" /> : <BadgeCheck size={16} />} Registrar y otorgar puntos</button></div>
  </form></section></div>;
}

function EvidenceForm({ enrollments, regulations, onClose, onCreated }: { enrollments: Enrollment[]; regulations: Regulation[]; onClose: () => void; onCreated: () => void }) {
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const [enrollmentId, setEnrollmentId] = useState(enrollments[0]?.id || "");
  const selected = enrollments.find((row) => row.id === enrollmentId);
  const regulation = regulations.find((row) => row.careerCode === selected?.career.code);
  const [category, setCategory] = useState(regulation?.categories[0]?.id || "");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { setCategory(regulation?.categories[0]?.id || ""); }, [regulation?.id]);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>(".e06-modal");
    const firstControl = dialog?.querySelector<HTMLElement>("input, select, textarea, button");
    firstControl?.focus();
    function keepFocusInside(event: KeyboardEvent) {
      if (event.key === "Escape") { closeRef.current(); return; }
      if (event.key !== "Tab" || !dialog) return;
      const controls = [...dialog.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])")];
      if (!controls.length) return;
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls[controls.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) { event.preventDefault(); controls[0].focus(); }
    }
    document.addEventListener("keydown", keepFocusInside);
    return () => { document.removeEventListener("keydown", keepFocusInside); previouslyFocused?.focus(); };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try { await api("/api/v1/evidence/", { method: "POST", body: form }); onCreated(); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  const chosenCategory = regulation?.categories.find((item) => item.id === category);
  return <div className="e06-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="e06-modal" role="dialog" aria-modal="true" aria-labelledby="e06-form-title"><div className="e06-modal-head"><div><span className="eyebrow">NUEVO REGISTRO</span><h2 id="e06-form-title">Presentar evidencia</h2><p>Adjunta un documento verificable para tu matrícula.</p></div><button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={19} /></button></div><form onSubmit={submit} className="e06-form" autoComplete="off">
    <label>Matrícula<select name="enrollment" value={enrollmentId} onChange={(event) => setEnrollmentId(event.target.value)} required>{enrollments.map((item) => <option value={item.id} key={item.id}>{item.career.name} · {item.period.name}</option>)}</select></label>
    <label>Categoría SPD<select name="category" value={category} onChange={(event) => setCategory(event.target.value)} required>{regulation?.categories.map((item) => <option key={item.id} value={item.id}>{item.name} · +{item.points} pts</option>)}</select></label>
    {chosenCategory && <div className="e06-criterion"><strong>Criterio de validación</strong><span>{chosenCategory.criterion}</span><small>Reglamento {regulation?.version} · {regulation?.title}</small></div>}
    <label>Nombre de la actividad<input name="title" required maxLength={160} placeholder="Ej. Certificación de fundamentos de Python…" /></label>
    <label>Descripción y aporte<textarea name="description" required maxLength={3000} rows={3} placeholder="Describe qué realizaste y cuál fue tu participación…" /></label>
    <div className="e06-form-row"><label>Fecha de realización<input name="occurredOn" type="date" required max={new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "America/La_Paz" }).format(new Date())} /></label><label>Fuente / entidad<input name="source" maxLength={200} placeholder="Organizador o institución…" /></label></div>
    <label className="e06-upload"><UploadCloud size={20} /><span><strong>Adjunta la evidencia</strong><small>PDF, JPG o PNG · máximo 10 MB</small></span><input name="file" type="file" accept="application/pdf,image/jpeg,image/png" required /></label>
    {error && <div className="error-banner" role="alert">{error}</div>}<div className="e06-form-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button className="button button-primary" disabled={busy || !category}>{busy ? <><LoaderCircle size={16} className="spin" /> Enviando…</> : <><FileCheck2 size={16} /> Enviar a revisión</>}</button></div>
  </form></section></div>;
}

function PointsPanel({ data }: { data: Data | null }) {
  const [career, setCareer] = useState("");
  const regulations = data?.regulations ?? [];
  const visibleRegulations = useMemo(() => regulations.filter((row) => !career || row.careerCode === career), [regulations, career]);
  const totals = (data?.totals ?? []).filter((row) => !career || regulations.find((reg) => reg.career === row.career)?.careerCode === career);
  const groupView = Boolean(data?.groupView);
  return <div className="e06-points-layout"><section className="e06-section"><div className="section-title-row"><div><span className="eyebrow">SALDO RECONSTRUIDO</span><h2>{groupView ? "Trayectoria SPD de mis grupos" : "Mi trayectoria SPD"}</h2>{groupView && <p className="muted">Consulta de solo lectura para estudiantes de tus grupos asignados.</p>}</div><select className="e06-filter" aria-label="Filtrar por carrera" value={career} onChange={(event) => setCareer(event.target.value)}><option value="">{groupView ? "Todas las carreras asignadas" : "Todas mis carreras"}</option>{regulations.map((row) => <option key={row.id} value={row.careerCode}>{row.career}</option>)}</select></div>
    {!totals.length ? <div className="e06-empty"><div className="e06-empty-icon"><WalletCards size={22} /></div><h3>{groupView ? "Tus grupos todavía no registran movimientos SPD" : "Sin movimientos todavía"}</h3><p>{groupView ? "Los movimientos de estudiantes aparecerán aquí cuando una evidencia sea aprobada conforme al reglamento vigente." : "Los puntos aparecerán cuando una evidencia sea aprobada conforme al reglamento vigente."}</p></div> : <div className="e06-points-cards">{totals.map((item) => <article className="e06-balance-card" key={item.enrollment}><div className="e06-balance-top"><div className="e06-balance-icon"><WalletCards size={19} /></div><LevelInsignia name={item.level} /></div>{groupView && <div className="e06-student-ledger"><strong>{item.student}</strong><span>Matrícula {item.studentNumber}</span></div>}<span className="e06-balance-number">{item.points}<small> pts</small></span><strong>{item.career}</strong><span className="muted">{item.period}</span><div className="e06-level-track" aria-label={`Nivel ${item.level}`}><div style={{ width: `${Math.min(100, item.points % 100)}%` }} /></div><small className="muted">{groupView ? "Mérito propio del estudiante · transferencias por separado" : "Mérito propio · transferencias se mostrarán por separado"}</small><div className="e06-movements">{item.movements.length ? item.movements.map((movement) => <div className="e06-movement" key={movement.id}><div><strong>{movement.category}</strong><span>{movement.reason} · Reg. v{movement.regulationVersion}</span><small>{dateLabel(movement.date)}</small></div><b className={movement.points < 0 ? "negative" : ""}>{movement.points > 0 ? "+" : ""}{movement.points}</b></div>) : <p>Aún no hay movimientos en esta matrícula.</p>}</div></article>)}</div>}
    <section className="e06-insignia-showcase" aria-labelledby="e06-levels-title"><div className="e06-levels-heading"><div><span className="eyebrow">RECONOCIMIENTO DE TRAYECTORIA</span><h3 id="e06-levels-title">Insignias por nivel</h3></div><p>Cada insignia se obtiene según los puntos de mérito propio.</p></div><div className="e06-levels-grid">{data?.levelThresholds.map((item) => <div className="e06-level-item" key={item.name}><LevelInsignia name={item.name} compact /><strong>{item.from}{item.to === null ? "+" : `–${item.to}`} puntos</strong></div>)}</div></section>
  </section><aside className="e06-regulations"><div className="section-title-row"><div><span className="eyebrow">REGLAS PÚBLICAS</span><h2>Reglamento SPD</h2></div><BookOpen size={19} /></div>{visibleRegulations.map((regulation) => <article className="e06-reg-card" key={regulation.id}><div className="e06-reg-title"><strong>{regulation.career}</strong><span>v{regulation.version}</span></div><p>{regulation.title}</p><small>Vigente desde {dateLabel(regulation.effectiveFrom)}</small><div className="e06-reg-categories">{regulation.categories.map((category) => <div key={category.id}><span>{category.name}<small>{category.criterion}</small></span><b>+{category.points}</b></div>)}</div></article>)}</aside></div>;
}
