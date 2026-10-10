import { useEffect, useState, type FormEvent } from "react";
import { BadgeCheck, BarChart3, CalendarClock, Check, ClipboardCheck, LoaderCircle, LockKeyhole, MessageSquareText, Plus, Send, ShieldCheck, UsersRound } from "lucide-react";
import { api, dateLabel, errorMessage } from "../../api";
import "./e09.css";

type Offering = { id: string; career: string; careerCode: string; period: string; periodCode: string; course: string; courseCode: string; group: string };
type Metric = { mean: number; distribution: Record<string, number> };
type TargetResult = { id: string; subject: string; role: string; result: null | { state: "published" | "suppressed"; responseCount?: number; metrics?: Record<string, Metric> } };
type Campaign = { id: string; title: string; version: number; status: string; statusLabel: string; career: string; careerCode: string; period: string; course: string; courseCode: string; group: string; opensAt: string; closesAt: string; minimumResponses: number; canPublish: boolean; canClose: boolean; canPublishResults: boolean; canCancel: boolean; targets: TargetResult[] };
type Survey = { campaignId: string; targetId: string; title: string; version: number; status: string; course: string; courseCode: string; group: string; period: string; subject: string; role: string; opensAt: string; closesAt: string; answered: boolean; canRespond: boolean };
type SubjectResult = { campaign: string; version: number; career: string; period: string; course: string; courseCode: string; group: string; responseCount: number; metrics: Record<string, Metric>; publishedAt: string };
type Data = { questionnaire: Array<{ code: string; label: string }>; scale: Array<{ value: number; label: string }>; minimumPrivacyThreshold: number; mySurveys: Survey[]; subjectResults: SubjectResult[]; campaigns: Campaign[]; offerings: Offering[]; canManage: boolean };

const localInput = (date: Date) => {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
};
const statusLabel: Record<string, string> = { draft: "Borrador", open: "Abierta", closed: "Cerrada", published: "Resultados publicados", cancelled: "Cancelada" };

export default function E09Page() {
  const [data, setData] = useState<Data | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [answering, setAnswering] = useState<Survey | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [cancelReason, setCancelReason] = useState<Record<string, string>>({});

  async function load() {
    setError("");
    try { setData(await api<Data>("/api/v1/evaluations/")); }
    catch (err) { setError(errorMessage(err)); }
  }
  useEffect(() => { void load(); }, []);

  async function act(url: string, success: string, body: Record<string, unknown> = {}): Promise<boolean> {
    setBusy(true); setError(""); setNotice("");
    try { await api(url, { method: "POST", body: JSON.stringify(body) }); setNotice(success); setAnswering(null); setAnswers({}); await load(); return true; }
    catch (err) { setError(errorMessage(err)); return false; }
    finally { setBusy(false); }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const saved = await act("/api/v1/evaluations/", "Campaña guardada como borrador y lista para revisar.", {
      offeringId: form.get("offeringId"), title: form.get("title"),
      opensAt: new Date(String(form.get("opensAt"))).toISOString(),
      closesAt: new Date(String(form.get("closesAt"))).toISOString(),
      minimumResponses: Number(form.get("minimumResponses")),
    });
    if (saved) setShowCreate(false);
  }

  function submitBallot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answering || !data || data.questionnaire.some((question) => !answers[question.code])) return;
    void act("/api/v1/evaluations/respond/", "Tu respuesta se registró de forma anónima. No podrás modificarla.", { targetId: answering.targetId, answers });
  }

  const openSurveys = data?.mySurveys.filter((survey) => survey.canRespond) ?? [];
  const completedSurveys = data?.mySurveys.filter((survey) => survey.answered || survey.status !== "open") ?? [];
  if (!data && !error) return <div className="e09-loading" role="status"><LoaderCircle className="spin" size={20} /> Cargando evaluaciones…</div>;

  return <div className="page-stack e09-page">
    <section className="welcome-hero e09-hero">
      <div className="welcome-copy"><span className="eyebrow hero-eyebrow"><MessageSquareText size={14} /> MEJORA ACADÉMICA</span><h1>Evaluación <span className="wave">académica.</span></h1><p>Comparte una experiencia concreta de aprendizaje mediante criterios respetuosos y respuestas estructuradas.</p><div className="hero-note"><span className="hero-note-icon"><LockKeyhole size={15} /></span><span><strong>Tu respuesta es anónima.</strong> Solo se publican resultados agregados al alcanzar el mínimo de privacidad.</span></div></div>
      <div className="hero-art" aria-hidden="true"><div className="hero-art-ring ring-a" /><div className="hero-art-ring ring-b" /><div className="hero-art-ring ring-c" /><div className="hero-art-core"><BarChart3 size={31} strokeWidth={1.6} /></div><span className="art-star star-a">✳</span><span className="art-star star-b">✦</span><span className="art-orbit-label label-a">ESCUCHA</span><span className="art-orbit-label label-b">APRENDE</span><span className="art-orbit-label label-c">MEJORA</span></div>
    </section>
    {error && <div className="error-banner" role="alert">{error}<button className="text-button" onClick={() => void load()}>Reintentar</button></div>}
    {notice && <div className="e09-notice" role="status"><Check size={17} />{notice}</div>}

    <section className="e09-privacy-strip"><div><ShieldCheck size={20} /><span><strong>Respuestas protegidas</strong><small>La habilitación se almacena separada del contenido de tu evaluación.</small></span></div><div><UsersRound size={20} /><span><strong>Mínimo {data?.minimumPrivacyThreshold ?? 5} respuestas</strong><small>Las muestras menores no muestran puntuaciones ni conteos exactos.</small></span></div><div><ClipboardCheck size={20} /><span><strong>Sin texto libre</strong><small>No se publican comentarios individuales ni inferencias disciplinarias.</small></span></div></section>

    {openSurveys.length > 0 && <section className="e09-section"><div className="e09-section-head"><div><span className="eyebrow">TU PARTICIPACIÓN</span><h2>Encuestas disponibles</h2><p>Evalúa únicamente grupos en los que tienes matrícula activa.</p></div><span className="e09-count">{openSurveys.length} disponibles</span></div><div className="e09-survey-grid">{openSurveys.map((survey) => <article className="e09-survey-card" key={survey.targetId}><div className="e09-card-top"><span className="e09-icon"><MessageSquareText size={18} /></span><span className="e09-state state-open">Abierta</span></div><span className="e09-kicker">{survey.courseCode} · {survey.period}</span><h3>{survey.subject}</h3><p>{survey.role} · {survey.course} · Grupo {survey.group}</p><small><CalendarClock size={14} /> Cierra {dateLabel(survey.closesAt)}</small><button className="button button-primary" onClick={() => { setAnswering(survey); setAnswers({}); }}><ClipboardCheck size={16} /> Responder encuesta</button></article>)}</div></section>}

    {answering && <div className="e09-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAnswering(null); }}><section className="e09-ballot-modal" role="dialog" aria-modal="true" aria-labelledby="e09-ballot-title"><button className="e09-modal-close" onClick={() => setAnswering(null)} aria-label="Cerrar encuesta">×</button><span className="eyebrow">RESPUESTA ESTRUCTURADA · ANÓNIMA</span><h2 id="e09-ballot-title">{answering.subject}</h2><p>{answering.courseCode} · Grupo {answering.group} · {answering.period}</p><form onSubmit={submitBallot}><div className="e09-question-list">{data?.questionnaire.map((question, index) => <fieldset className="e09-question" key={question.code}><legend><span>{String(index + 1).padStart(2, "0")}</span>{question.label}</legend><div className="e09-scale" role="radiogroup" aria-label={question.label}>{data.scale.map((option) => <label className={`e09-scale-option ${answers[question.code] === option.value ? "selected" : ""}`} key={option.value}><input type="radio" name={question.code} value={option.value} checked={answers[question.code] === option.value} onChange={() => setAnswers((current) => ({ ...current, [question.code]: option.value }))} required /><span>{option.value}</span><small>{option.label}</small></label>)}</div></fieldset>)}</div><div className="e09-ballot-foot"><span><LockKeyhole size={15} /> No se guarda tu identidad junto a las respuestas.</span><button className="button button-primary" disabled={busy || data?.questionnaire.some((question) => !answers[question.code])}><Send size={16} />{busy ? "Enviando…" : "Enviar respuesta"}</button></div></form></section></div>}

    {completedSurveys.length > 0 && <section className="e09-section"><div className="e09-section-head"><div><span className="eyebrow">HISTORIAL PRIVADO</span><h2>Tu participación</h2><p>Solo tú ves cuáles encuestas completaste; esta información no se entrega al personal evaluado.</p></div></div><div className="e09-participation-list">{completedSurveys.map((survey) => <article key={survey.targetId}><span className={`e09-state ${survey.answered ? "state-done" : "state-closed"}`}>{survey.answered ? "Respondida" : "Cerrada"}</span><div><strong>{survey.subject}</strong><small>{survey.courseCode} · Grupo {survey.group} · {survey.period}</small></div><BadgeCheck size={18} /></article>)}</div></section>}

    {(data?.subjectResults.length ?? 0) > 0 && <section className="e09-section"><div className="e09-section-head"><div><span className="eyebrow">RESULTADOS PUBLICADOS</span><h2>Retroalimentación agregada</h2><p>Resultados de tus asignaciones que superaron el mínimo de privacidad; no incluyen respuestas individuales.</p></div></div><div className="e09-results-grid">{data?.subjectResults.map((result, index) => <article className="e09-result-card" key={`${result.courseCode}-${result.group}-${result.version}-${index}`}><div className="e09-result-head"><span className="e09-icon"><BarChart3 size={18} /></span><span className="e09-state state-done">{result.responseCount} respuestas</span></div><span className="e09-kicker">{result.courseCode} · Grupo {result.group} · {result.period}</span><h3>{result.course}</h3><p>{result.campaign} · versión {result.version}</p><MetricList metrics={result.metrics} questions={data?.questionnaire ?? []} /><small className="e09-published"><BadgeCheck size={14} /> Publicado {dateLabel(result.publishedAt)}</small></article>)}</div></section>}

    {data?.canManage && <section className="e09-section e09-management"><div className="e09-section-head"><div><span className="eyebrow">COORDINACIÓN ACADÉMICA</span><h2>Campañas y resultados</h2><p>Administra encuestas por asignatura y grupo dentro de tu ámbito autorizado.</p></div><button className="button button-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={16} /> Nueva campaña</button></div>
      {showCreate && <form className="e09-create-form" onSubmit={createCampaign}><div className="e09-form-heading"><div><span className="eyebrow">NUEVA VERSIÓN</span><h3>Configurar campaña</h3></div><span><LockKeyhole size={15} /> Umbral mínimo: 5</span></div><label>Grupo y asignatura<select name="offeringId" required defaultValue=""><option value="" disabled>Selecciona un grupo asignado</option>{data.offerings.map((offering) => <option key={offering.id} value={offering.id}>{offering.careerCode} · {offering.courseCode} · Grupo {offering.group} · {offering.period}</option>)}</select></label><label>Nombre de campaña<input name="title" required maxLength={180} defaultValue="Evaluación de experiencia académica" /></label><div className="e09-form-grid"><label>Abre<input name="opensAt" type="datetime-local" required defaultValue={localInput(new Date(Date.now() + 60_000))} /></label><label>Cierra<input name="closesAt" type="datetime-local" required defaultValue={localInput(new Date(Date.now() + 14 * 86_400_000))} /></label><label>Umbral de publicación<input name="minimumResponses" type="number" required min={5} max={100} defaultValue={5} /><small>Debe ser 5 o más; las muestras menores no publican métricas.</small></label></div><div className="e09-form-actions"><button type="button" className="button button-secondary" onClick={() => setShowCreate(false)}>Volver</button><button className="button button-primary" disabled={busy || !data.offerings.length}>{busy ? "Guardando…" : "Guardar borrador"}</button></div>{!data.offerings.length && <p className="e09-inline-help">No hay grupos asignados con docente o auxiliar vigente en tu ámbito.</p>}</form>}
      {data.campaigns.length ? <div className="e09-campaign-list">{data.campaigns.map((campaign) => <article className="e09-campaign-card" key={campaign.id}><div className="e09-campaign-head"><div><span className="e09-kicker">{campaign.careerCode} · {campaign.courseCode} · Grupo {campaign.group} · {campaign.period}</span><h3>{campaign.title}</h3><small>Versión {campaign.version} · Umbral de privacidad: {campaign.minimumResponses} · Cierra {dateLabel(campaign.closesAt)}</small></div><span className={`e09-state state-${campaign.status}`}>{statusLabel[campaign.status] ?? campaign.statusLabel}</span></div><div className="e09-target-grid">{campaign.targets.map((target) => <article className="e09-target-result" key={target.id}><div><strong>{target.subject}</strong><small>{target.role}</small></div>{target.result?.state === "published" && target.result.metrics ? <><span className="e09-response-count">{target.result.responseCount} respuestas válidas</span><MetricList metrics={target.result.metrics} questions={data.questionnaire} compact /></> : target.result?.state === "suppressed" ? <div className="e09-suppressed"><LockKeyhole size={15} /><span>Resultado suprimido. No se alcanzó el mínimo de privacidad.</span></div> : <div className="e09-suppressed"><LockKeyhole size={15} /><span>La participación individual y los conteos bajo el umbral permanecen ocultos.</span></div>}</article>)}</div>{campaign.canCancel && <div className="e09-cancel-row"><label htmlFor={`cancel-${campaign.id}`}>Motivo si decides cancelar antes de recibir respuestas</label><input id={`cancel-${campaign.id}`} value={cancelReason[campaign.id] ?? ""} onChange={(event) => setCancelReason((current) => ({ ...current, [campaign.id]: event.target.value }))} minLength={10} maxLength={300} placeholder="Indica por qué debe cancelarse esta campaña" /><button className="e09-cancel-button" disabled={busy || (cancelReason[campaign.id] ?? "").trim().length < 10} onClick={() => void act(`/api/v1/evaluations/campaigns/${campaign.id}/cancel/`, "Campaña cancelada y conservada en el historial.", { reason: cancelReason[campaign.id] })}>Cancelar campaña</button></div>}<div className="e09-campaign-actions">{campaign.canPublish && <button className="button button-primary" disabled={busy} onClick={() => void act(`/api/v1/evaluations/campaigns/${campaign.id}/open/`, "Campaña abierta; el padrón habilitado quedó congelado.")}>Abrir campaña</button>}{campaign.canClose && <button className="button button-secondary" disabled={busy} onClick={() => void act(`/api/v1/evaluations/campaigns/${campaign.id}/close/`, "Campaña cerrada. Ya no admite nuevas respuestas.")}>Cerrar respuestas</button>}{campaign.canPublishResults && <button className="button button-primary" disabled={busy} onClick={() => void act(`/api/v1/evaluations/campaigns/${campaign.id}/publish-results/`, "Resultados agregados publicados; los grupos bajo el umbral permanecen protegidos.")}>Calcular y publicar resultados</button>}</div></article>)}</div> : <div className="e09-empty"><div><ClipboardCheck size={22} /></div><h3>Aún no hay campañas</h3><p>Crea una campaña para una asignatura y un grupo con asignación docente vigente.</p><button className="button button-primary" onClick={() => setShowCreate(true)}><Plus size={16} /> Configurar campaña</button></div>}
    </section>}

    {!openSurveys.length && !data?.canManage && !(data?.subjectResults.length) && <div className="e09-empty"><div><MessageSquareText size={22} /></div><h2>No hay encuestas disponibles</h2><p>Cuando coordinación publique una campaña para uno de tus grupos activos, aparecerá aquí.</p></div>}
    <span className="sr-only" aria-live="polite">{notice}</span>
  </div>;
}

function MetricList({ metrics, questions, compact = false }: { metrics: Record<string, Metric>; questions: Data["questionnaire"]; compact?: boolean }) {
  return <div className={`e09-metric-list ${compact ? "compact" : ""}`}>{questions.map((question) => {
    const metric = metrics[question.code];
    if (!metric) return null;
    const peak = Math.max(1, ...Object.values(metric.distribution));
    return <div className="e09-metric" key={question.code}><div className="e09-metric-label"><span>{question.label}</span><strong>{metric.mean.toFixed(2)} / 5</strong></div><div className="e09-distribution" role="img" aria-label={`${question.label}: promedio ${metric.mean.toFixed(2)} de 5. Distribución: ${Object.entries(metric.distribution).map(([score, count]) => `${score}: ${count}`).join(", ")}`}>
      {Object.entries(metric.distribution).map(([score, count]) => <span key={score} title={`${score}: ${count}`} style={{ height: `${Math.max(8, (count / peak) * 34)}px` }}><i>{count > 0 ? count : ""}</i></span>)}
    </div><div className="e09-scale-legend" aria-hidden="true"><span>1 · Nunca</span><span>3 · A veces</span><span>5 · Siempre</span></div></div>;
  })}</div>;
}
