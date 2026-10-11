import copy
import json
import time
from types import SimpleNamespace

import pytest
from test_research_facts import sample

from app.research.agents import AgentSession, coordinate
from app.research.checks import validate
from app.research.config import ResearchError
from app.research.engine import explain
from app.research.facts import decode
from app.research.models import Analysis, Draft, Grade, Grades, Question, Review, SearchPlan, Settings, Source
from app.research.retrieval import grade, research
from app.research.sources import ResearchSources, SourceError, Transport
from app.research.store import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import anthropic

    def refuse(*_args, **_kwargs):
        raise AssertionError("Network calls must be mocked in tests")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)
    monkeypatch.setattr(Transport, "get", refuse)


class Client:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.messages = self
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        assert self.outputs, "Unexpected model call"
        output = self.outputs.pop(0)
        if callable(output):
            output = output(kwargs)
        if hasattr(output, "model_dump"):
            output = output.model_dump()
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(output))],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=100),
        )


class Provider:
    def __init__(self, sources=()):
        self.passages = list(sources)
        self.warnings, self.fetched, self.queries = [], set(), []
        self.transport = SimpleNamespace(count=0)

    def discover(self, concept, focus):
        self.queries.append((concept, focus))
        return [{"url": p.url, "doi": p.document_id} for p in self.passages]

    def fetch(self, _candidate):
        self.transport.count += 1
        return self.passages


def passage(sid="S1", access="full_text", status="approved"):
    text = "Secondary electron contrast depends on surface geometry and detector collection conditions. It does not uniquely identify binder chemistry."
    return Source(
        id=sid,
        document_id=sid,
        title="SEM graphite silicon oxide detector contrast",
        text=text,
        url="https://example.org/paper",
        location="Methods paragraph 1",
        content_hash=sid,
        access=access,
        status=status,
        updates="none_found",
        checked_at=time.time(),
    )


def supported(source, verdict="supported", applicable=True):
    return Grade(
        source_id=source.id,
        verdict=verdict,
        relevant=True,
        applicable=applicable,
        answers_question=True,
        statement="Detector contrast is not uniquely chemical identification.",
        quote=source.text,
        reason="Applicable methods with qualification",
    )


def draft(document):
    result = []
    for item in document.samples:
        comparison = item.comparisons[0]
        f = comparison.reference_ids
        text = (
            "ETD-dark solid {"
            + comparison.value_id
            + "}: Batch_1 mean {"
            + f["Batch_1"]
            + "}, Batch_2 {"
            + f["Batch_2"]
            + "}, Batch_3 {"
            + f["Batch_3"]
            + "}; closest to Batch_3."
        )
        result.append(
            {
                "sample_id": item.sample_id,
                "answer": item.answer,
                "claims": [
                    {"id": item.sample_id + "-reason", "sample_id": item.sample_id, "kind": "decision", "text": text},
                    {
                        "id": item.sample_id + "-limit",
                        "sample_id": item.sample_id,
                        "kind": "limitation",
                        "text": "Detector contrast has multiple interpretations and is not a unique chemical identification.",
                    },
                ],
            }
        )
    return Draft.model_validate({"explanations": result})


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "corpus")
    yield db
    db.close()


def test_native_json_schema_constrains_the_reported_answer():
    document = decode(sample())
    client = Client([draft(document)])
    from app.research.agents import sample_views

    session = AgentSession(Settings(), {}, client)
    session.ask("materials_writer", "Return JSON", {"samples": sample_views(document)}, Draft)
    config = client.requests[0]["output_config"]
    assert config["format"]["type"] == "json_schema"
    assert config["format"]["schema"]["$defs"]["Explanation"]["properties"]["answer"]["enum"] == ["Batch_3"]
    assert config["effort"] == "low"


def test_coordinator_repairs_invalid_schema_without_exposing_output():
    private = "private-provider-text"
    client = Client([{"done": private}, Analysis(done=True, reason="Selected measured evidence")])
    session = AgentSession(Settings(), {}, client)
    assert coordinate(decode(sample()), session).done
    repair = json.loads(client.requests[1]["messages"][0]["content"])
    assert "bool_parsing" in repair["contract_feedback"]
    assert private not in repair["contract_feedback"]
    assert len(session.calls) == 2


def test_coordinator_can_select_known_warning_evidence():
    document = decode(sample())
    plan = Analysis(done=True, selected_facts=["F0_0", "W0_0"], reason="Keep the measured input and its limitation")
    client = Client([plan])
    assert coordinate(document, AgentSession(Settings(), {}, client)).selected_facts == ["F0_0", "W0_0"]
    allowed = client.requests[0]["output_config"]["format"]["schema"]["properties"]["selected_facts"]["items"]["enum"]
    assert "W0_0" in allowed and "made-up" not in allowed


def test_document_budget_is_shared_across_research_questions():
    class ScopedStore:
        def __init__(self):
            self.entries = {}

        def put(self, source):
            self.entries[source.id] = source

        def search(self, query, candidate_ids, _max_age, limit=6, originals_only=False, exclude_ids=None):
            prefix = "P" if "porosity" in query else "D"
            return [
                s
                for sid, s in self.entries.items()
                if sid in candidate_ids and sid.startswith(prefix) and sid not in (exclude_ids or set())
            ][:limit]

    class ScopedProvider(Provider):
        def discover(self, concept, focus):
            prefix = "P" if concept == "porosity" else "D"
            return [{"doi": f"{prefix}{i}", "url": "https://example.org/paper"} for i in range(3)]

        def fetch(self, candidate):
            return [passage(candidate["doi"], status="candidate")]

    def response(request):
        payload = json.loads(request["messages"][0]["content"])
        if "sources" not in payload:
            return SearchPlan(focus="meaning", reason="Find applicable theory")
        return Grades(
            items=[
                supported(Source.model_validate(s), verdict="supported" if s["id"].startswith("P") else "unsupported")
                for s in payload["sources"]
            ]
        )

    session = AgentSession(Settings(max_documents=2), {}, Client([response] * 8))
    provider = ScopedProvider()
    questions = [Question(concept=concept, sample_ids=["sample_one"]) for concept in ("detector_contrast", "porosity")]
    sources, _, gaps, _ = research(questions, decode(sample()), ScopedStore(), provider, session, lambda _s: None)
    assert provider.fetched == {"D0", "P0"}
    assert set(sources) == {"P0"} and len(gaps) == 1


def test_corrective_round_can_refine_a_query_before_documents_run_out(store):
    class RefiningProvider(Provider):
        def discover(self, concept, focus):
            self.queries.append((concept, focus))
            prefix = "D" if len(self.queries) == 1 else "P"
            return [{"doi": f"{prefix}{i}", "url": "https://example.org/paper"} for i in range(3)]

        def fetch(self, candidate):
            return [passage(candidate["doi"], status="candidate")]

    def response(request):
        payload = json.loads(request["messages"][0]["content"])
        if "sources" not in payload:
            return SearchPlan(focus="meaning", reason="Refine the public principle query")
        return Grades(
            items=[
                supported(Source.model_validate(s), verdict="supported" if s["id"].startswith("P") else "unsupported")
                for s in payload["sources"]
            ]
        )

    session = AgentSession(Settings(max_documents=3), {}, Client([response] * 8))
    provider = RefiningProvider()
    sources, _, gaps, _ = research(
        [Question(concept="detector_contrast", sample_ids=["sample_one"])],
        decode(sample()),
        store,
        provider,
        session,
        lambda _s: None,
    )
    assert provider.fetched == {"D0", "D1", "P0"}
    assert set(sources) == {"P0"} and gaps == []
    assert len(provider.queries) == 2


def test_scholarly_discovery_prefers_accessible_original_papers():
    works = [
        {"doi": "https://doi.org/10.example/abstract", "display_name": "Abstract lead"},
        {
            "doi": "https://doi.org/10.example/paper",
            "display_name": "Accessible paper",
            "best_oa_location": {"is_oa": True, "license": "cc-by", "pdf_url": "https://example.org/paper.pdf"},
        },
    ]
    provider = ResearchSources(SimpleNamespace(json=lambda *_args, **_kwargs: {"results": works}), {})
    candidates = provider.discover("porosity", "meaning")
    assert candidates[0]["doi"] == "10.example/paper"
    assert candidates[1]["doi"] == "10.example/abstract"


def test_related_caveat_does_not_close_a_different_research_question(store):
    source = passage()
    store.put(source)
    assessment = supported(source)
    assessment.answers_question = False
    session = AgentSession(Settings(online=False), {}, Client([Grades(items=[assessment])]))
    accepted, _, gaps, _ = research(
        [Question(concept="detector_contrast", sample_ids=["sample_one"])],
        decode(sample()),
        store,
        Provider(),
        session,
        lambda _s: None,
    )
    assert source.id in accepted
    assert len(gaps) == 1 and session.trace[-1]["route"] == "ambiguous"


def test_original_passages_cannot_be_crowded_out_by_discovery_summaries(store):
    for index in range(8):
        store.put(passage(f"seed{index}", access="seed"))
    paper = passage("paper", status="candidate")
    store.put(paper)
    originals = store.search("SEM secondary electron contrast", {paper.id}, 86400, originals_only=True)
    assert [source.id for source in originals] == [paper.id]
    assert (
        store.search("SEM secondary electron contrast", {paper.id}, 86400, originals_only=True, exclude_ids={paper.id})
        == []
    )


def test_accepted_science_must_be_used_in_the_explanation():
    document = decode(sample())
    source = passage()
    errors = validate(draft(document), document, {source.id: source}, [supported(source)], {source.id: ["sample_one"]})
    assert any("scientific interpretation" in error for error in errors)


def test_numerical_points_are_short_and_calculations_stay_expandable():
    from app.research.checks import render

    document = decode(sample())
    report = draft(document)
    _, claims, _ = render(report, document)
    contribution = next(f for f in document.samples[0].facts if f.pointer.endswith("/support_for_answer"))
    assert contribution.id in claims[0]["supporting_fact_ids"]
    report.explanations[0].claims[0].text += " Additional descriptive material" * 12
    assert any("35 words" in error for error in validate(report, document, {}, [], {}))


def test_scoped_tool_loop():
    document = decode(sample())
    plan = Analysis(
        done=False, tools=[{"name": "comparisons", "sample_id": "sample_one"}], reason="Inspect reference figures"
    )
    finish = Analysis(done=True, selected_facts=[], questions=[], reason="Selected KPI already supplies comparison")
    session = AgentSession(Settings(), {}, Client([plan, finish]))
    assert coordinate(document, session).done
    assert session.trace[0]["tool"] == "comparisons"


def test_analyst_cannot_read_other_sample_as_its_own():
    document = decode([sample("one"), sample("two")])
    foreign = document.samples[1].facts[0].id
    plan = Analysis(done=False, tools=[{"name": "facts", "sample_id": "one", "fact_ids": [foreign]}], reason="Read")
    with pytest.raises(ResearchError, match="boundaries"):
        coordinate(document, AgentSession(Settings(), {}, Client([plan])))


def test_corrective_online_fallback(store):
    source = passage(status="candidate")
    question = Question(concept="detector_contrast", sample_ids=["sample_one"])
    client = Client(
        [SearchPlan(focus="limitations", reason="No applicable local source"), Grades(items=[supported(source)])]
    )
    session = AgentSession(Settings(retrieval_rounds=1), {}, client)
    provider = Provider([source])
    sources, _, gaps, scopes = research([question], decode(sample()), store, provider, session, lambda _s: None)
    assert list(sources) == ["S1"] and gaps == [] and scopes["S1"] == ["sample_one"]
    assert [event["route"] for event in session.trace if event["stage"] == "corrective_retrieval"] == [
        "unsupported",
        "supported",
    ]
    assert provider.queries == [("detector_contrast", "limitations")]


@pytest.mark.parametrize("access", ["abstract", "seed"])
def test_partial_sources_cannot_be_laundered_as_full_text(access):
    source = passage(access=access)
    session = AgentSession(Settings(), {}, Client([Grades(items=[supported(source)])]))
    result = grade(Question(concept="porosity", sample_ids=["sample_one"]), [source], decode(sample()), session)
    assert result[0].verdict == "ambiguous"


def test_irrelevant_or_inapplicable_passage_not_accepted():
    source = passage()
    session = AgentSession(Settings(), {}, Client([Grades(items=[supported(source, applicable=False)])]))
    result = grade(Question(concept="porosity", sample_ids=["sample_one"]), [source], decode(sample()), session)
    assert result[0].verdict == "unsupported"


def test_offline_retrieval_abstains_instead_of_using_model_memory(store):
    session = AgentSession(Settings(online=False), {}, Client([]))
    sources, _, gaps, _ = research(
        [Question(concept="particles", sample_ids=["sample_one"])],
        decode(sample()),
        store,
        Provider(),
        session,
        lambda _s: None,
    )
    assert not sources and gaps


def test_store_scope_admission_and_invalidation(store):
    initial = store.version()
    store.put(passage())
    assert store.version() != initial
    assert store.search("SEM secondary electron contrast", set(), 86400)[0].id == "S1"
    source = passage("S2", status="candidate")
    store.put(source)
    assert "S2" not in {s.id for s in store.search("SEM contrast", set(), 86400)}
    assert "S2" in {s.id for s in store.search("SEM contrast", {"S2"}, 86400)}
    store.admit("S1", False)
    assert "S1" not in {s.id for s in store.search("SEM contrast", set(), 86400)}


def test_seed_refresh_does_not_keep_deleted_entries(store, tmp_path):
    path = tmp_path / "seed.json"
    path.write_text(json.dumps({"features": [{"id": "A", "name": "SEM porosity"}]}))
    store.seed(path)
    assert any(s.status == "approved" for s in store.sources().values())
    path.write_text(json.dumps({"features": []}))
    store.seed(path)
    assert all(s.status == "excluded" for s in store.sources().values())


def test_typed_validation_catches_wrong_direction_and_decision():
    document = decode(sample())
    result = draft(document)
    claim = result.explanations[0].claims[0]
    group = document.samples[0].comparisons[0]
    claim.text = (
        "ETD-dark solid {" + group.value_id + "} is below Batch_1 mean {" + group.reference_ids["Batch_1"] + "}."
    )
    result.explanations[0].answer = "Batch_1"
    errors = validate(result, document, {}, [], {})
    assert any("direction" in e for e in errors) and any("authoritative" in e for e in errors)


def test_citations_need_exact_quotes_and_sample_applicability():
    from app.research.models import Citation

    document = decode(sample())
    result = draft(document)
    claim = result.explanations[0].claims[0]
    claim.kind = "interpretation"
    source = passage()
    claim.citations = [Citation(source_id=source.id, quote=source.text)]
    assert validate(result, document, {source.id: source}, [supported(source)], {"S1": ["sample_one"]}) == []
    claim.citations[0].quote = "A fabricated quotation not present in the source passage."
    assert any(
        "quotation" in e
        for e in validate(result, document, {source.id: source}, [supported(source)], {"S1": ["sample_one"]})
    )


def test_whole_document_generation_and_cache(store):
    data = {"samples": [sample("one"), sample("two")]}
    before = copy.deepcopy(data)
    document = decode(data)
    client = Client([Analysis(done=True, reason="Numerical comparison"), draft(document), Review(findings=[])])
    result = explain(data, store, Settings(), {}, client=client, provider=Provider())
    assert list(result.explanations) == ["one", "two"] and data == before
    assert result.audit["validator_passed"] and result.audit["reviewer_passed"]
    second = Client([])
    cached = explain(data, store, Settings(), {}, client=second, provider=Provider())
    assert cached.audit["cache_hit"] and not second.requests
    assert cached.explanations == result.explanations


def test_profile_repair_feedback_identifies_the_offending_placeholders():
    document = decode(sample())
    extra = (
        document.samples[0]
        .facts[1]
        .model_copy(update={"id": "F0_999", "pointer": "/reference_profiles/pore/Batch_1/median"})
    )
    document.samples[0].facts.append(extra)
    report = draft(document)
    report.explanations[0].claims[0].text += " Reference median {F0_999}."
    errors = validate(report, document, {}, [], {})
    assert any(
        "sample_one-reason" in error and "{F0_999}" in error and "from THIS decision point" in error for error in errors
    )


def test_invalid_draft_repaired_before_review(store):
    document = decode(sample())
    bad = draft(document)
    bad.explanations[0].answer = "Batch_1"
    client = Client([Analysis(done=True, reason="Compare"), bad, draft(document), Review(findings=[])])
    result = explain(sample(), store, Settings(), {}, client=client, provider=Provider())
    assert len(client.requests) == 4 and result.audit["validator_passed"]
    repair = json.loads(client.requests[2]["messages"][0]["content"])
    assert repair["previous_draft"] == bad.model_dump()
    assert repair["repair_feedback"]


def test_invalid_reviewer_findings_are_repaired_by_the_reviewer(store):
    from app.research.models import Finding

    document = decode(sample())
    report = draft(document)
    invalid = Review(
        findings=[
            Finding(
                claim_id="sample_one-limit",
                category="inapplicable",
                reason="Missing warning reference",
                evidence_ids=[],
                action="rewrite",
            )
        ]
    )
    client = Client([Analysis(done=True, reason="Compare"), report, invalid, Review(findings=[])])
    result = explain(sample(), store, Settings(), {}, client=client, provider=Provider())
    assert result.audit["reviewer_passed"]
    assert len(client.requests) == 4
    repair = json.loads(client.requests[3]["messages"][0]["content"])
    assert repair["previous_review"] == invalid.model_dump()
    assert repair["draft"] == report.model_dump()
    assert "W0_0" in repair["allowed_evidence_ids"]
    assert "Repair the review" in repair["review_feedback"]


def test_reviewer_can_cite_recorded_research_gaps():
    from app.research.engine import review_claims
    from app.research.models import Finding

    document = decode(sample())
    gap = {"question": {"concept": "detector_contrast", "sample_ids": ["sample_one"]}, "reason": "No accepted research"}
    finding = Finding(
        claim_id="sample_one-limit",
        category="unsupported",
        reason="Check disclosed retrieval gap",
        evidence_ids=["G0"],
        action="rewrite",
    )
    client = Client([Review(findings=[finding])])
    review = review_claims(document, draft(document), {}, [], [gap], AgentSession(Settings(), {}, client))
    assert review.findings[0].evidence_ids == ["G0"]
    payload = json.loads(client.requests[0]["messages"][0]["content"])
    assert payload["research_gaps"]["G0"] == gap


def test_compact_evidence_preserves_formatted_values_and_method_definitions():
    from app.research.agents import sample_views, warning_evidence

    document = decode(sample())
    view = sample_views(document)[0]
    assert view["facts"][0]["display"] == document.samples[0].facts[0].display
    assert "raw_value" not in view["facts"][0]
    assert view["methods"][view["facts"][0]["method_id"]] == document.samples[0].facts[0].method
    assert view["warnings"] == warning_evidence(document)


def test_substantive_review_blocks_publication(store):
    from app.research.models import Finding

    document = decode(sample())
    result = draft(document)
    finding = Finding(
        claim_id=result.explanations[0].claims[0].id,
        category="unsupported",
        reason="Unsupported inference",
        evidence_ids=[document.samples[0].facts[0].id],
        action="remove",
    )
    client = Client([Analysis(done=True, reason="Compare"), result, Review(findings=[finding])])
    with pytest.raises(ResearchError, match="bounded"):
        explain(sample(), store, Settings(draft_attempts=1), {}, client=client, provider=Provider())
    assert store.db.execute("SELECT count(*) FROM results").fetchone()[0] == 0


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://example.org", "https://user:password@example.org", "https://example.org:8080"]
)
def test_disallowed_source_urls(url):
    with pytest.raises(SourceError):
        Transport.resolve(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_private_dns_responses_blocked(address, monkeypatch):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(None, None, None, None, (address, 443))])
    with pytest.raises(SourceError, match="Private"):
        Transport.resolve("https://example.org")


def test_private_queries_are_never_sent_online():
    provider = ResearchSources(Transport(2, time.monotonic() + 10), {})
    with pytest.raises(SourceError):
        provider.discover("sample_id=secret-image Batch_3 5.71", "meaning")


def test_phase_attribution_is_not_total_evidence():
    document = decode(sample())
    output = draft(document)
    fact = next(f for f in document.samples[0].facts if f.pointer.endswith("/positive/SiOx/share_pct"))
    from app.research.models import Claim

    output.explanations[0].claims.insert(
        1,
        Claim(
            id="wrong-denominator",
            sample_id="sample_one",
            kind="decision",
            text=f"DINOv2 positive attribution for Batch_3 versus Batch_1 is {{{fact.id}}} of all evidence on SiOx.",
        ),
    )
    assert any("all signed evidence" in error for error in validate(output, document, {}, [], {}))


def test_retrieval_receives_the_measured_detector_definition():
    data = sample()
    description = "Area share dark in ETD but solid in BSE; not a unique chemical identity."
    data["kpi_model"]["drivers"][0]["description"] = description
    source = passage()
    client = Client([Grades(items=[supported(source)])])
    session = AgentSession(Settings(), {}, client)
    grade(Question(concept="detector_contrast", sample_ids=["sample_one"]), [source], decode(data), session)
    payload = json.loads(client.requests[0]["messages"][0]["content"])
    features = payload["sample_methods"][0]["measured_features"]
    assert any(feature["description"] == description for feature in features)


def test_joined_quotation_is_still_rejected():
    source = passage()
    response = supported(source)
    response.quote = "Secondary electron contrast depends [...] It does not uniquely identify binder chemistry."
    session = AgentSession(Settings(), {}, Client([Grades(items=[response])]))
    result = grade(
        Question(concept="detector_contrast", sample_ids=["sample_one"]), [source], decode(sample()), session
    )
    assert result[0].verdict == "unsupported"


def test_unknown_publication_status_is_not_supported():
    source = passage()
    source.doi, source.updates = "10.example/article", "unknown"
    session = AgentSession(Settings(), {}, Client([Grades(items=[supported(source)])]))
    result = grade(Question(concept="porosity", sample_ids=["sample_one"]), [source], decode(sample()), session)
    assert result[0].verdict == "ambiguous"


def test_changed_rendered_cache_is_rejected(store):
    document = decode(sample())
    outputs = [Analysis(done=True, reason="Compare"), draft(document), Review(findings=[])]
    explain(sample(), store, Settings(), {}, client=Client(outputs), provider=Provider())
    key, value = store.db.execute("SELECT key,payload FROM results").fetchone()
    value = json.loads(value)
    value["result"]["explanations"]["sample_one"] = "- Altered after validation"
    with store.db:
        store.db.execute("UPDATE results SET payload=? WHERE key=?", (json.dumps(value), key))
    client = Client(outputs)
    result = explain(sample(), store, Settings(), {}, client=client, provider=Provider())
    assert not result.audit["cache_hit"] and len(client.requests) == 3


@pytest.mark.parametrize("nested", [False, True])
def test_insufficient_api_credit_has_actionable_redacted_error(nested):
    class BillingFailure(Exception):
        status_code = 400
        error = {"message": "Your credit balance is too low to access the Anthropic API. provider-private-detail"}
        body = {"error": error} if nested else error

    def fail(**_kwargs):
        raise BillingFailure()

    client = SimpleNamespace(messages=SimpleNamespace(create=fail))
    session = AgentSession(Settings(), {}, client)
    with pytest.raises(ResearchError) as caught:
        session.ask("coordinator", "Return JSON", {}, Analysis)
    assert caught.value.code == "billing"
    assert "API credits" in str(caught.value)
    assert "provider-private-detail" not in str(caught.value)
    assert len(session.calls) == 1


def test_generation_cancellation_is_checked(store):
    with pytest.raises(ResearchError, match="cancelled"):
        explain(sample(), store, Settings(), {}, client=Client([]), provider=Provider(), cancelled=lambda: True)
