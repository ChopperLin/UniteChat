import React, { useMemo, useState } from 'react';
import './WebSearchBlock.css';

function GlobeIcon({ size = 14, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.4" />
      <ellipse cx="8" cy="8" rx="3" ry="6" stroke={color} strokeWidth="1.3" />
      <path d="M2.2 6.5H13.8M2.2 9.5H13.8" stroke={color} strokeWidth="1.3" />
    </svg>
  );
}

function ChevronIcon({ size = 16, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <path d="M6 3.5L10.5 8L6 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckCircleIcon({ size = 14, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5" />
      <path d="M5.5 8L7.2 9.8L10.5 6.2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

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
          <span className="web-search-icon" aria-hidden="true"><GlobeIcon size={14} /></span>
          <span className="web-search-title">Searched the web</span>
        </span>
        <span className={`web-search-chevron ${expanded ? 'is-open' : ''}`} aria-hidden="true"><ChevronIcon size={14} /></span>
      </button>

      <div className={`web-search-collapse ${expanded ? 'is-open' : ''}`} aria-hidden={!expanded}>
        <div className="web-search-collapse-inner">
          <div className="web-search-body">
            {safeSearches.map((search, idx) => (
              <section className="web-search-group" key={`${search.query}-${idx}`}>
                <div className="web-search-group-head">
                  <span className="web-search-group-icon" aria-hidden="true"><GlobeIcon size={12} /></span>
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
              <span className="web-search-done-icon" aria-hidden="true"><CheckCircleIcon size={12} /></span>
              <span>Done</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default WebSearchBlock;
