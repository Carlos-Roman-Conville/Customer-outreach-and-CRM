import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { formatCategory } from '../lib/format';

interface CategoryPickerProps {
  value: string[];
  onChange: (next: string[]) => void;
  callableOnly?: boolean;
}

export function CategoryPicker({ value, onChange, callableOnly = true }: CategoryPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const { data: listData, isLoading } = useQuery({
    queryKey: ['meta-categories', debounced, callableOnly],
    queryFn: () => api.metaCategories({ q: debounced || undefined, limit: 50, callable_only: callableOnly }),
    enabled: open,
  });

  const { data: countData } = useQuery({
    queryKey: ['category-count', value],
    queryFn: () => api.categoryCount(value),
    enabled: value.length > 0,
  });

  const toggle = (cat: string) => {
    if (value.includes(cat)) {
      onChange(value.filter((c) => c !== cat));
    } else {
      onChange([...value, cat]);
    }
  };

  const label = value.length === 0
    ? 'All categories'
    : value.length === 1
      ? formatCategory(value[0])
      : `${value.length} selected`;

  return (
    <div className="category-picker" ref={rootRef}>
      <button
        type="button"
        className="btn btn-ghost category-picker-trigger"
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>

      {value.length > 0 && (
        <div className="category-chips">
          {value.map((cat) => (
            <span key={cat} className="category-chip">
              {formatCategory(cat)}
              <button type="button" aria-label={`Remove ${cat}`} onClick={() => toggle(cat)}>×</button>
            </span>
          ))}
        </div>
      )}

      {value.length > 0 && countData && (
        <p className="category-count-hint">
          {countData.total.toLocaleString()} dialable · {countData.with_email.toLocaleString()} with email
        </p>
      )}

      {open && (
        <div className="category-picker-panel">
          <input
            type="search"
            placeholder="Search categories…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
          <div className="category-picker-list">
            {isLoading && <p className="category-picker-empty">Loading…</p>}
            {!isLoading && (listData?.items || []).length === 0 && (
              <p className="category-picker-empty">No categories match</p>
            )}
            {(listData?.items || []).map((row) => (
              <label key={row.category} className="category-picker-row">
                <input
                  type="checkbox"
                  checked={value.includes(row.category)}
                  onChange={() => toggle(row.category)}
                />
                <span className="category-picker-name">{formatCategory(row.category)}</span>
                <span className="category-picker-count">{row.total.toLocaleString()}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
