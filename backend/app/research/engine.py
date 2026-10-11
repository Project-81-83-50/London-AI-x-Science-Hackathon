import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .agents import REVIEWER, WRITER, AgentSession, coordinate, evidence_selection, sample_views, warning_evidence
from .checks import PLACEHOLDER, render, validate
from .config import OutputError, ResearchError
from .facts import decode
from .models import Draft, Question, Report, Review, Settings
from .retrieval import research
from .sources import ResearchSources, Transport
from .store import INDEX_VERSION, Store


def implementation_version() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def review_claims(document, draft, sources, grades, gaps, session) -> Review:
    claims = [claim for explanation in draft.explanations for claim in explanation.claims]
    selected = evidence_selection(document, {fid for claim in claims for fid in PLACEHOLDER.findall(claim.text)})
    claim_ids = {claim.id for claim in claims}
    gap_evidence = {f"G{index}": gap for index, gap in enumerate(gaps)}
    evidence_ids = selected | set(sources) | set(warning_evidence(document)) | set(gap_evidence)
    payload = {
        "samples": sample_views(document, selected),
        "draft": draft.model_dump(),
        "sources": [source.model_dump() for source in sources.values()],
        "retrieval_grades": [g.model_dump() for g in grades if g.verdict == "supported"],
        "research_gaps": gap_evidence,
        "allowed_evidence_ids": sorted(evidence_ids),
    }
    for _ in range(2):
        try:
            review = session.ask("grounding_reviewer", REVIEWER, payload, Review, reviewer=True)
        except OutputError as exc:
            payload["review_feedback"] = str(exc)
            continue
        invalid = [
            finding.claim_id
            for finding in review.findings
            if finding.claim_id not in claim_ids
            or not set(finding.evidence_ids) <= evidence_ids
            or finding.category != "style"
            and not finding.evidence_ids
        ]
        if not invalid:
            return review
        payload["previous_review"] = review.model_dump()
        payload["review_feedback"] = (
            "Repair the review, not the report. Findings must name existing claims and allowed evidence IDs. "
            "Every blocking finding needs a specific fact, source or warning ID. Stylistic preferences are advisory. "
            f"Invalid findings: {', '.join(invalid)}"
        )
        session.trace.append({"stage": "review_contract", "invalid_claims": invalid})
    raise ResearchError(
        "review_failed", "The reviewer could not produce a valid evidence-scoped assessment; no report was published."
    )


def explain(
    document: str | dict | list,
    store: Store,
    settings: Settings,
    env: dict[str, str],
    client: Any = None,
    provider: ResearchSources | None = None,
    progress: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    force: bool = False,
    references: list[dict] | None = None,
) -> Report:
    session = AgentSession(settings, env, client, cancelled)

    def stage(name: str) -> None:
        session.check()
        if progress:
            progress(name)

    stage("decoding")
    decoded = decode(document)
    from .baselines import attach_profiles

    attach_profiles(decoded, references or [])
    reference_version = hashlib.sha256(
        json.dumps(references or [], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    provider = provider or ResearchSources(Transport(settings.max_web_requests, session.expires, settings.timeout), env)

    def key() -> str:
        payload = {
            "facts": decoded.input_hash,
            "registry": decoded.registry_version,
            "corpus": store.version(),
            "references": reference_version,
            "implementation": implementation_version(),
            "settings": settings.model_dump(),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    if settings.cache_ttl and not force:
        cached = store.cached(key(), settings.cache_ttl)
        if cached:
            try:
                result = Report.model_validate(cached["result"])
                draft = Draft.model_validate(cached["draft"])
                from .models import Grade

                grades = [Grade.model_validate(item) for item in result.audit["retrieval_grades"]]
                fresh = all(
                    0 <= time.time() - source.checked_at <= settings.source_max_age
                    for source in result.sources.values()
                )
                expected_explanations, expected_claims, _ = render(draft, decoded)
                consistent = result.explanations == expected_explanations and result.claims == expected_claims
                if (
                    fresh
                    and consistent
                    and not validate(draft, decoded, result.sources, grades, result.audit["source_scopes"])
                ):
                    result.facts = {fact.id: fact for sample in decoded.samples for fact in sample.facts}
                    stage("cache_hit")
                    result.audit.update(
                        cache_hit=True,
                        review_reused=True,
                        calls_this_run=0,
                        elapsed_seconds=round(time.monotonic() - session.started, 3),
                    )
                    return result
            except (ValueError, KeyError, TypeError):
                session.trace.append({"stage": "cache", "result": "failed_revalidation"})
    stage("analyzing")
    plan = coordinate(decoded, session)
    selected = set(plan.selected_facts)
    for sample in decoded.samples:
        for comparison in sample.comparisons:
            selected.update([comparison.value_id, *comparison.reference_ids.values()])
        for fact in sample.facts:
            if fact.used_by_model or fact.pointer.endswith("positive_share_of_total_evidence_pct"):
                selected.add(fact.id)
        opposites = {
            fact.pointer.replace("/positive/", "/negative/")
            for fact in sample.facts
            if fact.id in selected and "/positive/" in fact.pointer
        }
        selected.update(f.id for f in sample.facts if f.pointer in opposites)
    stage("searching_library")
    sources, grades, gaps, scopes = research(plan.questions, decoded, store, provider, session, stage)
    feedback: list[Any] = []
    draft = None
    approved = False
    for attempt in range(settings.draft_attempts):
        stage("writing")
        try:
            draft = session.ask(
                "materials_writer",
                WRITER,
                {
                    "samples": sample_views(decoded, selected),
                    "accepted_sources": [s.model_dump() for s in sources.values()],
                    "source_scopes": scopes,
                    "retrieval_grades": [g.model_dump() for g in grades if g.verdict == "supported"],
                    "research_gaps": gaps,
                    "repair_feedback": feedback,
                    "previous_draft": draft.model_dump() if draft is not None else None,
                },
                Draft,
            )
        except OutputError as exc:
            feedback = [str(exc)]
            session.trace.append({"stage": "draft", "attempt": attempt + 1, "error": exc.code})
            continue
        stage("validating")
        errors = validate(draft, decoded, sources, grades, scopes)
        if errors:
            session.trace.append({"stage": "validation", "attempt": attempt + 1, "errors": errors})
            feedback = errors
            continue
        stage("reviewing")
        review = review_claims(decoded, draft, sources, grades, gaps, session)
        blocking = [finding for finding in review.findings if finding.category != "style"]
        session.trace.append(
            {"stage": "review", "attempt": attempt + 1, "findings": [f.model_dump() for f in review.findings]}
        )
        if not blocking:
            approved = True
            break
        feedback = [f.model_dump() for f in blocking]
        if any(f.action == "retrieve" for f in blocking) and attempt + 1 < settings.draft_attempts:
            extra_questions = [
                Question(concept=q.concept, sample_ids=q.sample_ids, focus="counter_evidence") for q in plan.questions
            ]
            extra, extra_grades, extra_gaps, extra_scopes = research(
                extra_questions, decoded, store, provider, session, stage
            )
            sources.update(extra)
            grades.extend(extra_grades)
            gaps.extend(extra_gaps)
            for sid, owners in extra_scopes.items():
                scopes[sid] = sorted(set(scopes.get(sid, [])) | set(owners))
    if not approved:
        raise ResearchError(
            "validation_failed",
            "The bounded explanation/review checks did not pass. No partial or template report was published.",
        )
    stage("rendering")
    explanations, claims, markdown = render(draft, decoded)
    used_sources = {citation["source_id"] for claim in claims for citation in claim["citations"]}
    visible_sources = {sid: source for sid, source in sources.items() if sid in used_sources}
    if visible_sources:
        markdown += "\n\n## Research sources\n" + "\n".join(
            f"- {s.title} — {s.location}; {s.url}" for s in visible_sources.values()
        )
    result = Report(
        research_status="incomplete" if gaps else "supported" if visible_sources else "not_needed",
        explanations=explanations,
        claims=claims,
        facts={f.id: f for sample in decoded.samples for f in sample.facts},
        sources=visible_sources,
        markdown=markdown,
        audit={
            "input_hash": decoded.input_hash,
            "registry_version": decoded.registry_version,
            "reference_version": reference_version,
            "field_inventory": decoded.inventory,
            "source_scopes": scopes,
            "retrieval_grades": [g.model_dump() for g in grades],
            "research_gaps": gaps,
            "corpus_version": store.version(),
            "index": INDEX_VERSION,
            "index_note": "BM25 plus local TF-IDF/latent semantic vectors; relevance still requires evaluation.",
            "validator_passed": True,
            "reviewer_passed": True,
            "review_findings": [f.model_dump() for f in review.findings],
            "cache_hit": False,
            "review_reused": False,
            "calls_this_run": len(session.calls),
            "calls": session.calls,
            "trace": session.trace,
            "source_warnings": provider.warnings,
            "network_requests": provider.transport.count,
            "elapsed_seconds": round(time.monotonic() - session.started, 3),
        },
    )
    if settings.cache_ttl:
        store.cache(key(), {"draft": draft.model_dump(), "result": result.model_dump()})
    stage("done")
    return result
