import React, { useMemo, useState } from 'react';
import './WebSearchBlock.css';

function prettyHost(host, url) {
  if (typeof host === 'string' && host.trim()) return host.trim();
  try {
    const u = new URL(String(url || ''));
    const h = (u.hostname || '').replace(/^www\./i, '');
    return h || 'source';
  } catch (e) {
    return 'source';
  }
}

function WebSearchBlock({ searches }) {
  const [expanded, setExpanded] = useState(false);

  const safeSearches = useMemo(() => {
    if (!Array.isArray(searches)) return [];
    return searches
      .map((s) => {
        const query = typeof s?.query === 'string' ? s.query.trim() : '';
        const resultCount = Number.isFinite(Number(s?.result_count)) ? Number(s.result_count) : 0;
        const status = String(s?.status || '').trim().toLowerCase() || 'done';
        const results = Array.isArray(s?.results)
          ? s.results
              .map((r) => {
                const url = typeof r?.url === 'string' ? r.url.trim() : '';
                const title = typeof r?.title === 'string' && r.title.trim() ? r.title.trim() : url;
                const host = prettyHost(r?.host, url);
                return url ? { url, title, host } : null;
              })
              .filter(Boolean)
          : [];
        return {
          query: query || 'Web search',
          resultCount,
          status,
          results,
        };
      })
      .filter((s) => s.query || s.results.length > 0 || s.resultCount > 0);
  }, [searches]);

  if (safeSearches.length === 0) return null;

  return (
    <div className="web-search-block">
      <button
        type="button"
        className="web-search-header no-scale-effect"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="web-search-header-left">
          <span className="web-search-icon" aria-hidden="true">◎</span>
          <span className="web-search-title">Searched the web</span>
        </span>
        <span className={`web-search-chevron ${expanded ? 'is-open' : ''}`} aria-hidden="true">›</span>
      </button>

      {expanded && (
        <div className="web-search-body">
          {safeSearches.map((search, idx) => (
            <section className="web-search-group" key={`${search.query}-${idx}`}>
              <div className="web-search-group-head">
                <span className="web-search-group-icon" aria-hidden="true">◎</span>
                <span className="web-search-query">{search.query}</span>
                <span className="web-search-count">
                  {search.status === 'done' ? `${search.resultCount} results` : 'searching'}
                </span>
              </div>

              {search.results.length > 0 && (
                <div className="web-search-result-list">
                  {search.results.map((r, i) => (
                    <a
                      key={`${r.url}-${i}`}
                      className="web-search-result-item"
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={r.url}
                    >
                      <span className="web-search-result-title">{r.title}</span>
                      <span className="web-search-result-host">{r.host}</span>
                    </a>
                  ))}
                </div>
              )}
            </section>
          ))}

          <div className="web-search-done">
            <span className="web-search-done-icon" aria-hidden="true">◉</span>
            <span>Done</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default WebSearchBlock;
