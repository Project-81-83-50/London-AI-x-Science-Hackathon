import re

from .models import Claim, Document, Draft, Fact, Grade, Sample, Source
from .retrieval import normalized

PLACEHOLDER = re.compile(r"\{(F\d+_\d+)\}")
NUMBER = re.compile(r"(?<!\w)[-+]?\d+(?:\.\d+)?")
UNSUPPORTED = re.compile(
    r"statistically indistinguishable|\binseparable\b|\bproves?\b|caused the classification|drove the call",
    re.IGNORECASE,
)


def render_text(text: str, facts: dict[str, Fact]) -> str:
    return PLACEHOLDER.sub(lambda match: facts[match[1]].display if match[1] in facts else match[0], text)


def _numeric_checks(claim: Claim, sample: Sample, facts: dict[str, Fact]) -> list[str]:
    errors = []
    used = set(PLACEHOLDER.findall(claim.text))
    nearest = re.search(
        r"\b(?:closest to|nearest to|closest mean is|closest mean for)\s+(Batch_\d+)", claim.text, re.IGNORECASE
    )
    if nearest:
        supported = False
        for comparison in sample.comparisons:
            if comparison.value_id not in used:
                continue
            value = facts[comparison.value_id].value
            distances = {batch: abs(facts[fid].value - value) for batch, fid in comparison.reference_ids.items()}
            if distances:
                supported |= nearest[1] in distances and abs(distances[nearest[1]] - min(distances.values())) < 1e-8
        if not supported:
            errors.append(f"{claim.id}: closest-mean claim contradicts or lacks the referenced comparison")
    holders = list(PLACEHOLDER.finditer(claim.text))
    for left, right in zip(holders, holders[1:], strict=False):
        a, b = facts.get(left[1]), facts.get(right[1])
        if a is None or b is None or a.unit != b.unit or not all(isinstance(f.value, (float, int)) for f in (a, b)):
            continue
        gap = claim.text[left.end() : right.start()]
        if len(gap) > 70 or re.search(r"[;.]", gap):
            continue
        same_metric = any(a.id == c.value_id and b.id in c.reference_ids.values() for c in sample.comparisons)
        if not same_metric:
            continue
        lower = re.search(r"\b(?:below|lower than|less than|smaller than)\b", gap, re.IGNORECASE)
        higher = re.search(r"\b(?:above|higher than|greater than|larger than)\b", gap, re.IGNORECASE)
        if a.display != b.display and (lower and a.value >= b.value or higher and a.value <= b.value):
            errors.append(f"{claim.id}: numerical comparison has the wrong direction")
    for label in re.finditer(r"(Batch_\d+)\s+(?:mean|median)\s*\{(F\d+_\d+)\}", claim.text):
        fact = facts.get(label[2])
        if fact and "/batch_means/" in fact.pointer and not fact.pointer.endswith("/" + label[1]):
            errors.append(f"{claim.id}: batch name and mean reference disagree")
    if (
        re.search(
            r"(?:ranges?|intervals?).*(?:overlap|separat)|(?:overlap|separat).*(?:ranges?|intervals?)",
            claim.text,
            re.IGNORECASE,
        )
        and claim.kind != "limitation"
    ):
        intervals = {}
        for fid in used:
            fact = facts.get(fid)
            if fact is None:
                continue
            root, _, endpoint = fact.pointer.rpartition("/")
            if (
                "/ranges/" in root
                and endpoint in {"0", "1"}
                or "/reference_profiles/" in root
                and endpoint in {"q1", "q3", "min", "max"}
            ):
                family = "typical" if endpoint in {"q1", "q3"} else "observed"
                intervals.setdefault((root, family), {})[endpoint] = fact
        complete = [values for values in intervals.values() if len(values) == 2]
        measures = {next(iter(values.values())).label.split(":")[0] for values in complete}
        observed = [facts[fid] for fid in used if fid in facts and facts[fid].role == "observation"]
        if len(complete) != 2 or len(measures) != 1 or not any(f.label.split(":")[0] in measures for f in observed):
            errors.append(
                f"{claim.id}: range claims need a sample value and both endpoints of two comparable ranges in this point"
            )
        else:
            left, right = [sorted(f.value for f in group.values()) for group in complete]
            disjoint = left[1] < right[0] or right[1] < left[0]
            says_disjoint = bool(
                re.search(r"non.?overlap|do not overlap|don't overlap|separat", claim.text, re.IGNORECASE)
            )
            if says_disjoint != disjoint:
                errors.append(f"{claim.id}: stated range overlap/separation contradicts the endpoints")
    return errors


def validate(
    draft: Draft, document: Document, sources: dict[str, Source], grades: list[Grade], scopes: dict[str, list[str]]
) -> list[str]:
    samples = {s.sample_id: s for s in document.samples}
    facts = {f.id: f for s in document.samples for f in s.facts}
    ids = [item.sample_id for item in draft.explanations]
    errors = []
    if len(ids) != len(samples) or set(ids) != set(samples):
        errors.append("Return exactly one explanation per sample, with no omissions or duplicates")
    supported = {g.source_id for g in grades if g.verdict == "supported"}
    claim_ids: set[str] = set()
    for explanation in draft.explanations:
        sample = samples.get(explanation.sample_id)
        if sample is None:
            continue
        if explanation.answer != sample.answer:
            errors.append(f"{sample.sample_id}: preserve the authoritative answer {sample.answer}")
        compared = not any(c.used_by_model for c in sample.comparisons) or sample.answer_type in {
            "refused",
            "known_location",
            "unsure",
        }
        has_limit = False
        for claim in explanation.claims:
            if claim.sample_id != sample.sample_id or claim.id in claim_ids:
                errors.append(f"{claim.id}: duplicate claim or wrong sample owner")
            claim_ids.add(claim.id)
            refs = set(PLACEHOLDER.findall(claim.text))
            local = [facts[fid] for fid in refs if fid in facts and facts[fid].sample_id == sample.sample_id]
            if len(local) != len(refs):
                errors.append(f"{claim.id}: unknown or cross-sample numerical evidence")
            text = PLACEHOLDER.sub("", claim.text)
            text = re.sub(r"Batch_\d+|DINOv2|2-D|3-D", "", text)
            if NUMBER.search(text) or "{" in text or "}" in text:
                errors.append(f"{claim.id}: all numerical claims need typed fact placeholders")
            if UNSUPPORTED.search(text):
                errors.append(f"{claim.id}: unsupported certainty, causality or batch equivalence")
            for other in samples.keys() - {sample.sample_id}:
                if re.search(rf"(?<!\w){re.escape(other)}(?!\w)", claim.text):
                    errors.append(f"{claim.id}: mentions another sample")
            word_limit = 35 if claim.kind in {"decision", "opposing"} else 60
            if len(render_text(claim.text, facts).split()) > word_limit:
                errors.append(
                    f"{claim.id}: exceedance of {word_limit} words; keep the point concise without dropping its evidence"
                )
            errors.extend(_numeric_checks(claim, sample, facts))
            if claim.kind == "decision":
                profile_ids = sorted(f.id for f in local if f.pointer.startswith("/reference_profiles/"))
                if profile_ids:
                    errors.append(
                        f"{claim.id}: remove these descriptive-profile placeholders and their comparison clause from THIS decision point: "
                        f"{', '.join('{' + fid + '}' for fid in profile_ids)}. Keep the actual measured input and reported model contribution. "
                        "A caveat in another point does not fix this; the profiles are not reconstructed classifier evidence."
                    )
                if any(f.role in {"quality", "diagnostic"} for f in local):
                    errors.append(
                        f"{claim.id}: quality metrics and probability/diagnostic scores are not material reasons"
                    )
                if not any(f.used_by_model or f.role == "attribution" for f in local):
                    errors.append(
                        f"{claim.id}: decision reasons must reference actual model inputs or signed attribution"
                    )
                if any(f.role == "attribution" and f.contrast and f.contrast[0] != sample.answer for f in local):
                    errors.append(
                        f"{claim.id}: this attribution supports a different component answer; describe it as opposing evidence"
                    )
            if any(f.role == "attribution" for f in local):
                if not re.search(r"DINO|attribution|evidence", claim.text, re.IGNORECASE):
                    errors.append(f"{claim.id}: label attribution separately from physical area or probability")
                if not all(batch in claim.text for batch in sample.attribution_pair):
                    errors.append(f"{claim.id}: name the material contrast {' versus '.join(sample.attribution_pair)}")
                for fact in local:
                    if fact.pointer.endswith("/share_pct") and re.search(
                        rf"\{{{fact.id}\}}\s*(?:of\s+)?(?:all|total)\s+(?:DINOv2\s+)?evidence",
                        claim.text,
                        re.IGNORECASE,
                    ):
                        errors.append(f"{claim.id}: phase attribution share is not a share of all signed evidence")
                    if "/positive/" in fact.pointer and "positive" not in claim.text.lower():
                        errors.append(f"{claim.id}: positive phase evidence has its own denominator")
                    if "/negative/" in fact.pointer and not re.search(
                        r"negative|opposing|against", claim.text, re.IGNORECASE
                    ):
                        errors.append(f"{claim.id}: label negative attribution")
            for fact in local:
                if fact.pointer.endswith("/robust_z") and (
                    not set(fact.inputs) <= refs
                    or not re.search(r"robust|training.relative|pooled.training", claim.text, re.IGNORECASE)
                ):
                    errors.append(
                        f"{claim.id}: robust/training-relative scores need their actual measured value and an explicit score label"
                    )
            for comparison in sample.comparisons:
                compared |= (
                    comparison.used_by_model
                    and comparison.value_id in refs
                    and len(refs & set(comparison.reference_ids.values())) >= 2
                )
            if claim.kind == "interpretation" and (not claim.citations or not local):
                errors.append(
                    f"{claim.id}: scientific interpretation needs both sample facts and accepted original passages"
                )
            for citation in claim.citations:
                source = sources.get(citation.source_id)
                if (
                    source is None
                    or citation.source_id not in supported
                    or sample.sample_id not in scopes.get(citation.source_id, [])
                ):
                    errors.append(f"{claim.id}: source not accepted/applicable for this sample")
                elif normalized(citation.quote) not in normalized(source.text):
                    errors.append(f"{claim.id}: quotation is not in the original passage")
                elif (
                    source.access in {"seed", "abstract"}
                    or source.updates == "notice"
                    or source.doi
                    and source.updates != "none_found"
                ):
                    errors.append(f"{claim.id}: supporting full text or publication-status review is missing")
            if claim.kind != "limitation" and not local and not claim.citations:
                errors.append(f"{claim.id}: no evidence attached")
            has_limit |= claim.kind == "limitation"
        if not compared:
            errors.append(
                f"{sample.sample_id}: include a selected measurement and at least two named batch reference values"
            )
        applicable_science = any(
            sid in supported
            and sample.sample_id in scopes.get(sid, [])
            and source.access in {"full_text", "technical"}
            and source.status != "excluded"
            and source.updates != "notice"
            and (not source.doi or source.updates == "none_found")
            for sid, source in sources.items()
        )
        if applicable_science and not any(
            claim.kind == "interpretation" and claim.citations for claim in explanation.claims
        ):
            errors.append(
                f"{sample.sample_id}: include a short scientific interpretation connecting a sample fact to an accepted passage; listing sources alone is insufficient"
            )
        if not has_limit:
            errors.append(f"{sample.sample_id}: include the material limitation without inventing a mechanism")
    return errors


def render(draft: Draft, document: Document) -> tuple[dict[str, str], list[dict], str]:
    facts = {f.id: f for s in document.samples for f in s.facts}
    by_id = {item.sample_id: item for item in draft.explanations}
    explanations, claims, sections = {}, [], []
    for sample in document.samples:
        sections.append(f"## {sample.sample_id}: {sample.answer}\n")
        points = []
        for claim in by_id[sample.sample_id].claims:
            text = " ".join(render_text(claim.text, facts).split())
            direct_ids = list(dict.fromkeys(PLACEHOLDER.findall(claim.text)))
            supporting_ids = [
                fact.id
                for fact in sample.facts
                if fact.id not in direct_ids
                and fact.inputs
                and set(fact.inputs) <= set(direct_ids)
                and fact.role in {"calculation", "attribution"}
            ]
            rendered = {
                **claim.model_dump(),
                "text": text,
                "fact_ids": direct_ids,
                "supporting_fact_ids": supporting_ids,
            }
            claims.append(rendered)
            points.append("- " + text)
        explanations[sample.sample_id] = "\n".join(points)
        sections.extend(points)
    return explanations, claims, "\n".join(sections)
