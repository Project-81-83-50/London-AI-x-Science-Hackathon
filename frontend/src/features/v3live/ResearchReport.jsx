function safeLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export default function ResearchReport({ report }) {
  const facts = report.facts || {};
  const sources = report.sources || {};
  const audit = report.audit || {};
  return (
    <div className="v3-research v3-markdown">
      {report.research_status === "incomplete" && (
        <p className="v3-warn">
          Some scientific interpretation remains unsupported or conflicting. The measured classification reasons are
          shown; this is not a fully established material mechanism.
        </p>
      )}
      <p className="v3-small v3-muted">
        {audit.cache_hit
          ? "Reused a revalidated result and its original review."
          : "Numerical evidence checked; independent grounding review completed."}
        {audit.elapsed_seconds != null && ` · ${audit.elapsed_seconds} s`}
      </p>
      {Object.entries(report.explanations || {}).map(([sampleId, explanation]) => (
        <section key={sampleId}>
          <h4>{sampleId}</h4>
          <ul className="v3-sentinel">
            {explanation
              .split("\n")
              .filter(Boolean)
              .map((point, index) => (
                <li key={`${sampleId}-${index}`}>{point.replace(/^-\s*/, "")}</li>
              ))}
          </ul>
          <details className="v3-details">
            <summary>Supporting measurements, mathematics and research</summary>
            {(report.claims || [])
              .filter((claim) => claim.sample_id === sampleId)
              .map((claim) => (
                <section key={claim.id}>
                  <h4>{claim.kind.replaceAll("_", " ")}</h4>
                  <p>{claim.text}</p>
                  {!!claim.fact_ids?.length && (
                    <div style={{ overflowX: "auto" }}>
                      <table className="v3live-table">
                        <caption>Source-linked evidence</caption>
                        <thead>
                          <tr>
                            <th>Quantity</th>
                            <th>Value</th>
                            <th>Scope and method</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...new Set([...claim.fact_ids, ...(claim.supporting_fact_ids || [])])].map((id) => {
                            const fact = facts[id];
                            if (!fact) return null;
                            return (
                              <tr key={id}>
                                <td>
                                  {fact.label}
                                  <br />
                                  <code>{fact.pointer}</code>
                                </td>
                                <td>{fact.display}</td>
                                <td>
                                  {fact.method}
                                  {fact.denominator && <p>Denominator: {fact.denominator}</p>}
                                  {fact.uncertainty && <p>{fact.uncertainty}</p>}
                                  {fact.formula && (
                                    <p>
                                      Calculation: <code>{fact.formula}</code>
                                    </p>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {claim.citations.map((citation, index) => {
                    const source = sources[citation.source_id];
                    if (!source) return null;
                    const url = safeLink(source.url);
                    return (
                      <details key={`${source.id}-${index}`} className="v3-details">
                        <summary>
                          {source.title}
                          {source.year ? ` (${source.year})` : ""}
                        </summary>
                        <blockquote>{citation.quote}</blockquote>
                        <p>
                          {source.location} · {source.access.replaceAll("_", " ")} · library status: {source.status}
                        </p>
                        {source.doi && <p>DOI: {source.doi}</p>}
                        {url && (
                          <a href={url} target="_blank" rel="noopener noreferrer">
                            Original source
                          </a>
                        )}
                        <p>
                          Publication updates: {source.updates.replaceAll("_", " ")}; checked{" "}
                          {new Date(source.checked_at * 1000).toLocaleDateString()}
                        </p>
                        <ul>
                          {source.caveats.map((note) => (
                            <li key={note}>{note}</li>
                          ))}
                        </ul>
                        {(audit.retrieval_grades || [])
                          .filter((grade) => grade.source_id === source.id && grade.verdict === "supported")
                          .map((grade, i) => (
                            <p key={i}>
                              Applicability: {grade.statement} {grade.limitations.join(" ")}
                            </p>
                          ))}
                      </details>
                    );
                  })}
                </section>
              ))}
          </details>
        </section>
      ))}
      {!!audit.research_gaps?.length && (
        <details className="v3-details">
          <summary>Unresolved research questions</summary>
          <ul>
            {audit.research_gaps.map((gap, index) => (
              <li key={index}>
                {gap.question.concept}: {gap.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      {!!audit.source_warnings?.length && (
        <details className="v3-details">
          <summary>Source availability notes</summary>
          <ul>
            {audit.source_warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      <details className="v3-details">
        <summary>Retrieval and review audit</summary>
        <p>{audit.index_note}</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {JSON.stringify(
            {
              input: audit.input_hash,
              registry: audit.registry_version,
              corpus: audit.corpus_version,
              calls: audit.calls,
              actions: audit.trace,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}
