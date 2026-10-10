import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDownLeft, ArrowUpRight, BadgeCheck, CircleAlert, FileCheck2, LoaderCircle, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "../../api";

type Enrollment = { id: string; student: string; studentNumber: string; career: string; careerCode: string; period: string; periodCode: string };
type Source = { id: string; enrollment: string; title: string; category: string; points: number; available: number; date: string };
type Review = { decision: string; reason: string; reviewer: string; at: string } | null;
type Request = { id: string; amount: number; reason: string; status: string; statusLabel: string; riskFlags: string[]; submittedAt: string; sender: Enrollment; recipient: Enrollment; activity: string; category: string; isSender: boolean; canCancel: boolean; canReview: boolean; review: Review; riskAlerts: Array<{ id: string; code: string; description: string; status: string; resolutionReason: string }>; adjustments: Array<{ id: string; points: number; reason: string; enrollment: string; createdAt: string }> };
type Balance = { enrollment: string; career: string; careerCode: string; period: string; merit: number; sent: number; received: number; transferable: number };
type Data = { enrollments: Enrollment[]; recipients: Enrollment[]; sources: Source[]; requests: Request[]; reviewQueue: Request[]; riskAlerts: Array<{ id: string; requestId: string; code: string; description: string; career: string }>; balances: Balance[]; monthly: { sentOrPending: number; remaining: number; limit: number }; limits: { perRequest: number; perMonth: number }; canReviewTransfers: boolean };

const dateLabel = (value: string) => new Intl.DateTimeFormat("es-BO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));

export default function TransferPanel() {
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const idempotencyKey = useRef(crypto.randomUUID());
  const [amount, setAmount] = useState(1);

  async function load() {
    setLoading(true); setError("");
    try { setData(await api<Data>("/api/v1/transfers/")); }
    catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await api("/api/v1/transfers/", { method: "POST", body: JSON.stringify({
        senderEnrollment: form.get("senderEnrollment"), recipientEnrollment: form.get("recipientEnrollment"),
        activity: form.get("activity"), amount: Number(form.get("amount")), reason: form.get("reason"),
        idempotencyKey: idempotencyKey.current,
      }) });
      idempotencyKey.current = crypto.randomUUID();
      formElement.reset();
      setNotice("Solicitud enviada. Los puntos quedan reservados hasta la revisión independiente.");
      await load();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function cancel(id: string) {
    setBusy(true); setError("");
    try { await api(`/api/v1/transfers/${id}/cancel/`, { method: "POST", body: "{}" }); setNotice("Solicitud cancelada; el saldo reservado volvió a estar disponible."); await load(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function decide(id: string, decision: string, reason: string) {
    setBusy(true); setError("");
    try { await api(`/api/v1/transfers/${id}/review/`, { method: "POST", body: JSON.stringify({ decision, reason }) }); setNotice(decision === "approve" ? "Transferencia aprobada y registrada en ambos historiales." : "Solicitud rechazada con motivo registrado."); await load(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function resolveRisk(id: string, reason: string) {
    setBusy(true); setError("");
    try { await api(`/api/v1/transfers/alerts/${id}/resolve/`, { method: "POST", body: JSON.stringify({ reason }) }); setNotice("Alerta resuelta con movimientos compensatorios vinculados y decisión auditada."); await load(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  const activeEnrollments = data?.enrollments ?? [];
  const [senderId, setSenderId] = useState("");
  const selectedSenderId = senderId && activeEnrollments.some((item) => item.id === senderId) ? senderId : activeEnrollments[0]?.id ?? "";
  const sender = activeEnrollments.find((item) => item.id === selectedSenderId);
  const sourceOptions = (data?.sources ?? []).filter((item) => item.enrollment === selectedSenderId);
  const [selectedActivityId, setSelectedActivityId] = useState("");
  const currentActivityId = sourceOptions.some((item) => item.id === selectedActivityId) ? selectedActivityId : sourceOptions[0]?.id ?? "";
  const currentSource = sourceOptions.find((item) => item.id === currentActivityId);
  const recipients = (data?.recipients ?? []).filter((item) => item.careerCode === sender?.careerCode);
  useEffect(() => { setAmount(Math.min(5, currentSource?.available ?? 1)); }, [currentActivityId, currentSource?.available]);

  if (loading && !data) return <div className="loading-state"><LoaderCircle size={20} className="spin" /> Cargando transferencias…</div>;
  if (!data) return <div className="error-banner" role="alert">{error || "No se pudo cargar la información."} <button className="text-button" onClick={() => void load()}>Reintentar</button></div>;

  return <div className="transfer-page">
    {error && <div className="error-banner" role="alert">{error}<button className="text-button" onClick={() => void load()}>Reintentar</button></div>}
    {notice && <div className="transfer-notice" role="status"><BadgeCheck size={17} />{notice}</div>}
    <section className="transfer-intro"><div><span className="eyebrow">RECONOCIMIENTO ENTRE ESTUDIANTES</span><h2>Colaborar también deja huella.</h2><p>Propón un reconocimiento por una colaboración validada. Una persona autorizada e independiente revisará la solicitud antes de mover los puntos.</p></div><div className="transfer-rule"><ShieldCheck size={19} /><span>Solo méritos transferibles aprobados<br /><strong>Máximo {data.limits.perRequest} por solicitud · {data.limits.perMonth} por mes</strong></span></div></section>
    <section className="transfer-balances" aria-label="Resumen de puntos"><article><small>Mérito propio</small><strong>{data.balances.reduce((sum, row) => sum + row.merit, 0)} <span>pts</span></strong><p>Cuenta para niveles y trayectoria.</p></article><article><small>Transferible disponible</small><strong>{data.balances.reduce((sum, row) => sum + row.transferable, 0)} <span>pts</span></strong><p>Solo en colaboraciones aprobadas.</p></article><article><small>Enviado</small><strong>{data.balances.reduce((sum, row) => sum + row.sent, 0)} <span>pts</span></strong><p>Se mantiene separado del mérito.</p></article><article><small>Recibido</small><strong>{data.balances.reduce((sum, row) => sum + row.received, 0)} <span>pts</span></strong><p>No se puede volver a transferir.</p></article><article><small>Límite mensual disponible</small><strong>{data.monthly.remaining} <span>de {data.monthly.limit} pts</span></strong><p>{data.monthly.sentOrPending} enviados o reservados este mes.</p></article></section>

    <div className="transfer-layout"><section className="transfer-card"><div className="transfer-card-heading"><span className="transfer-icon"><Send size={18} /></span><div><span className="eyebrow">NUEVO RECONOCIMIENTO</span><h3>Reconocer colaboración</h3></div></div>
      {!activeEnrollments.length ? <div className="transfer-empty"><CircleAlert size={18} /><p>Necesitas una matrícula activa para enviar reconocimientos.</p></div> : !sourceOptions.length ? <div className="transfer-empty"><CircleAlert size={18} /><p>Aún no hay puntos disponibles. Primero debe aprobarse una evidencia con una categoría de colaboración o mentoría transferible.</p></div> : !recipients.length ? <div className="transfer-empty"><CircleAlert size={18} /><p>No hay otra matrícula activa de tu carrera disponible como destinataria.</p></div> : <form className="transfer-form" onSubmit={submit}>
        <label>Mi matrícula<select name="senderEnrollment" value={selectedSenderId} onChange={(event) => { setSenderId(event.target.value); setSelectedActivityId(""); }}>{activeEnrollments.map((item) => <option key={item.id} value={item.id}>{item.careerCode} · {item.period}</option>)}</select></label>
        <label>Actividad de colaboración aprobada<select name="activity" value={currentActivityId} onChange={(event) => setSelectedActivityId(event.target.value)} required>{sourceOptions.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.category} · {item.available} disponibles</option>)}</select><small>El origen de los puntos queda enlazado al movimiento SPD validado.</small></label>
        <label>Estudiante destinatario<select name="recipientEnrollment" required>{recipients.map((item) => <option key={item.id} value={item.id}>{item.student} · {item.studentNumber} · {item.period}</option>)}</select><small>Solo matrículas activas de {sender?.career}.</small></label>
        <label>Cantidad de puntos<input name="amount" type="number" min="1" max={Math.min(data.limits.perRequest, currentSource?.available ?? data.limits.perRequest)} value={amount} onChange={(event) => setAmount(Number(event.target.value))} required /><small>Saldo disponible en este origen: {currentSource?.available ?? 0} puntos.</small></label>
        <label>Motivo y aporte concreto<textarea name="reason" required minLength={10} maxLength={500} rows={3} placeholder="Describe qué aporte realizó la otra persona en esta actividad…" /></label>
        <div className="transfer-explainer"><FileCheck2 size={17} /><span>La solicitud queda pendiente. El revisor no puede ser el emisor ni el destinatario. Los puntos se reservan mientras se revisa.</span></div>
        <button className="button button-primary" disabled={busy}><Send size={16} />{busy ? "Enviando…" : "Enviar a revisión"}</button>
      </form>}
    </section>

    {data.canReviewTransfers && <section className="transfer-card transfer-review"><div className="transfer-card-heading"><span className="transfer-icon transfer-icon-amber"><ShieldCheck size={18} /></span><div><span className="eyebrow">REVISIÓN INDEPENDIENTE</span><h3>Solicitudes para revisar</h3></div><span className="transfer-count">{data.reviewQueue.length}</span></div>
      {data.reviewQueue.length ? <div className="transfer-request-list">{data.reviewQueue.map((request) => <TransferReviewCard key={request.id} request={request} busy={busy} onDecide={(decision, reason) => void decide(request.id, decision, reason)} />)}</div> : <p className="transfer-muted">No tienes solicitudes pendientes en tus ámbitos autorizados.</p>}
    </section>}
    </div>

    {data.riskAlerts.length > 0 && <section className="transfer-risk-section"><div className="transfer-section-heading"><div><span className="eyebrow">ALERTAS RESTRINGIDAS</span><h3>Revisión de irregularidades</h3><p>Al resolver una revocación posterior, se agregan contrapartidas vinculadas para cancelar el reconocimiento afectado.</p></div><span>{data.riskAlerts.length} abiertas</span></div><div className="transfer-risk-list">{data.riskAlerts.map((alert) => <RiskAlertCard key={alert.id} alert={alert} busy={busy} onResolve={(reason) => void resolveRisk(alert.id, reason)} />)}</div></section>}

    <section className="transfer-card transfer-history"><div className="transfer-section-heading"><div><span className="eyebrow">HISTORIAL TRAZABLE</span><h3>Mis transferencias</h3><p>Los envíos y recepciones permanecen aparte del mérito propio.</p></div><button className="transfer-refresh" aria-label="Actualizar transferencias" onClick={() => void load()}><RefreshCw size={16} /></button></div>
      {data.requests.length ? <div className="transfer-request-list">{data.requests.map((request) => <article className="transfer-request" key={request.id}><span className={`transfer-direction ${request.isSender ? "sent" : "received"}`}>{request.isSender ? <ArrowUpRight size={18} /> : <ArrowDownLeft size={18} />}</span><div className="transfer-request-main"><div className="transfer-request-title"><strong>{request.isSender ? `Para ${request.recipient.student}` : `De ${request.sender.student}`}</strong><span className={`transfer-status status-${request.status}`}>{request.statusLabel}</span></div><p>{request.amount} pts · {request.activity} · {request.category}</p><p className="transfer-reason">“{request.reason}”</p><small>{dateLabel(request.submittedAt)} · {request.sender.careerCode} · {request.sender.period}</small>{request.review && <div className="transfer-review-note"><strong>{request.review.decision === "approve" ? "Aprobada" : "Rechazada"} por {request.review.reviewer}</strong><span>{request.review.reason}</span></div>}{request.adjustments.length > 0 && <div className="transfer-review-note transfer-adjustment-note"><strong>Regularización compensatoria · {request.adjustments.reduce((sum, adjustment) => sum + adjustment.points, 0)} pts netos</strong>{request.adjustments.map((adjustment) => <span key={adjustment.id}>{adjustment.points > 0 ? "+" : ""}{adjustment.points} pts · {adjustment.reason}</span>)}</div>}{request.riskFlags.length > 0 && <div className="transfer-risk-flag"><CircleAlert size={14} /> Marcada para revisión prioritaria</div>}</div>{request.canCancel && <button className="transfer-cancel" disabled={busy} onClick={() => void cancel(request.id)}>Cancelar</button>}</article>)}</div> : <div className="transfer-empty"><FileCheck2 size={18} /><p>Todavía no tienes transferencias. Cuando participes en una colaboración aprobada, puedes proponer un reconocimiento.</p></div>}
    </section>
  </div>;
}

function TransferReviewCard({ request, busy, onDecide }: { request: Request; busy: boolean; onDecide: (decision: string, reason: string) => void }) {
  const [reason, setReason] = useState("");
  return <article className="transfer-review-item"><div className="transfer-review-item-head"><div><strong>{request.sender.student}</strong><span> → </span><strong>{request.recipient.student}</strong><small>{request.sender.careerCode} · {request.amount} puntos · {request.activity}</small></div><span className={`transfer-status status-${request.status}`}>{request.statusLabel}</span></div><p>{request.reason}</p>{request.riskFlags.length > 0 && <div className="transfer-risk-flag"><CircleAlert size={14} /> {request.riskFlags.join(" · ")} · requiere evaluación reforzada</div>}<label>Motivo de resolución<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={5} maxLength={500} rows={2} placeholder="Documenta la evidencia de colaboración y la decisión…" /></label><div className="transfer-review-actions"><button className="button button-secondary" disabled={busy || reason.trim().length < 5} onClick={() => onDecide("reject", reason)}>Rechazar</button><button className="button button-primary" disabled={busy || reason.trim().length < 5} onClick={() => onDecide("approve", reason)}><BadgeCheck size={15} /> Aprobar transferencia</button></div></article>;
}

function RiskAlertCard({ alert, busy, onResolve }: { alert: Data["riskAlerts"][number]; busy: boolean; onResolve: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return <article className="transfer-risk-item"><span><CircleAlert size={17} />{alert.description}</span><small>{alert.career} · Solicitud {alert.requestId.slice(0, 8)}</small><label>Resultado de la revisión<input value={reason} onChange={(event) => setReason(event.target.value)} minLength={10} maxLength={500} placeholder="Documenta la revisión y regularización…" /></label><button className="button button-secondary" disabled={busy || reason.trim().length < 10} onClick={() => onResolve(reason)}>Resolver alerta</button></article>;
}
