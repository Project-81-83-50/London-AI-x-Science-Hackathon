from .agents import EVALUATOR, LIBRARIAN, AgentSession
from .config import OutputError
from .facts import CONCEPTS
from .models import Document, Grade, Grades, Question, SearchPlan, Source
from .sources import PUBLIC_QUERIES, ResearchSources, SourceError
from .store import Store


def normalized(text: str) -> str:
    return " ".join(text.split())


def grade(question: Question, sources: list[Source], document: Document, session: AgentSession) -> list[Grade]:
    if not sources:
        return []
    result = session.ask(
        "retrieval_evaluator",
        EVALUATOR,
        {
            "question": question.model_dump(),
            "claim_scope": "general_scientific_principle_not_sample_specific_effect",
            "desired_use": "Explain the meaning and limits of a measured feature, not validate its numerical value or predict this sample's performance.",
            "public_query": CONCEPTS[question.concept],
            "sample_methods": [
                {
                    "sample_id": s.sample_id,
                    "material": "graphite/SiOx anode",
                    "dimensionality": "2-D SEM cross-section",
                    "preparation_and_cycling_state": "not established",
                    "methods": sorted({f.method for f in s.facts if f.method}),
                    "measured_features": [
                        {
                            "label": f.label,
                            "method": f.method,
                            "description": f.description,
                            "denominator": f.denominator,
                        }
                        for f in s.facts
                        if f.role == "observation" and f.used_by_model
                    ],
                    "warnings": s.warnings,
                }
                for s in document.samples
                if s.sample_id in question.sample_ids
            ],
            "sources": [s.model_dump() for s in sources],
        },
        Grades,
        reviewer=True,
    )
    by_id = {source.id: source for source in sources}
    ids = [item.source_id for item in result.items]
    if len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise OutputError("source_scope", "Retrieval evaluator must grade exactly the supplied passages.")
    for item in result.items:
        source = by_id[item.source_id]
        if item.verdict == "supported":
            if (
                not item.relevant
                or not item.applicable
                or len(item.quote.strip()) < 25
                or normalized(item.quote) not in normalized(source.text)
            ):
                item.verdict, item.reason = "unsupported", "Exact quote, relevance or applicability checks failed."
            elif (
                source.access in {"seed", "abstract"}
                or source.updates == "notice"
                or source.doi
                and source.updates != "none_found"
            ):
                item.verdict, item.reason = (
                    "ambiguous",
                    "The original supporting full text or source-status review is missing.",
                )
    return result.items


def research(
    questions: list[Question],
    document: Document,
    store: Store,
    provider: ResearchSources,
    session: AgentSession,
    progress,
) -> tuple[dict, list, list, dict]:
    accepted: dict[str, Source] = {}
    grades: list[Grade] = []
    gaps: list[dict] = []
    scopes: dict[str, set[str]] = {}
    reserve = min(4, session.settings.draft_attempts * 2, session.settings.max_calls // 2)
    candidate_ids = getattr(provider, "candidate_ids", set())
    provider.candidate_ids = candidate_ids
    for question_index, question in enumerate(questions):
        remaining_questions = len(questions) - question_index
        remaining_documents = max(0, session.settings.max_documents - len(provider.fetched))
        question_document_limit = (
            len(provider.fetched) + (remaining_documents + remaining_questions - 1) // remaining_questions
        )
        focus = question.focus
        evaluated_ids: set[str] = set()
        resolved = False
        for round_index in range(session.settings.retrieval_rounds + 1):
            session.check()
            if len(session.calls) >= session.settings.max_calls - reserve:
                break
            progress("evaluating_sources")
            query = PUBLIC_QUERIES[question.concept][("meaning", "limitations", "counter_evidence").index(focus)]
            passages = store.search(
                query, candidate_ids, session.settings.source_max_age, originals_only=True, exclude_ids=evaluated_ids
            )
            if len(passages) < 6:
                passages += store.search(
                    query,
                    candidate_ids,
                    session.settings.source_max_age,
                    limit=6 - len(passages),
                    exclude_ids=evaluated_ids | {p.id for p in passages},
                )
            try:
                evaluated = grade(question, passages, document, session)
            except OutputError as exc:
                session.trace.append({"stage": "retrieval_evaluation", "error": exc.code})
                evaluated = []
            grades.extend(evaluated)
            evaluated_ids.update(item.source_id for item in evaluated)
            supported = {g.source_id for g in evaluated if g.verdict == "supported"}
            sufficient = any(g.source_id in supported and g.answers_question for g in evaluated)
            conflict = any(g.conflict for g in evaluated)
            for passage in passages:
                if passage.id in supported:
                    accepted[passage.id] = passage
                    scopes.setdefault(passage.id, set()).update(question.sample_ids)
            route = (
                "supported"
                if sufficient and not conflict
                else "ambiguous"
                if supported or any(g.verdict == "ambiguous" for g in evaluated)
                else "unsupported"
            )
            session.trace.append(
                {
                    "stage": "corrective_retrieval",
                    "question": question.model_dump(),
                    "round": round_index,
                    "route": route,
                    "sources": [p.id for p in passages],
                    "accepted": sorted(supported),
                }
            )
            if route == "supported":
                resolved = True
                break
            if (
                not session.settings.online
                or round_index == session.settings.retrieval_rounds
                or len(provider.fetched) >= question_document_limit
                or len(session.calls) + 2 > session.settings.max_calls - reserve
            ):
                break
            progress("searching_online")
            try:
                strategy = session.ask(
                    "research_librarian",
                    LIBRARIAN,
                    {"question": question.model_dump(), "assessments": [g.model_dump() for g in evaluated]},
                    SearchPlan,
                )
                focus = strategy.focus
            except OutputError:
                focus = "counter_evidence"
            remaining_rounds = session.settings.retrieval_rounds - round_index
            round_documents = (
                question_document_limit - len(provider.fetched) + remaining_rounds - 1
            ) // remaining_rounds
            round_document_limit = len(provider.fetched) + round_documents
            for candidate in provider.discover(question.concept, focus):
                session.check()
                identity = candidate.get("doi") or candidate["url"]
                if identity in provider.fetched:
                    continue
                if len(provider.fetched) >= round_document_limit:
                    break
                provider.fetched.add(identity)
                progress("verifying_sources")
                try:
                    passages = provider.fetch(candidate)
                    for passage in passages:
                        store.put(passage)
                        candidate_ids.add(passage.id)
                    session.trace.append(
                        {
                            "stage": "fetch_source",
                            "document_id": identity,
                            "passages": len(passages),
                            "access": passages[0].access if passages else None,
                        }
                    )
                except SourceError as exc:
                    session.trace.append({"stage": "fetch_source", "document_id": identity, "error": str(exc)})
        if not resolved:
            gaps.append(
                {
                    "question": question.model_dump(),
                    "reason": "Applicable inspected research remains incomplete or conflicting within the retrieval budget.",
                }
            )
    return accepted, grades, gaps, {key: sorted(value) for key, value in scopes.items()}
