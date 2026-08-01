import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useCallStore } from '../store/callStore';
import { LeadDrawer } from '../components/LeadDrawer';

const METRO = { west: -76, south: 39.5, east: -74.35, north: 40.61 };

export function MapPage() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const setBbox = useCallStore((s) => s.setBbox);
  const navigate = useNavigate();

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      bounds: [[METRO.west, METRO.south], [METRO.east, METRO.north]],
      fitBoundsOptions: { padding: 40 },
    });
    mapRef.current = map;

    map.on('load', async () => {
      const fc = await api.mapPoints(METRO);
      map.addSource('leads', { type: 'geojson', data: fc as never });
      map.addLayer({
        id: 'leads-heat',
        type: 'heatmap',
        source: 'leads',
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'icp_score'], 25, 0, 100, 1],
          'heatmap-intensity': 0.6,
          'heatmap-color': [
            'interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(15,20,25,0)',
            0.4, '#c45c26',
            1, '#f3ede3',
          ],
          'heatmap-radius': 18,
        },
      });
      map.addLayer({
        id: 'leads-points',
        type: 'circle',
        source: 'leads',
        paint: {
          'circle-radius': 5,
          'circle-color': [
            'match', ['get', 'status'],
            'won', '#2d6a4f',
            'meeting', '#c45c26',
            'working', '#d4734a',
            '#888',
          ],
          'circle-opacity': 0.85,
        },
      });

      map.on('click', 'leads-points', (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (f?.properties?.business_id) setSelected(String(f.properties.business_id));
      });
      map.getCanvas().style.cursor = 'pointer';
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const loadQueueFromView = () => {
    const map = mapRef.current;
    if (!map) return;
    const b = map.getBounds();
    setBbox({
      west: b.getWest(),
      south: b.getSouth(),
      east: b.getEast(),
      north: b.getNorth(),
    });
    navigate('/call');
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h1>Territory Map</h1>
          <p style={{ color: 'var(--text-muted)' }}>141k metro POIs · heat by ICP score</p>
        </div>
        <button className="btn btn-primary" onClick={loadQueueFromView}>Load view as call queue</button>
      </div>
      <div ref={containerRef} className="map-container" />
      <LeadDrawer id={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
