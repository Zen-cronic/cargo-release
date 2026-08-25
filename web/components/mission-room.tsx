"use client";

import {
  AlertOctagon, ArrowRight, BadgeCheck, Boxes, Check, ChevronRight, CircleDot,
  BrainCircuit, Clock3, FileCheck2, FileWarning, Film, Fingerprint, KeyRound, Layers3, LoaderCircle,
  LockKeyhole, Moon, Network, PackageCheck, RefreshCcw, Route, ScanLine, ShieldCheck,
  Send, Ship, Sun, Unplug, UsersRound, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  createDemoMission, type Evidence, generateVeoReplay, getMission, type MissionArtifact,
  type MissionSnapshot, postMissionAction, type Receipt, type ReceiptKind, type TruthMode,
  veoReplayMediaUrl,
} from "@/lib/cargo-api";
import { missionFrictionMetric } from "@/lib/mission-metrics";

type Drawer = "architecture" | "fleet" | null;
type WorkspaceTab = "mission" | "authority" | "evidence" | "documents" | "receipts" | "models" | "activity";
type Theme = "dark" | "light";
type MapState = "complete" | "active" | "idle" | "blocked";

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
  { kind: "ADK", name: "Mission Coordinator", version: "cargo_release_coordinator", detail: "Owns the only lease-protected bounded advance tool; never owns business truth.", fallback: "ADAPTER" },
  { kind: "ADK · READ", name: "Manifest Evidence Worker", version: "manifest_evidence_worker", detail: "Sees statuses, fact keys, and immutable digests—not raw evidence text.", fallback: "ADAPTER" },
  { kind: "ADK · READ", name: "Security Pack Worker", version: "security_pack_worker", detail: "Audits the human, insurer, and adjuster security chain without mutation tools.", fallback: "ADAPTER" },
  { kind: "ADK · READ", name: "Carrier Authority Worker", version: "carrier_authority_worker", detail: "Audits acceptance, release order, and read-back references only.", fallback: "ADAPTER" },
  { kind: "ADK · READ", name: "Runtime Recovery Worker", version: "runtime_recovery_worker", detail: "Classifies durable state; cannot acquire a lease or resume a run.", fallback: "ADAPTER" },
  { kind: "CONTROL", name: "Deterministic Receipt Saga", version: "security-pack@1.0.0", detail: "Cloud SQL state machine applies allowed transitions and verified partner receipts.", fallback: "FIXTURE" },
  { kind: "CONTROL", name: "Release Notifier", version: "release-notifier@1.0.0", detail: "Sends one marked synthetic notice only after carrier read-back.", fallback: "FIXTURE" },
  { kind: "MODEL · ADVISORY", name: "Gemma Critic", version: "gemma-release-critic@1.0.0", detail: "Reviews sanitized proposals with release_authority=false.", fallback: "ADAPTER" },
  { kind: "MODEL · ADVISORY", name: "Replay Producer", version: "veo-post-release-replay@1.0.0", detail: "Generates training media only after physical release.", fallback: "ADAPTER" },
  { kind: "CONTROL", name: "Adjustment Monitor", version: "adjustment-monitor@1.0.0", detail: "Persists reviewed context while the long-tail adjustment remains open.", fallback: "ADAPTER" },
] as const;

const tabs: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "mission", label: "Mission" },
  { id: "authority", label: "Authority map" },
  { id: "evidence", label: "Evidence" },
  { id: "documents", label: "Documents" },
  { id: "receipts", label: "Receipts" },
  { id: "models", label: "AI checks" },
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
    invoke: (current) => postMissionAction(current.mission.id, "/approvals/owner-bond:approve-and-resume", current.mission.version),
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
  const [theme, setTheme] = useState<Theme>("dark");

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
  const generateReplay = async () => {
    if (!snapshot || snapshot.mission.release_state !== "RELEASED" || busy) return;
    setBusy(true); setError(null); setTab("models");
    try { setSnapshot(await generateVeoReplay(snapshot.mission.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Replay generation failed closed"); }
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
  const notification = snapshot.notifications?.at(-1);
  const selectedEvidence = snapshot.evidence.find((item) => item.id === selectedEvidenceId) ?? snapshot.evidence[0];
  const selectedArtifact = snapshot.artifacts.find((item) => item.id === selectedArtifactId) ?? snapshot.artifacts.at(-1);
  return (
    <div className={`app-shell theme-${theme} ${released ? "is-released" : ""}`}>
      <header className="mission-header">
        <div className="brand-block"><div className="brand-mark"><Boxes size={19} strokeWidth={1.8} /></div><div><strong>Cargo Release</strong><span>General Average mission control</span></div></div>
        <div className="case-identity"><span className="fictional-label">Fictional system</span><strong>{snapshot.mission.vessel}</strong><span>{snapshot.mission.case_ref} · {snapshot.mission.container_ref}</span></div>
        <div className="header-actions">
          <TruthBadge mode={snapshot.mission.truth_mode} />
          <button className="quiet-button" onClick={() => setDrawer("fleet")}><UsersRound size={15} /> Agent fleet</button>
          <button className="quiet-button" onClick={() => setDrawer("architecture")}><Network size={15} /> Architecture</button>
          <button className="icon-button" aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`} aria-pressed={theme === "light"} onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
          <button className="icon-button" aria-label={snapshot.mission.truth_mode === "NATIVE" ? "Reload native mission" : "Reset exact fixture"} onClick={() => void reset()}><RefreshCcw size={16} /></button>
        </div>
      </header>
      <div className="safety-banner"><ShieldCheck size={15} /><strong>Deterministic authority</strong><span>{notification ? "Marked synthetic operator notice delivered; no real cargo instruction sent." : "Agents propose. Humans approve. Partners issue receipts. External notices are disabled by default."}</span><span className="banner-ref">case v{snapshot.mission.version}</span></div>
      {error && <div className="error-banner"><AlertOctagon size={16} /> Action failed closed: {error}</div>}
      <nav className="workspace-tabs" aria-label="Mission workspace">
        <div className="tab-list">{tabs.map((item) => {
          const count = item.id === "evidence" ? snapshot.evidence.length : item.id === "documents" ? snapshot.artifacts.length : item.id === "receipts" ? snapshot.receipts.length : item.id === "models" ? (snapshot.model_receipts?.length ?? 0) : item.id === "activity" ? snapshot.events.length : null;
          return <button key={item.id} className={tab === item.id ? "active" : ""} aria-current={tab === item.id ? "page" : undefined} onClick={() => setTab(item.id)}>{item.label}{count !== null && <span>{count}</span>}</button>;
        })}</div>
        <div className={`tab-state ${released ? "released" : "held"}`}>{released ? <PackageCheck size={15} /> : <LockKeyhole size={15} />} Physical release: <strong>{released ? "RELEASED" : "HELD"}</strong></div>
      </nav>
      <main className="workspace-grid">
        <section className="workspace-stage">
          {tab === "mission" && <MissionPanel snapshot={snapshot} />}
          {tab === "authority" && <AuthorityMapPanel snapshot={snapshot} />}
          {tab === "evidence" && <EvidencePanel snapshot={snapshot} selected={selectedEvidence} onSelect={setSelectedEvidenceId} />}
          {tab === "documents" && <DocumentsPanel snapshot={snapshot} selected={selectedArtifact} onSelect={setSelectedArtifactId} />}
          {tab === "receipts" && <ReceiptsPanel snapshot={snapshot} onInspect={setReceipt} />}
          {tab === "models" && <ModelReviewPanel snapshot={snapshot} busy={busy} onGenerateReplay={generateReplay} />}
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

function mapState(complete: boolean, active = false): MapState {
  if (complete) return "complete";
  return active ? "active" : "idle";
}

function verifiedReceiptCount(
  snapshot: MissionSnapshot,
  kinds: readonly ReceiptKind[],
): number {
  const verified = new Set(
    snapshot.receipts
      .filter((receipt) => receipt.verified)
      .map((receipt) => receipt.kind),
  );
  return kinds.filter((kind) => verified.has(kind)).length;
}

function AuthorityMapPanel({ snapshot }: { snapshot: MissionSnapshot }) {
  const metric = missionFrictionMetric(snapshot);
  const latestRun = snapshot.runs.at(-1);
  const evidenceResolved = snapshot.mission.release_state !== "EVIDENCE_BLOCKED";
  const ownerAttested = snapshot.approvals.some(
    (approval) => approval.kind === "OWNER_BOND",
  );
  const securityKinds = [
    "INSURER_GUARANTEE",
    "ADJUSTER_REJECTION",
    "ADJUSTER_ACCEPTANCE",
  ] as const satisfies readonly ReceiptKind[];
  const releaseKinds = [
    "ADJUSTER_ACCEPTANCE",
    "CARRIER_RELEASE_ORDER",
    "CARRIER_RELEASE_READBACK",
  ] as const satisfies readonly ReceiptKind[];
  const securityReceipts = verifiedReceiptCount(snapshot, securityKinds);
  const releaseReceipts = verifiedReceiptCount(snapshot, releaseKinds);
  const released = snapshot.mission.release_state === "RELEASED";
  const notified = metric.operatorNotifications === 1;
  const recoveryState: MapState = latestRun?.status === "FAILED"
    ? "blocked"
    : latestRun?.status === "COMPLETED"
      ? "complete"
      : latestRun
        ? "active"
        : "idle";

  return <div className="detail-panel authority-map-panel">
    <PanelHeading eyebrow="Live control topology" title="Authority moves. Agents do not own it." detail="This is not a route map. Every lit edge comes from durable mission state, a scoped worker boundary, a human attestation, or a verified issuer receipt." />
    <section className="authority-map" aria-label="Cargo release authority map">
      <header className="map-legend">
        <span><i className="edge-swatch read" /> Read-only scope</span>
        <span><i className="edge-swatch advance" /> Human or bounded advance</span>
        <span><i className="edge-swatch verified" /> Verified authority</span>
        <code>release_authority=false for every model and worker</code>
      </header>
      <div className="map-lanes">
        <section className="map-lane intake-lane">
          <div className="lane-heading"><span>01</span><div><small>Authenticated intake</small><strong>Open one mission</strong></div></div>
          <MapNode icon={<Route />} state="complete" kicker="EVENT" title="Pub/Sub → Eventarc" detail={`${snapshot.mission.case_ref} · idempotent casualty envelope`} badge={<TruthBadge mode={snapshot.mission.truth_mode} />} />
          <MapNode icon={<ShieldCheck />} state="active" kicker="WEB" title="Server relay" detail="Exact method/path allowlist · server-bound operator" badge={<span className="scope-badge">ALLOWLIST</span>} />
        </section>

        <section className="map-lane agent-lane">
          <div className="lane-heading"><span>02</span><div><small>ADK coordination plane</small><strong>Delegate by tool scope</strong></div></div>
          <MapNode icon={<Network />} state={latestRun ? "active" : "idle"} kicker="GEMINI 3.5+ · ADK" title="Mission Coordinator" detail="Four transfers · one lease-protected POST" badge={<span className="scope-badge advance">POST ×1</span>} />
          <div className="worker-grid">
            <MapNode compact icon={<Layers3 />} state={mapState(evidenceResolved, snapshot.evidence.length > 0)} kicker="READ ONLY" title="Evidence worker" detail={`${snapshot.evidence.filter((item) => item.status === "VERIFIED").length} verified · ${snapshot.evidence.filter((item) => item.status === "QUARANTINED").length} quarantined`} />
            <MapNode compact icon={<FileCheck2 />} state={mapState(securityReceipts === 3, ownerAttested)} kicker="READ ONLY" title="Security worker" detail={`${ownerAttested ? 1 : 0} human · ${securityReceipts}/3 partner`} />
            <MapNode compact icon={<KeyRound />} state={mapState(releaseReceipts === 3, securityReceipts > 0)} kicker="READ ONLY" title="Authority worker" detail={`${releaseReceipts}/3 release-key receipts`} />
            <MapNode compact icon={<RefreshCcw />} state={recoveryState} kicker="READ ONLY" title="Recovery worker" detail={latestRun ? `${latestRun.status.replace("_", " ")} · ${latestRun.steps} bounded steps` : "No run to classify yet"} />
          </div>
        </section>

        <section className="map-lane authority-lane">
          <div className="lane-heading"><span>03</span><div><small>Deterministic authority</small><strong>One state writer</strong></div></div>
          <MapNode icon={<Boxes />} state={released ? "complete" : "active"} kicker="CLOUD RUN + CLOUD SQL" title="Receipt saga controller" detail={`${snapshot.mission.release_state.replaceAll("_", " ")} · version ${snapshot.mission.version} · adjustment ${snapshot.mission.adjustment_state}`} badge={<span className="scope-badge authority">SOLE WRITER</span>} />
          <MapNode icon={<UsersRound />} state={mapState(ownerAttested, snapshot.artifacts.length > 0)} kicker="HUMAN KEY" title="Owner bond attestation" detail={ownerAttested ? snapshot.approvals[0]?.actor ?? "Attested" : "Required before partner security"} />
          <MapNode icon={<KeyRound />} state={mapState(releaseReceipts === 3, snapshot.receipts.length > 0)} kicker="ISSUER-BOUND" title="Independent partner keys" detail={`${snapshot.receipts.filter((item) => item.verified).length} verified receipts · insurer / adjuster / carrier`} />
        </section>

        <section className="map-lane consequence-lane">
          <div className="lane-heading"><span>04</span><div><small>Observable consequence</small><strong>Release, then notify</strong></div></div>
          <MapNode icon={released ? <PackageCheck /> : <LockKeyhole />} state={mapState(released, releaseReceipts > 0)} kicker="PHYSICAL CARGO" title={released ? "Container released" : "Container held"} detail={`${snapshot.mission.container_ref} · adjustment remains ${snapshot.mission.adjustment_state}`} badge={<span className={`consequence-badge ${released ? "released" : "held"}`}>{released ? "RELEASED" : "HELD"}</span>} />
          <MapNode icon={<Send />} state={mapState(notified, released)} kicker="POST-READ-BACK" title="Marked Slack proof" detail={notified ? snapshot.notifications?.at(-1)?.endpoint_label ?? "Operator endpoint" : released ? "Endpoint disabled or delivery not requested" : "Cannot run before release"} />
        </section>
      </div>
    </section>
    <section className={`friction-proof ${metric.autonomousActions === 8 ? "complete" : ""}`} data-testid="friction-metric">
      <div className="metric-ratio"><span data-testid="human-attestations">{metric.humanAttestations}</span><ArrowRight size={21} /><strong>{metric.autonomousActions}<small> / 8</small></strong></div>
      <div className="metric-copy"><span className="eyebrow">Reproducible friction metric</span><h2>One human attestation, eight downstream actions</h2><p>A capability count—not an industry savings claim. Duplicate receipts, events, and notices cannot inflate it.</p></div>
      <div className="metric-breakdown"><span>Signed receipts <b>{metric.partnerReceipts}/5</b></span><span>Submit <b>{metric.securitySubmissions}/1</b></span><span>Correct <b>{metric.securityCorrections}/1</b></span><span>Marked notice <b>{metric.operatorNotifications}/1</b></span></div>
    </section>
  </div>;
}

function MapNode({ icon, state, kicker, title, detail, badge, compact = false }: { icon: ReactNode; state: MapState; kicker: string; title: string; detail: string; badge?: ReactNode; compact?: boolean }) {
  return <article className={`map-node state-${state} ${compact ? "compact" : ""}`}>
    <span className="map-node-icon">{icon}</span>
    <div><small>{kicker}</small><strong>{title}</strong><p>{detail}</p></div>
    {badge && <span className="map-node-badge">{badge}</span>}
  </article>;
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

interface CriticFindingView {
  finding_code: string;
  severity: string;
  finding: string;
  evidence_refs: string[];
  operator_action: string;
  uncertainty: string;
}

interface RetrievedCaseView {
  rank: number;
  case_id: string;
  title: string;
  reviewed_outcome: string;
  key_difference: string;
}

function criticFindings(result: Record<string, unknown>): CriticFindingView[] {
  if (!Array.isArray(result.findings)) return [];
  return result.findings.flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const item = value as Record<string, unknown>;
    return [{
      finding_code: String(item.finding_code ?? "UNSPECIFIED"),
      severity: String(item.severity ?? "ADVISORY"),
      finding: String(item.finding ?? "No finding text returned."),
      evidence_refs: Array.isArray(item.evidence_refs) ? item.evidence_refs.map(String) : [],
      operator_action: String(item.operator_action ?? "Inspect the source packet."),
      uncertainty: String(item.uncertainty ?? "Model output requires human review."),
    }];
  });
}

function retrievedCases(result: Record<string, unknown>): RetrievedCaseView[] {
  if (!Array.isArray(result.top_cases)) return [];
  return result.top_cases.flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const item = value as Record<string, unknown>;
    return [{
      rank: Number(item.rank ?? 0),
      case_id: String(item.case_id ?? "unknown-case"),
      title: String(item.title ?? "Reviewed synthetic case"),
      reviewed_outcome: String(item.reviewed_outcome ?? "No reviewed outcome supplied."),
      key_difference: String(item.key_difference ?? "Compare the source facts directly."),
    }];
  });
}

function ModelReviewPanel({ snapshot, busy, onGenerateReplay }: { snapshot: MissionSnapshot; busy: boolean; onGenerateReplay: () => Promise<void> }) {
  const gemma = snapshot.model_receipts?.filter((item) => item.kind === "GEMMA_RELEASE_CRITIC").at(-1);
  const retrieval = snapshot.model_receipts?.filter((item) => item.kind === "GEMINI_EMBEDDING_RETRIEVAL").at(-1);
  const veo = snapshot.model_receipts?.filter((item) => item.kind === "VEO_POST_RELEASE_REPLAY").at(-1);
  if (!gemma && !retrieval && !veo && snapshot.mission.release_state !== "RELEASED") return <div className="detail-panel"><PanelHeading eyebrow="Independent model review" title="Advisory checks stay outside authority" detail="Optional model checks run only on sanitized packets. Disabled or unavailable checks never approve, block, or release cargo." /><div className="large-empty"><BrainCircuit size={34} /><h2>No managed advisory receipt yet</h2><p>Start the mission to reconcile evidence and request the proposal-only checks.</p></div></div>;
  const findings = gemma ? criticFindings(gemma.result) : [];
  const summary = gemma ? String(gemma.result.summary ?? (gemma.status === "DEGRADED" ? "The critic is unavailable; the deterministic workflow is unaffected." : "Review completed.")) : "";
  const examples = retrieval ? retrievedCases(retrieval.result) : [];
  return <div className="detail-panel model-review-panel"><PanelHeading eyebrow="Independent model review" title="Second opinion, zero authority" detail="Gemma inspects a sanitized packet. Embedding 2 ranks reviewed examples. Veo can visualize the completed workflow only after release. None owns a release key." />
    {gemma && <article className={`model-receipt status-${gemma.status.toLowerCase()}`}>
      <div className="model-receipt-head"><span className="model-icon"><BrainCircuit size={20} /></span><div><small>Proposal checklist receipt</small><strong>{gemma.model_id}</strong><code>{gemma.location} · {gemma.request_ref}</code></div><TruthBadge mode={gemma.truth_mode} /></div>
      <div className="authority-zero"><ShieldCheck size={16} /><span><strong>release_authority=false</strong> · no tools · no state transition · no partner contact</span></div>
      <p className="model-summary">{summary}</p>
      {gemma.status === "DEGRADED" ? <div className="model-degraded"><AlertOctagon size={17} /><div><strong>Advisory unavailable</strong><p>{String(gemma.result.error_type ?? "Managed model error")} · release_affected=false · explicit retry available through the API.</p></div></div> : <div className="critic-findings">{findings.map((finding) => <article key={`${finding.finding_code}-${finding.evidence_refs.join("-")}`}><header><span>{finding.severity}</span><code>{finding.finding_code}</code></header><strong>{finding.finding}</strong><p><b>Operator:</b> {finding.operator_action}</p><p><b>Uncertainty:</b> {finding.uncertainty}</p><small>{finding.evidence_refs.join(" · ") || "packet-level finding"}</small></article>)}</div>}
      <div className="model-digests"><span>Input <code>sha256:{gemma.input_digest}</code></span><span>Output <code>sha256:{gemma.output_digest}</code></span></div>
    </article>}
    {retrieval && <article className={`model-receipt retrieval-receipt status-${retrieval.status.toLowerCase()}`}>
      <div className="model-receipt-head"><span className="model-icon retrieval-icon"><Layers3 size={20} /></span><div><small>Reviewed-case ranking receipt</small><strong>{retrieval.model_id}</strong><code>{retrieval.location} · {retrieval.request_ref}</code></div><TruthBadge mode={retrieval.truth_mode} /></div>
      <div className="authority-zero"><ShieldCheck size={16} /><span><strong>release_authority=false</strong> · rank only · no threshold · no state branch</span></div>
      <p className="retrieval-label">Nearest reviewed synthetic examples—not precedent or recommendation</p>
      {retrieval.status === "DEGRADED" ? <div className="model-degraded"><AlertOctagon size={17} /><div><strong>Retrieval unavailable</strong><p>{String(retrieval.result.error_type ?? "Managed embedding error")} · release_affected=false · explicit retry available through the API.</p></div></div> : <div className="retrieval-cases">{examples.map((item) => <article key={item.case_id}><span className="retrieval-rank">#{item.rank}</span><div><code>{item.case_id}</code><strong>{item.title}</strong><p>{item.reviewed_outcome}</p><small><b>Different here:</b> {item.key_difference}</small></div></article>)}</div>}
      <div className="retrieval-meta"><span>{String(retrieval.result.dimensions ?? "—")} dimensions</span><span>{String(retrieval.result.corpus_size ?? "—")} reviewed cases</span><span>scores withheld</span></div>
      <div className="model-digests"><span>Input <code>sha256:{retrieval.input_digest}</code></span><span>Output <code>sha256:{retrieval.output_digest}</code></span></div>
    </article>}
    {!veo && snapshot.mission.release_state === "RELEASED" && <article className="replay-ready">
      <span className="model-icon veo-icon"><Film size={20} /></span><div><small>Optional post-release artifact</small><strong>Turn the completed receipt chain into a 4-second synthetic training replay</strong><p>The prompt contains no documents, identifiers, people, brands, or operational instructions. Generation cannot change the already committed release.</p></div><button data-testid="generate-replay" className="primary-button" disabled={busy} onClick={() => void onGenerateReplay()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Film size={16} />}{busy ? "Generating…" : "Generate training replay"}</button>
    </article>}
    {veo && <article className={`model-receipt veo-receipt status-${veo.status.toLowerCase()}`}>
      <div className="model-receipt-head"><span className="model-icon veo-icon"><Film size={20} /></span><div><small>Post-release media receipt</small><strong>{veo.model_id}</strong><code>{veo.location} · {veo.request_ref}</code></div><TruthBadge mode={veo.truth_mode} /></div>
      <div className="authority-zero"><ShieldCheck size={16} /><span><strong>release_authority=false</strong> · generated after release · training only · not evidence</span></div>
      <p className="replay-label">SYNTHETIC REPLAY — NOT EVIDENCE — GENERATED AFTER RELEASE</p>
      {veo.status === "DEGRADED" ? <div className="model-degraded"><AlertOctagon size={17} /><div><strong>Replay unavailable</strong><p>{String(veo.result.error_type ?? "Managed media error")} · release_affected=false · physical release stays committed.</p></div></div> : <div className="replay-media">{veo.truth_mode === "NATIVE" ? <video controls playsInline preload="metadata" aria-label="Synthetic post-release training replay"><source src={veoReplayMediaUrl(snapshot.mission.id)} type="video/mp4" /></video> : <div className="replay-stage" role="img" aria-label="Synthetic post-release replay fixture"><span className="replay-pulse one" /><span className="replay-pulse two" /><span className="replay-pulse three" /><div className="replay-container"><span /><span /><span /><span /></div></div>}</div>}
      <div className="retrieval-meta"><span>{String(veo.result.duration_seconds ?? "—")} seconds</span><span>{String(veo.result.resolution ?? "—")}</span><span>{String(veo.result.safety_filtered_count ?? "—")} safety filtered</span><span>audio off</span></div>
      <code className="asset-ref">{String(veo.result.asset_uri ?? "No asset created")}</code>
      <div className="model-digests"><span>Asset <code>sha256:{String(veo.result.asset_sha256 ?? "unavailable")}</code></span><span>Receipt <code>sha256:{veo.output_digest}</code></span></div>
    </article>}
  </div>;
}

function ActivityPanel({ snapshot }: { snapshot: MissionSnapshot }) {
  const notification = snapshot.notifications?.at(-1);
  return <div className="detail-panel activity-panel"><PanelHeading eyebrow="Hash-linked activity" title="Every change has a cause" detail="The mission is reconstructable from append-only events, actor identities, and trace spans." />
    {notification && <article className="notification-proof"><span className="notification-proof-icon"><Send size={18} /></span><div><small>Synthetic outbound proof · non-authoritative</small><strong>{notification.endpoint_label}</strong><p>Delivered only after verified carrier read-back. No real cargo instruction was sent.</p><code>{notification.provider_ref} · sha256:{notification.payload_digest.slice(0, 16)}</code></div><TruthBadge mode={notification.truth_mode ?? "ADAPTER"} /></article>}
    <MissionSpine snapshot={snapshot} />
  </div>;
}

function PanelHeading({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return <div className="panel-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{detail}</p></div>;
}

function DecisionRail({ snapshot, nextAction, busy, onAdvance, onNavigate }: { snapshot: MissionSnapshot; nextAction: NextAction | null; busy: boolean; onAdvance: () => Promise<void>; onNavigate: (tab: WorkspaceTab) => void }) {
  const adjuster = hasReceipt(snapshot, "ADJUSTER_ACCEPTANCE");
  const carrier = hasReceipt(snapshot, "CARRIER_RELEASE_READBACK");
  const notification = snapshot.notifications?.at(-1);
  const latestRun = snapshot.runs.at(-1);
  return <aside className="decision-rail" aria-labelledby="action-title">
    <div className="rail-heading"><span>Next decision</span><strong id="action-title">What needs you now</strong></div>
    {nextAction ? <div className={`next-action tone-${nextAction.tone}`}><span className="action-eyebrow">{nextAction.eyebrow}</span><h2>{nextAction.title}</h2><p>{nextAction.detail}</p><button data-testid="primary-action" className="primary-button" disabled={busy} onClick={() => void onAdvance()}>{busy ? <LoaderCircle className="spin" size={17} /> : <CircleDot size={17} />}{busy ? "Recording…" : nextAction.button}{!busy && <ArrowRight size={16} />}</button></div> : <div className="release-complete"><BadgeCheck size={25} /><span className="action-eyebrow">No release action open</span><h2>Carrier read-back verified</h2><p>{notification ? `Marked synthetic notice delivered to ${notification.endpoint_label}.` : "The container is released. External notices remain disabled until an operator endpoint is configured."} Adjustment monitoring remains active and separate.</p></div>}
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
      <button onClick={() => onNavigate("models")}><span><BrainCircuit size={16} /><strong>AI checks</strong></span><small>{snapshot.model_receipts?.length ?? 0} advisory</small><ChevronRight size={15} /></button>
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
  const partnerTrace = snapshot.traces.find((item) => item.operation === "verify_partner_receipt");
  const partnerMode: TruthMode = partnerTrace?.truth_mode ?? "FIXTURE";
  const observabilityMode: TruthMode = snapshot.mission.truth_mode === "NATIVE" && snapshot.traces.length > 0 ? "NATIVE" : "ADAPTER";
  const controllerMode: TruthMode = snapshot.mission.truth_mode === "NATIVE" ? "NATIVE" : "FIXTURE";
  return <div className="overlay" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><aside className="side-drawer" role="dialog" aria-modal="true" aria-label={drawer === "fleet" ? "Agent fleet" : "Architecture"}>
    <div className="drawer-header"><div><span className="eyebrow">Inspect, do not trust logos</span><h2>{drawer === "fleet" ? "Agents versus deterministic actors" : "Transition ownership"}</h2></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
    {drawer === "fleet" ? <div className="fleet-list">{fleet.map((item, index) => { const trace = snapshot.traces.find((candidate) => candidate.agent.includes(item.version.split("@")[0])); return <article key={item.version}><span className="fleet-number">{String(index + 1).padStart(2, "0")}</span><div><span className="roster-kind">{item.kind}</span><strong>{item.name}</strong><code>{item.version}</code><p>{item.detail}</p></div><TruthBadge mode={(trace?.truth_mode ?? item.fallback) as TruthMode} /></article>; })}</div> : <div className="architecture-list">{[
      ["Eventarc intake", "Authenticated CloudEvent opens one idempotent mission", snapshot.mission.truth_mode],
      ["Server relay", "Fail-closed route/method allowlist; web identity injects the operator actor", "ADAPTER"],
      ["Agent Runtime + ADK", "Coordinator plus four scoped workers; candidate tree awaits managed rollout proof", "ADAPTER"],
      ["Cloud SQL authority", "PostgreSQL receipt saga is the sole managed state writer", controllerMode],
      ["Memory Bank", "Reviewed release context only; never authoritative state", memoryMode],
      ["Model Armor", "Managed cargo-release-policy template passed a retained injection probe", "NATIVE"],
      ["Agent Registry", "Managed coordinator and exact partner endpoints are registered", "NATIVE"],
      ["Agent Identity + Gateway", "Fail-closed IAP authorization governs the exact Registry allowlist", "NATIVE"],
      ["Agent Observability", "Mission truth, trace spans, request IDs, and Cloud trace context", observabilityMode],
      ["Partner Cloud Run", "Independent insurer, adjuster, and carrier identities return signed fixtures", partnerMode],
      ["Operator notification", "Allowlisted Slack webhook; marked synthetic and post-release only", snapshot.notifications?.at(-1)?.truth_mode ?? "FIXTURE"],
      ["Gemma 4 critic", "Sanitized proposal review; durable receipt, no tools or authority", snapshot.model_receipts?.find((item) => item.kind === "GEMMA_RELEASE_CRITIC")?.truth_mode ?? "ADAPTER"],
      ["Embedding 2 retrieval", "Reviewed synthetic top-k context; rank only, no threshold or precedent", snapshot.model_receipts?.find((item) => item.kind === "GEMINI_EMBEDDING_RETRIEVAL")?.truth_mode ?? "ADAPTER"],
      ["Veo 3.1 Fast replay", "Post-release training media; private asset, never evidence", snapshot.model_receipts?.find((item) => item.kind === "VEO_POST_RELEASE_REPLAY")?.truth_mode ?? "ADAPTER"],
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
