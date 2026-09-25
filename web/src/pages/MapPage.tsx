import { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, type CountyStat, type GeoFeature, type LeadRow } from '../api/client';
import { CategoryPicker } from '../components/CategoryPicker';
import { LeadDrawer } from '../components/LeadDrawer';
import { formatCategory, formatScore, formatStatus, SCORE_TOOLTIP } from '../lib/format';
import { useCallStore } from '../store/callStore';

type MapMode = 'overview' | 'hunt' | 'cadence' | 'campaign';

const METRO = { west: -76, south: 39.5, east: -74.35, north: 40.61 };

const COUNTIES = [
  'Philadelphia',
  'Montgomery',
  'Bucks',
  'Chester',
  'Delaware',
  'Camden',
  'Burlington',
  'Gloucester',
] as const;

/** Fallback fitBounds when GeoJSON feature missing */
const COUNTY_BOUNDS: Record<string, [[number, number], [number, number]]> = {
  Philadelphia: [[-75.28, 39.87], [-74.96, 40.14]],
  Montgomery: [[-75.70, 40.07], [-75.07, 40.44]],
  Bucks: [[-75.27, 40.08], [-74.71, 40.60]],
  Chester: [[-76.14, 39.72], [-75.35, 40.15]],
  Delaware: [[-75.48, 39.84], [-75.20, 40.00]],
  Camden: [[-75.13, 39.70], [-74.90, 39.98]],
  Burlington: [[-75.10, 39.75], [-74.48, 40.18]],
  Gloucester: [[-75.45, 39.50], [-74.98, 39.85]],
};

const BATCH_COLORS = ['#c45c26', '#2d6a4f', '#3d5a80', '#9b5de5', '#f4a261', '#e76f51', '#577590', '#43aa8b'];

function opportunityColor(opp: number, maxOpp: number): string {
  if (maxOpp <= 0 || opp <= 0) return 'rgba(80,90,100,0.35)';
  const t = Math.min(1, opp / maxOpp);
  const r = Math.round(80 + t * (196 - 80));
  const g = Math.round(90 + t * (92 - 90));
  const b = Math.round(100 + t * (38 - 100));
  return `rgba(${r},${g},${b},0.55)`;
}

export function MapPage() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const countiesGeoRef = useRef<{ type: string; features: Array<{ type: string; properties?: Record<string, unknown>; geometry?: { type: string; coordinates: unknown } }> } | null>(null);
  const rosterRef = useRef<HTMLDivElement>(null);

  const [mode, setMode] = useState<MapMode>('overview');
  const [county, setCountyFilter] = useState('');
  const [status, setStatus] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [minScore, setMinScore] = useState(25);
  const [batchId, setBatchId] = useState('');
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  const setBbox = useCallStore((s) => s.setBbox);
  const setCallCounty = useCallStore((s) => s.setCounty);
  const navigate = useNavigate();

  const pointMode: 'hunt' | 'cadence' | 'campaign' | 'overview' =
    mode === 'overview' ? 'hunt' : mode;

  const { data: countyData } = useQuery({
    queryKey: ['map-counties', minScore, status, categories],
    queryFn: () =>
      api.mapCounties({
        min_score: minScore,
        status: status || undefined,
        category: categories.length ? categories : undefined,
      }),
  });

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: api.campaigns,
    enabled: mode === 'campaign',
  });

  const { data: pointsData, isFetching: pointsLoading } = useQuery({
    queryKey: [
      'map-points',
      mode,
      county,
      status,
      categories,
      minScore,
      batchId,
      overdueOnly,
    ],
    queryFn: () =>
      api.mapPoints({
        ...METRO,
        mode: pointMode,
        county: county || undefined,
        status: status || undefined,
        category: categories.length ? categories : undefined,
        min_score: minScore,
        batch_id: mode === 'campaign' && batchId ? batchId : undefined,
        overdue_only: mode === 'cadence' ? overdueOnly : undefined,
        limit: 5000,
      }),
    enabled: mapReady && mode !== 'overview',
  });

  const { data: rosterData, isLoading: rosterLoading } = useQuery({
    queryKey: ['map-roster', county, status, categories, minScore],
    queryFn: () =>
      api.leads({
        page: 1,
        page_size: 50,
        county: county || undefined,
        status: status || undefined,
        category: categories.length ? categories : undefined,
        min_score: minScore,
      }),
    enabled: mode === 'hunt',
  });

  const countyStats = countyData?.items || [];

  const fitCounty = useCallback((name: string) => {
    const map = mapRef.current;
    if (!map) return;
    const feat = countiesGeoRef.current?.features.find(
      (f) => f.properties && f.properties.name === name,
    );
    if (feat?.geometry) {
      const bounds = new maplibregl.LngLatBounds();
      const walk = (coords: unknown): void => {
        if (!Array.isArray(coords)) return;
        if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
          bounds.extend(coords as [number, number]);
          return;
        }
        coords.forEach(walk);
      };
      walk(feat.geometry.coordinates);
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 48, duration: 600 });
        return;
      }
    }
    const fallback = COUNTY_BOUNDS[name];
    if (fallback) map.fitBounds(fallback, { padding: 48, duration: 600 });
  }, []);

  const paintCounties = useCallback(
    (stats: CountyStat[]) => {
      const map = mapRef.current;
      if (!map?.getSource('counties')) return;
      const byName = Object.fromEntries(stats.map((s) => [s.county, s]));
      const max = Math.max(1, ...stats.map((s) => s.opportunity || 0));
      const base = countiesGeoRef.current;
      if (!base) return;
      const colored = {
        type: 'FeatureCollection' as const,
        features: base.features.map((f) => {
          const name = String(f.properties?.name || '');
          const st = byName[name];
          return {
            ...f,
            properties: {
              ...f.properties,
              opportunity: st?.opportunity ?? 0,
              lead_count: st?.lead_count ?? 0,
              fill: opportunityColor(st?.opportunity ?? 0, max),
            },
          };
        }),
      };
      (map.getSource('counties') as maplibregl.GeoJSONSource).setData(colored as never);
    },
    [],
  );

  const applyPointStyle = useCallback((map: maplibregl.Map, m: MapMode) => {
    if (!map.getLayer('leads-points')) return;
    if (m === 'cadence') {
      map.setPaintProperty('leads-points', 'circle-color', [
        'case',
        ['==', ['get', 'overdue'], true],
        '#c45c26',
        ['==', ['get', 'overdue'], 1],
        '#c45c26',
        '#5a6570',
      ]);
      map.setPaintProperty('leads-points', 'circle-opacity', [
        'case',
        ['any', ['==', ['get', 'overdue'], true], ['==', ['get', 'overdue'], 1]],
        0.95,
        0.45,
      ]);
      map.setPaintProperty('leads-heat', 'visibility', 'none');
    } else if (m === 'campaign') {
      map.setPaintProperty('leads-points', 'circle-color', [
        'case',
        ['==', ['typeof', ['get', 'batch_id']], 'string'],
        '#c45c26',
        '#666',
      ]);
      map.setPaintProperty('leads-points', 'circle-opacity', 0.85);
      map.setPaintProperty('leads-heat', 'visibility', 'none');
    } else {
      map.setPaintProperty('leads-points', 'circle-color', [
        'match',
        ['get', 'status'],
        'won',
        '#2d6a4f',
        'meeting',
        '#c45c26',
        'working',
        '#d4734a',
        '#888',
      ]);
      map.setPaintProperty('leads-points', 'circle-opacity', 0.85);
      map.setPaintProperty('leads-heat', 'visibility', m === 'overview' ? 'none' : 'visible');
    }
  }, []);

  // Init map once — keep MapLibre 5.x; layers only after `load`
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      bounds: [
        [METRO.west, METRO.south],
        [METRO.east, METRO.north],
      ],
      fitBoundsOptions: { padding: 40 },
    });
    mapRef.current = map;

    map.on('load', async () => {
      let countiesGeo: NonNullable<typeof countiesGeoRef.current> = {
        type: 'FeatureCollection',
        features: [],
      };
      try {
        const res = await fetch('/geo/metro-counties.geojson');
        countiesGeo = (await res.json()) as NonNullable<typeof countiesGeoRef.current>;
      } catch {
        /* COUNTY_BOUNDS still works for fit */
      }
      countiesGeoRef.current = countiesGeo;

      map.addSource('counties', { type: 'geojson', data: countiesGeo as never });
      map.addLayer({
        id: 'counties-fill',
        type: 'fill',
        source: 'counties',
        paint: {
          'fill-color': ['coalesce', ['get', 'fill'], 'rgba(80,90,100,0.35)'],
          'fill-opacity': 0.85,
        },
      });
      map.addLayer({
        id: 'counties-line',
        type: 'line',
        source: 'counties',
        paint: {
          'line-color': '#f3ede3',
          'line-width': 1.2,
          'line-opacity': 0.55,
        },
      });

      map.addSource('leads', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: 'leads-heat',
        type: 'heatmap',
        source: 'leads',
        layout: { visibility: 'none' },
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'icp_score'], 25, 0, 100, 1],
          'heatmap-intensity': 0.6,
          'heatmap-color': [
            'interpolate',
            ['linear'],
            ['heatmap-density'],
            0,
            'rgba(15,20,25,0)',
            0.4,
            '#c45c26',
            1,
            '#f3ede3',
          ],
          'heatmap-radius': 18,
        },
      });
      map.addLayer({
        id: 'leads-points',
        type: 'circle',
        source: 'leads',
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': 5,
          'circle-color': '#888',
          'circle-opacity': 0.85,
        },
      });

      map.on('click', 'counties-fill', (e) => {
        const name = e.features?.[0]?.properties?.name;
        if (!name) return;
        setCountyFilter(String(name));
        setMode('hunt');
        fitCounty(String(name));
      });

      map.on('click', 'leads-points', (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (f?.properties?.business_id) {
          const id = String(f.properties.business_id);
          setSelected(id);
          const row = rosterRef.current?.querySelector(`[data-bid="${id}"]`);
          row?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
      });

      map.on('mouseenter', 'counties-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'counties-fill', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', 'leads-points', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'leads-points', () => {
        map.getCanvas().style.cursor = '';
      });

      setMapReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [fitCounty]);

  // Paint choropleth when stats arrive
  useEffect(() => {
    if (!mapReady) return;
    paintCounties(countyStats);
  }, [mapReady, countyStats, paintCounties]);

  // Toggle layer visibility by mode
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map?.getLayer('counties-fill')) return;
    const showCounties = mode === 'overview';
    const showPoints = mode !== 'overview';
    map.setLayoutProperty('counties-fill', 'visibility', showCounties ? 'visible' : 'none');
    map.setLayoutProperty('counties-line', 'visibility', showCounties ? 'visible' : 'none');
    map.setLayoutProperty('leads-points', 'visibility', showPoints ? 'visible' : 'none');
    map.setLayoutProperty('leads-heat', 'visibility', mode === 'hunt' ? 'visible' : 'none');
    applyPointStyle(map, mode);
  }, [mode, mapReady, applyPointStyle]);

  // Push point GeoJSON
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map?.getSource('leads') || mode === 'overview') return;
    const fc = pointsData || { type: 'FeatureCollection', features: [] as GeoFeature[] };

    // Campaign: color by batch_id categorically via feature-state isn't available easily;
    // rewrite circle-color with match when we know batch ids
    if (mode === 'campaign' && fc.features?.length) {
      const batches = [
        ...new Set(
          fc.features
            .map((f) => f.properties?.batch_id)
            .filter((b): b is string => typeof b === 'string' && b.length > 0),
        ),
      ].slice(0, BATCH_COLORS.length);
      const matchExpr: unknown[] = ['match', ['get', 'batch_id']];
      batches.forEach((b, i) => {
        matchExpr.push(b, BATCH_COLORS[i]);
      });
      matchExpr.push('#666');
      map.setPaintProperty('leads-points', 'circle-color', matchExpr as never);
    } else {
      applyPointStyle(map, mode);
    }

    (map.getSource('leads') as maplibregl.GeoJSONSource).setData(fc as never);
  }, [pointsData, mode, mapReady, applyPointStyle]);

  const selectCountyCard = (name: string) => {
    setCountyFilter(name);
    setMode('hunt');
    fitCounty(name);
  };

  const workTerritory = () => {
    const map = mapRef.current;
    if (county) {
      setCallCounty(county);
      const bounds = COUNTY_BOUNDS[county];
      if (bounds) {
        setBbox({
          west: bounds[0][0],
          south: bounds[0][1],
          east: bounds[1][0],
          north: bounds[1][1],
        });
      } else if (map) {
        const b = map.getBounds();
        setBbox({
          west: b.getWest(),
          south: b.getSouth(),
          east: b.getEast(),
          north: b.getNorth(),
        });
      }
    } else if (map) {
      setCallCounty(null);
      const b = map.getBounds();
      setBbox({
        west: b.getWest(),
        south: b.getSouth(),
        east: b.getEast(),
        north: b.getNorth(),
      });
    }
    navigate('/call');
  };

  const roster = rosterData?.items || [];
  const pointCount = pointsData?.features?.length ?? 0;

  return (
    <div className="territory-page">
      <div className="territory-header">
        <div>
          <h1>Territory Map</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            County regions · {mode === 'overview' ? 'opportunity choropleth' : `${pointCount.toLocaleString()} pins`}
            {pointsLoading ? ' · loading…' : ''}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={workTerritory}>
          Work this territory
        </button>
      </div>

      <div className="mode-tabs" role="tablist">
        {(
          [
            ['overview', 'Overview'],
            ['hunt', 'Hunt'],
            ['cadence', 'Cadence'],
            ['campaign', 'Campaign'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            className={`mode-tab${mode === id ? ' active' : ''}`}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="filters-row">
        <select value={county} onChange={(e) => {
          const v = e.target.value;
          setCountyFilter(v);
          if (v) fitCounty(v);
        }}
        >
          <option value="">All counties</option>
          {COUNTIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <CategoryPicker value={categories} onChange={setCategories} callableOnly={false} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {['new', 'working', 'meeting', 'won', 'dead'].map((s) => (
            <option key={s} value={s}>{formatStatus(s)}</option>
          ))}
        </select>
        <label className="filter-inline">
          Min ICP
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value) || 0)}
            style={{ width: 72 }}
          />
        </label>
        {mode === 'cadence' && (
          <label className="filter-inline">
            <input
              type="checkbox"
              checked={overdueOnly}
              onChange={(e) => setOverdueOnly(e.target.checked)}
            />
            Overdue only
          </label>
        )}
        {mode === 'campaign' && (
          <select value={batchId} onChange={(e) => setBatchId(e.target.value)}>
            <option value="">All batches</option>
            {(campaigns?.items || []).map((b) => (
              <option key={b.batch_id} value={b.batch_id}>
                {b.batch_id} ({b.total})
              </option>
            ))}
          </select>
        )}
      </div>

      {mode === 'overview' && (
        <div className="county-cards">
          {countyStats.map((c) => (
            <button
              key={c.county}
              type="button"
              className={`kpi-card county-card${county === c.county ? ' selected' : ''}`}
              onClick={() => selectCountyCard(c.county)}
            >
              <div className="label">{c.county}</div>
              <div className="value">{c.lead_count.toLocaleString()}</div>
              <div className="county-card-meta">
                <span title={SCORE_TOOLTIP}>Avg ICP {formatScore(c.avg_icp)}</span>
                <span>{c.untouched_pct}% new</span>
                <span>{c.overdue_count} overdue</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {(mode === 'cadence' || mode === 'campaign') && (
        <div className="map-legend">
          {mode === 'cadence' ? (
            <>
              <span><i style={{ background: '#c45c26' }} /> Overdue</span>
              <span><i style={{ background: '#5a6570' }} /> On cadence / untouched</span>
            </>
          ) : (
            <>
              <span><i style={{ background: '#c45c26' }} /> In a batch</span>
              <span><i style={{ background: '#666' }} /> Unbatched</span>
            </>
          )}
        </div>
      )}

      <div className={`territory-layout${mode === 'hunt' ? ' with-roster' : ''}`}>
        <div ref={containerRef} className="map-container territory-map" />
        {mode === 'hunt' && (
          <div className="territory-roster" ref={rosterRef}>
            <div className="roster-head">
              <strong>{county || 'Metro'}</strong>
              <span style={{ color: 'var(--text-muted)' }}>
                {rosterLoading ? 'Loading…' : `${roster.length} leads`}
              </span>
            </div>
            <ul className="roster-list">
              {roster.map((row: LeadRow) => (
                <li key={row.business_id}>
                  <button
                    type="button"
                    data-bid={row.business_id}
                    className={`roster-row${selected === row.business_id ? ' selected' : ''}`}
                    onClick={() => setSelected(row.business_id)}
                  >
                    <div className="roster-name">{row.name}</div>
                    <div className="roster-meta">
                      {formatCategory(row.category)} ·{' '}
                      <span title={SCORE_TOOLTIP}>{formatScore(row.icp_score)}</span>
                      {' · '}
                      {formatStatus(row.status || '')}
                    </div>
                  </button>
                </li>
              ))}
              {!rosterLoading && roster.length === 0 && (
                <li className="roster-empty">No leads for these filters</li>
              )}
            </ul>
          </div>
        )}
      </div>

      <LeadDrawer id={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
