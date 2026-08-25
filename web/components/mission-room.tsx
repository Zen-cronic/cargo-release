"use client";

import {
  AlertOctagon, ArrowRight, BadgeCheck, Boxes, Check, ChevronRight, CircleDot,
  Clock3, FileCheck2, FileWarning, Fingerprint, KeyRound, Layers3, LoaderCircle,
  LockKeyhole, Network, PackageCheck, RefreshCcw, Route, ScanLine, ShieldCheck,
  Ship, Unplug, UsersRound, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createDemoMission, type Evidence, getMission, type MissionArtifact, type MissionSnapshot,
  postMissionAction, type Receipt, type ReceiptKind, type TruthMode,
} from "@/lib/cargo-api";

type Drawer = "architecture" | "fleet" | null;
type WorkspaceTab = "mission" | "evidence" | "documents" | "receipts" | "activity";

interface NextAction {
  eyebrow: string;
  title: string;
  detail: string;
  button: string;
  tone: "signal" | "danger" | "verified";
  invoke: (snapshot: MissionSnapshot) => Promise<MissionSnapshot>;
}

const receiptLabels: Record<ReceiptKind, string> = {
  INSURER_GUARANTEE: "Insurer guarantee",
  ADJUSTER_REJECTION: "Adjuster correction",
  ADJUSTER_ACCEPTANCE: "Full security accepted",
  CARRIER_RELEASE_ORDER: "Carrier release order",
  CARRIER_RELEASE_READBACK: "Carrier read-back",
};

const fleet = [
  ["Mission Coordinator", "mission-coordinator@1.0.0", "Routes work; never owns business truth."],
  ["Manifest Evidence", "manifest-evidence@1.0.0", "Reconciles cargo identifiers."],
  ["Coverage", "coverage-evidence@1.0.0", "Assembles policy questions; no coverage decision."],
  ["Security Pack", "security-pack@1.0.0", "Drafts bond and guarantee artifacts."],
  ["Adjuster Liaison", "adjuster-liaison@1.0.0", "Consumes independent review receipts."],
  ["Release Verifier", "carrier-verifier@1.0.0", "Requires order plus carrier read-back."],
  ["Adjustment Monitor", "adjustment-monitor@1.0.0", "Keeps the long-tail mission open."],
];

const tabs: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "mission", label: "Mission" },
  { id: "evidence", label: "Evidence" },
  { id: "documents", label: "Documents" },
  { id: "receipts", label: "Receipts" },
  { id: "activity", label: "Activity" },
];

function hasReceipt(snapshot: MissionSnapshot, kind: ReceiptKind) {
  return snapshot.receipts.some((receipt) => receipt.kind === kind);
}

function actionFor(snapshot: MissionSnapshot): NextAction | null {
  const { mission } = snapshot;
  if (mission.release_state === "EVIDENCE_BLOCKED") return {
    eyebrow: "Continuous action engine", title: "Start the cargo release mission",
    detail: "The fleet will reconcile evidence, quarantine unsafe instructions, and stop only at the owner-attestation gate.",
    button: "Start autonomous mission", tone: "signal",
    invoke: (current) => postMissionAction(current.mission.id, ":run"),
  };
  if (mission.release_state === "READY_FOR_SIGNATURE" && snapshot.approvals.length === 0) return {
    eyebrow: "Human authority required", title: "Owner bond is ready to attest",
    detail: "Review the generated artifact. Approval resumes the fleet; insurer, adjuster, correction, and carrier work then complete without step-through.",
    button: "Approve bond & resume", tone: "signal",
    invoke: (current) => postMissionAction(current.mission.id, "/approvals/owner-bond:approve-and-resume", current.mission.version, "cargo-owner.demo"),
  };
  if (mission.release_state !== "RELEASED") return {
    eyebrow: "Recovery-safe runtime", title: "Resume the bounded mission",
    detail: "The prior run stopped between verified transitions. Resume from durable state without replaying completed work.",
    button: "Resume autonomous mission", tone: "verified",
    invoke: (current) => postMissionAction(current.mission.id, ":run"),
  };
  return null;
}

export function MissionRoom() {
  const [snapshot, setSnapshot] = useState<MissionSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [tab, setTab] = useState<WorkspaceTab>("mission");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);

  const reset = useCallback(async () => {
    setBusy(true); setError(null); setTab("mission");
    try {
      const requestedMission = new URLSearchParams(window.location.search).get("mission");
      const next = requestedMission ? await getMission(requestedMission) : await createDemoMission();
      setSnapshot(next);
      setSelectedEvidenceId(next.evidence[0]?.id ?? null);
      setSelectedArtifactId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Mission API unavailable");
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { void reset(); }, [reset]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setDrawer(null); setReceipt(null); }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  const nextAction = useMemo(() => snapshot ? actionFor(snapshot) : null, [snapshot]);
  const advance = async () => {
    if (!snapshot || !nextAction || busy) return;
    setBusy(true); setError(null);
    try { setSnapshot(await nextAction.invoke(snapshot)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Action failed closed"); }
    finally { setBusy(false); }
  };

  if (!snapshot) return (
    <main className="loading-shell">
      <div className="loading-mark"><Ship aria-hidden="true" /></div>
      <p className="eyebrow">Opening synthetic mission</p><h1>Building the cargo evidence ledger…</h1>
      {error ? <><p className="error-copy"><Unplug size={16} /> {error}</p><button className="primary-button" onClick={() => void reset()}>Retry local API</button></> : <LoaderCircle className="spin" aria-label="Loading" />}
    </main>
  );

  const released = snapshot.mission.release_state === "RELEASED";
  const selectedEvidence = snapshot.evidence.find((item) => item.id === selectedEvidenceId) ?? snapshot.evidence[0];
  const selectedArtifact = snapshot.artifacts.find((item) => item.id === selectedArtifactId) ?? snapshot.artifacts.at(-1);
  return (
    <div className={`app-shell ${released ? "is-released" : ""}`}>
      <header className="mission-header">
        <div className="brand-block"><div className="brand-mark"><Boxes size={19} strokeWidth={1.8} /></div><div><strong>Cargo Release</strong><span>General Average mission control</span></div></div>
        <div className="case-identity"><span className="fictional-label">Fictional system</span><strong>{snapshot.mission.vessel}</strong><span>{snapshot.mission.case_ref} · {snapshot.mission.container_ref}</span></div>
        <div className="header-actions">
          <TruthBadge mode={snapshot.mission.truth_mode} />
          <button className="quiet-button" onClick={() => setDrawer("fleet")}><UsersRound size={15} /> Agent fleet</button>
          <button className="quiet-button" onClick={() => setDrawer("architecture")}><Network size={15} /> Architecture</button>
          <button className="icon-button" aria-label={snapshot.mission.truth_mode === "NATIVE" ? "Reload native mission" : "Reset exact fixture"} onClick={() => void reset()}><RefreshCcw size={16} /></button>
        </div>
      </header>
      <div className="safety-banner"><ShieldCheck size={15} /><strong>Deterministic authority</strong><span>Agents propose. Humans approve. Partners issue receipts. No real parties contacted.</span><span className="banner-ref">case v{snapshot.mission.version}</span></div>
      {error && <div className="error-banner"><AlertOctagon size={16} /> Action failed closed: {error}</div>}
      <nav className="workspace-tabs" aria-label="Mission workspace">
        <div className="tab-list">{tabs.map((item) => {
          const count = item.id === "evidence" ? snapshot.evidence.length : item.id === "documents" ? snapshot.artifacts.length : item.id === "receipts" ? snapshot.receipts.length : item.id === "activity" ? snapshot.events.length : null;
          return <button key={item.id} className={tab === item.id ? "active" : ""} aria-current={tab === item.id ? "page" : undefined} onClick={() => setTab(item.id)}>{item.label}{count !== null && <span>{count}</span>}</button>;
        })}</div>
        <div className={`tab-state ${released ? "released" : "held"}`}>{released ? <PackageCheck size={15} /> : <LockKeyhole size={15} />} Physical release: <strong>{released ? "RELEASED" : "HELD"}</strong></div>
      </nav>
      <main className="workspace-grid">
        <section className="workspace-stage">
          {tab === "mission" && <MissionPanel snapshot={snapshot} />}
          {tab === "evidence" && <EvidencePanel snapshot={snapshot} selected={selectedEvidence} onSelect={setSelectedEvidenceId} />}
          {tab === "documents" && <DocumentsPanel snapshot={snapshot} selected={selectedArtifact} onSelect={setSelectedArtifactId} />}
          {tab === "receipts" && <ReceiptsPanel snapshot={snapshot} onInspect={setReceipt} />}
          {tab === "activity" && <ActivityPanel snapshot={snapshot} />}
        </section>
        <DecisionRail snapshot={snapshot} nextAction={nextAction} busy={busy} onAdvance={advance} onNavigate={setTab} />
      </main>
      <footer className="mission-footer"><span><CircleDot size={11} /> {snapshot.mission.truth_mode === "NATIVE" ? "Native Eventarc mission" : "Local deterministic fixture"}</span><span>Release and General Average adjustment remain separate lifecycles.</span><span data-testid="adjustment-state"><RefreshCcw size={12} /> Adjustment <strong>{snapshot.mission.adjustment_state}</strong></span></footer>
      {drawer && <SideDrawer drawer={drawer} snapshot={snapshot} onClose={() => setDrawer(null)} />}
      {receipt && <ReceiptDialog receipt={receipt} onClose={() => setReceipt(null)} />}
    </div>
  );
}

function MissionPanel({ snapshot }: { snapshot: MissionSnapshot }) {
  const released = snapshot.mission.release_state === "RELEASED";
  const latest = snapshot.events.at(-1);
  return <div className="mission-panel">
    <div className="hero-heading"><div><p className="eyebrow">Business consequence · physical release</p><h1><span>Cargo</span>{" "}<em>{released ? "released" : "held at North Harbor"}</em></h1><p>{heroSentence(snapshot)}</p></div><div className={`release-state ${released ? "verified" : "held"}`}>{released ? <PackageCheck size={17} /> : <LockKeyhole size={17} />}{released ? "RELEASED" : "HELD"}</div></div>
    <HeldCargoHero snapshot={snapshot} />
    <div className="mission-summary-row">
      <article><span>Latest verified transition</span><strong>{latest ? eventTitle(latest.event_type) : "Mission opened"}</strong><small>{latest?.actor ?? "eventarc.fixture"} · {latest?.event_hash.slice(0, 8) ?? "pending"}</small></article>
      <article><span>Long-tail mission</span><strong>General Average adjustment stays open</strong><small>Cargo release does not settle contribution accounting.</small></article>
    </div>
  </div>;
}

function EvidencePanel({ snapshot, selected, onSelect }: { snapshot: MissionSnapshot; selected?: Evidence; onSelect: (id: string) => void }) {
  return <div className="detail-panel">
    <PanelHeading eyebrow="Evidence workspace" title="Trust the file, not the instruction" detail="Every source keeps its lineage. Model-addressed text can be inspected without entering mission memory." />
    <div className="evidence-browser">
      <div className="evidence-index">{snapshot.evidence.map((item) => <button key={item.id} className={selected?.id === item.id ? "active" : ""} onClick={() => onSelect(item.id)}><span className={`evidence-icon status-${item.status.toLowerCase()}`}>{item.status === "VERIFIED" ? <FileCheck2 /> : item.status === "QUARANTINED" ? <ShieldCheck /> : <FileWarning />}</span><span><small>{item.kind}</small><strong>{item.filename}</strong></span><ChevronRight size={15} /></button>)}</div>
      {selected && <article className={`evidence-detail status-${selected.status.toLowerCase()}`}>
        <div className="document-kicker"><span>{selected.kind}</span><strong>{selected.status.replace("_", " ")}</strong></div>
        <h2>{selected.filename}</h2><p className="document-summary">{selected.summary}</p>
        {selected.status === "QUARANTINED" && <div className="guard-note"><ScanLine size={18} /><div><strong>Model-addressed text is not a fact</strong><span>This source remains visible to the operator but cannot mutate mission memory or release state.</span></div></div>}
        <dl className="document-facts"><div><dt>Evidence ID</dt><dd>{selected.id}</dd></div>{Object.entries(selected.facts).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>
        <div className="digest-block"><Fingerprint size={15} /><span>Source digest</span><code>sha256:{selected.sha256}</code></div>
      </article>}
    </div>
  </div>;
}

function DocumentsPanel({ snapshot, selected, onSelect }: { snapshot: MissionSnapshot; selected?: MissionArtifact; onSelect: (id: string) => void }) {
  return <div className="detail-panel">
    <PanelHeading eyebrow="Generated instruments" title="Inspect what the fleet produced" detail="Every legal-adjacent artifact is versioned, content-addressed, and kept separate from the state transition that consumes it." />
    {snapshot.artifacts.length === 0 ? <div className="large-empty"><FileCheck2 size={34} /><h2>No instrument generated yet</h2><p>Start the mission to create the owner bond from reconciled evidence.</p></div> : <div className="evidence-browser artifact-browser">
      <div className="evidence-index">{snapshot.artifacts.slice().reverse().map((item) => <button key={item.id} className={selected?.id === item.id ? "active" : ""} onClick={() => onSelect(item.id)}><span className={`evidence-icon ${item.status === "DRAFT" ? "" : "status-verified"}`}><FileCheck2 /></span><span><small>{item.kind.replaceAll("_", " ")} · V{item.revision}</small><strong>{item.status}</strong></span><ChevronRight size={15} /></button>)}</div>
      {selected && <article className="evidence-detail status-verified">
        <div className="document-kicker"><span>{selected.kind.replaceAll("_", " ")} · revision {selected.revision}</span><strong>{selected.status}</strong></div>
        <h2>{selected.kind === "OWNER_BOND" ? "Cargo owner General Average bond" : "Full security submission pack"}</h2>
        <p className="document-summary">Generated from reviewed mission facts. This instrument cannot release cargo by itself.</p>
        <dl className="document-facts">{Object.entries(selected.content).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value ?? "—")}</dd></div>)}</dl>
        <div className="digest-block"><Fingerprint size={15} /><span>Artifact digest</span><code>sha256:{selected.digest}</code></div>
      </article>}
    </div>}
  </div>;
}

function ReceiptsPanel({ snapshot, onInspect }: { snapshot: MissionSnapshot; onInspect: (receipt: Receipt) => void }) {
  return <div className="detail-panel"><PanelHeading eyebrow="Authority ledger" title="Receipts unlock cargo" detail="Agent output is advisory. Independent, issuer-bound receipts are the keys that permit state transitions." />
    {snapshot.receipts.length === 0 ? <div className="large-empty"><KeyRound size={34} /><h2>No partner authority recorded</h2><p>Receipts will appear here as the insurer, adjuster, and carrier independently respond.</p></div> : <div className="receipt-gallery">{snapshot.receipts.slice().reverse().map((item) => <button key={item.id} className={item.kind === "ADJUSTER_REJECTION" ? "rejected" : ""} onClick={() => onInspect(item)}><span className="receipt-icon">{item.kind === "ADJUSTER_REJECTION" ? <FileWarning size={17} /> : <FileCheck2 size={17} />}</span><span><small>{item.issuer}</small><strong>{receiptLabels[item.kind]}</strong><code>{item.external_id}</code></span><ChevronRight size={17} /></button>)}</div>}
  </div>;
}

function ActivityPanel({ snapshot }: { snapshot: MissionSnapshot }) {
  return <div className="detail-panel activity-panel"><PanelHeading eyebrow="Hash-linked activity" title="Every change has a cause" detail="The mission is reconstructable from append-only events, actor identities, and trace spans." /><MissionSpine snapshot={snapshot} /></div>;
}

function PanelHeading({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return <div className="panel-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{detail}</p></div>;
}

function DecisionRail({ snapshot, nextAction, busy, onAdvance, onNavigate }: { snapshot: MissionSnapshot; nextAction: NextAction | null; busy: boolean; onAdvance: () => Promise<void>; onNavigate: (tab: WorkspaceTab) => void }) {
  const adjuster = hasReceipt(snapshot, "ADJUSTER_ACCEPTANCE");
  const carrier = hasReceipt(snapshot, "CARRIER_RELEASE_READBACK");
  const latestRun = snapshot.runs.at(-1);
  return <aside className="decision-rail" aria-labelledby="action-title">
    <div className="rail-heading"><span>Next decision</span><strong id="action-title">What needs you now</strong></div>
    {nextAction ? <div className={`next-action tone-${nextAction.tone}`}><span className="action-eyebrow">{nextAction.eyebrow}</span><h2>{nextAction.title}</h2><p>{nextAction.detail}</p><button data-testid="primary-action" className="primary-button" disabled={busy} onClick={() => void onAdvance()}>{busy ? <LoaderCircle className="spin" size={17} /> : <CircleDot size={17} />}{busy ? "Recording…" : nextAction.button}{!busy && <ArrowRight size={16} />}</button></div> : <div className="release-complete"><BadgeCheck size={25} /><span className="action-eyebrow">No release action open</span><h2>Carrier read-back verified</h2><p>The container is released. Adjustment monitoring remains active and separate.</p></div>}
    {latestRun && <div className={`runtime-status status-${latestRun.status.toLowerCase()}`}><span><CircleDot size={13} /> Autonomous runtime</span><strong>{latestRun.status.replace("_", " ")}</strong><small>{latestRun.steps} bounded steps · {latestRun.reason.replaceAll("_", " ").toLowerCase()}</small></div>}
    <div className="authority-block">
      <div className="human-authority"><span>Human authority</span>{snapshot.approvals.length ? <strong className="verified"><Check size={14} /> Owner bond attested</strong> : <strong className="pending"><LockKeyhole size={14} /> Awaiting owner</strong>}</div>
      <AuthorityCard label="Adjuster key" complete={adjuster} detail={adjuster ? "Full security accepted" : "Acceptance receipt missing"} />
      <AuthorityCard label="Carrier key" complete={carrier} detail={carrier ? "Read-back verified" : "Order + read-back required"} />
    </div>
    <div className="rail-links">
      <button onClick={() => onNavigate("evidence")}><span><Layers3 size={16} /><strong>Evidence</strong></span><small>{snapshot.evidence.length} sources</small><ChevronRight size={15} /></button>
      <button onClick={() => onNavigate("documents")}><span><FileCheck2 size={16} /><strong>Documents</strong></span><small>{snapshot.artifacts.length} versions</small><ChevronRight size={15} /></button>
      <button onClick={() => onNavigate("receipts")}><span><KeyRound size={16} /><strong>Receipts</strong></span><small>{snapshot.receipts.length} verified</small><ChevronRight size={15} /></button>
      <button onClick={() => onNavigate("activity")}><span><Clock3 size={16} /><strong>Activity</strong></span><small>{snapshot.events.length} events</small><ChevronRight size={15} /></button>
    </div>
  </aside>;
}

function TruthBadge({ mode }: { mode: TruthMode }) { return <span className={`truth-badge mode-${mode.toLowerCase()}`}>{mode}</span>; }

function heroSentence(snapshot: MissionSnapshot) {
  const state = snapshot.mission.release_state;
  if (state === "EVIDENCE_BLOCKED") return "One identifier conflict blocks the security pack. No party has accepted anything.";
  if (state === "READY_FOR_SIGNATURE") return "Evidence is reconciled. Human and insurer authority must now complete the security pack.";
  if (state === "SECURITY_SUBMITTED") return "Full security is under independent adjuster review. The container remains held.";
  if (state === "SECURITY_ACCEPTED") return "The adjuster key is verified. Carrier release and read-back are still required.";
  return "Both independent release keys are verified. The casualty adjustment continues on its own clock.";
}

function HeldCargoHero({ snapshot }: { snapshot: MissionSnapshot }) {
  const owner = snapshot.approvals.length > 0;
  const guarantee = hasReceipt(snapshot, "INSURER_GUARANTEE");
  const adjuster = hasReceipt(snapshot, "ADJUSTER_ACCEPTANCE");
  const carrier = hasReceipt(snapshot, "CARRIER_RELEASE_READBACK");
  const steps = [["Owner bond", "HUMAN", owner], ["Guarantee", "INSURER", guarantee], ["Security accepted", "ADJUSTER KEY", adjuster], ["Release read-back", "CARRIER KEY", carrier]] as const;
  return <div className="cargo-hero">
    <div className="chain-track" aria-label="Receipt-keyed release chain">{steps.map(([label, authority, complete], index) => <div key={label} className={`chain-step ${complete ? "complete" : ""}`}>{index > 0 && <span className="chain-link" />}<span className="chain-node">{complete ? <Check size={17} /> : <LockKeyhole size={15} />}</span><strong>{label}</strong><small>{authority}</small></div>)}</div>
    <div className={`container-visual ${carrier ? "doors-open" : ""}`}><div className="container-shadow" /><div className="container-body"><div className="container-door left"><span /><span /><span /></div><div className="container-door right"><span /><span /><span /></div><div className="container-id">{snapshot.mission.container_ref}</div><div className={`seal adjuster-seal ${adjuster ? "unlocked" : ""}`}><KeyRound size={14} /><span>ADJ</span></div><div className={`seal carrier-seal ${carrier ? "unlocked" : ""}`}><KeyRound size={14} /><span>CAR</span></div></div><div className="quay-line"><Route size={15} /> North Harbor · Terminal 4</div></div>
    <div className="release-rule"><ShieldCheck size={16} /><span><strong>Two-key release.</strong> Adjuster acceptance alone cannot release physical cargo.</span></div>
  </div>;
}

function AuthorityCard({ label, complete, detail }: { label: string; complete: boolean; detail: string }) { return <div className={`authority-card ${complete ? "complete" : ""}`}><span>{complete ? <BadgeCheck size={16} /> : <LockKeyhole size={15} />}{label}</span><strong>{detail}</strong></div>; }

function MissionSpine({ snapshot }: { snapshot: MissionSnapshot }) { return <ol className="mission-spine">{snapshot.events.slice().reverse().map((event, index) => <li key={event.seq}><span className={`spine-dot ${index === 0 ? "current" : ""}`}>{index === 0 ? <CircleDot size={13} /> : <Check size={11} />}</span><time>{new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time><div><strong>{eventTitle(event.event_type)}</strong><span>{event.actor}</span></div><code>{event.event_hash.slice(0, 8)}</code></li>)}</ol>; }

function eventTitle(type: string) { return type.split("_").map((word) => word[0] + word.slice(1).toLowerCase()).join(" "); }

function SideDrawer({ drawer, snapshot, onClose }: { drawer: Exclude<Drawer, null>; snapshot: MissionSnapshot; onClose: () => void }) {
  const memoryTrace = snapshot.traces.find((item) => item.operation === "persist_reviewed_release_context");
  const memoryRef = String(memoryTrace?.detail.memory_ref ?? "");
  const memoryMode: TruthMode = memoryRef.startsWith("projects/") ? "NATIVE" : "ADAPTER";
  return <div className="overlay" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><aside className="side-drawer" role="dialog" aria-modal="true" aria-label={drawer === "fleet" ? "Agent fleet" : "Architecture"}>
    <div className="drawer-header"><div><span className="eyebrow">Inspect, do not trust logos</span><h2>{drawer === "fleet" ? "Versioned capability fleet" : "Transition ownership"}</h2></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
    {drawer === "fleet" ? <div className="fleet-list">{fleet.map(([name, version, detail], index) => { const trace = snapshot.traces.find((item) => item.agent.includes(version.split("@")[0])); return <article key={version}><span className="fleet-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{name}</strong><code>{version}</code><p>{detail}</p></div><TruthBadge mode={trace?.truth_mode ?? "ADAPTER"} /></article>; })}</div> : <div className="architecture-list">{[
      ["Eventarc intake", "Authenticated CloudEvent opens one idempotent mission", snapshot.mission.truth_mode],
      ["Agent Runtime + ADK", "Managed coordinator deployment with one bounded advance tool", "ADAPTER"],
      ["Memory Bank", "Reviewed release context only; never authoritative state", memoryMode],
      ["Model Armor", "Managed template retained; gateway enforcement remains pending", "ADAPTER"],
      ["Agent Registry", "Versioned fleet discovery and approved endpoints", "ADAPTER"],
      ["Agent Identity + Gateway", "Consent-gated egress configuration; route proof pending", "ADAPTER"],
      ["Agent Observability", "OpenTelemetry topology, traces, and security spans", "ADAPTER"],
      ["Partner Cloud Run", "Independent insurer, adjuster, and carrier fixtures", "FIXTURE"],
    ].map(([name, detail, mode], index) => <article key={String(name)}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{name}</strong><p>{detail}</p></div><TruthBadge mode={mode as TruthMode} /></article>)}<div className="architecture-rule"><ShieldCheck size={18} /><p><strong>One authority.</strong> Model output and managed memory never write release state. Deterministic transitions require verified receipts and allowed prior state.</p></div></div>}
  </aside></div>;
}

function ReceiptDialog({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  return <div className="overlay dialog-overlay" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><section className="receipt-dialog" role="dialog" aria-modal="true" aria-labelledby="receipt-title">
    <div className="receipt-dialog-top"><span className="receipt-stamp"><BadgeCheck size={19} /> VERIFIED FIXTURE</span><button className="icon-button" aria-label="Close receipt" onClick={onClose}><X size={18} /></button></div>
    <p className="eyebrow">Independent partner receipt</p><h2 id="receipt-title">{receiptLabels[receipt.kind]}</h2>
    <dl><div><dt>Issuer</dt><dd>{receipt.issuer}</dd></div><div><dt>External reference</dt><dd>{receipt.external_id}</dd></div><div><dt>Status</dt><dd>{receipt.status.replaceAll("_", " ")}</dd></div><div><dt>Subject</dt><dd>{receipt.subject_ref}</dd></div><div><dt>Issued</dt><dd>{new Date(receipt.issued_at).toLocaleString()}</dd></div></dl>
    <div className="receipt-digest"><Fingerprint size={14} /><span>sha256</span><code>{receipt.digest}</code></div><p className="receipt-footnote">Synthetic partner identity · HMAC signature verified by the mission gateway · no real external delivery.</p>
  </section></div>;
}
