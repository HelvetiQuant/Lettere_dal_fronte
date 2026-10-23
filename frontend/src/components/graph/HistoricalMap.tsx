import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface MapLocation {
  name: string;
  lat: number;
  lon: number;
  role: string;
  verification: string;
  label_number: number;
  source_ids?: string[];
}

export interface MapLine {
  name: string;
  points: { lat: number; lon: number }[];
  style: string;
  line_type: string;
  color: string;
  verification: string;
}

export interface MapMovement {
  name: string;
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  movement_type: string;
  verification: string;
}

export interface MapPhase {
  name: string;
  start_date: string;
  end_date: string;
  color: string;
  description: string;
}

export interface MapSubMap {
  title: string;
  svg: string;
  locations: MapLocation[];
  lines: MapLine[];
  movements: MapMovement[];
  is_partial: boolean;
  partial_note: string;
}

interface HistoricalMapProps {
  locations: MapLocation[];
  lines: MapLine[];
  movements: MapMovement[];
  phases?: MapPhase[];
  subMaps?: MapSubMap[];
  title?: string;
  isPartial?: boolean;
  partialNote?: string;
}

const VERIFICATION_COLORS: Record<string, string> = {
  verified: '#2196F3',
  probable: '#FF9800',
  hypothetical: '#999',
};

const ROLE_ICONS: Record<string, L.DivIconOptions> = {
  battlefield: { html: '⚔', className: 'map-icon battlefield' },
  casualty_site: { html: '✝', className: 'map-icon casualty' },
  camp: { html: '⌂', className: 'map-icon camp' },
  mentioned: { html: '•', className: 'map-icon mentioned' },
};

function createLabelIcon(label: number, color: string, role: string): L.DivIcon {
  const iconHtml = ROLE_ICONS[role]?.html || '•';
  return L.divIcon({
    className: 'historical-map-marker',
    html: `<div style="display:flex;align-items:center;gap:2px;">
      <div style="width:24px;height:24px;border-radius:50%;background:${color};border:2px solid white;display:flex;align-items:center;justify-content:center;font-size:11px;color:white;font-weight:bold;box-shadow:0 1px 3px rgba(0,0,0,0.4);">${label}</div>
      <div style="font-size:12px;color:${color};font-weight:bold;text-shadow:1px 1px 2px white,-1px -1px 2px white;">${iconHtml}</div>
    </div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

export function HistoricalMap({
  locations,
  lines,
  movements,
  phases = [],
  subMaps = [],
  title,
  isPartial = false,
  partialNote = '',
}: HistoricalMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current) return;

    // Clean up any existing Leaflet instance on this container (HMR/StrictMode safe)
    if (mapInstance.current) {
      mapInstance.current.remove();
      mapInstance.current = null;
    }
    // Also clear any leftover _leaflet_id from a previous mount
    if (mapRef.current._leaflet_id) {
      delete mapRef.current._leaflet_id;
    }

    const map = L.map(mapRef.current, {
      center: [46.0, 13.5],
      zoom: 8,
      scrollWheelZoom: true,
    });

    // OpenStreetMap tiles (free)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18,
    }).addTo(map);

    // Draw lines (front lines)
    for (const line of lines) {
      if (!line.points || line.points.length < 2) continue;
      const latlngs = line.points
        .filter(p => p && typeof p.lat === 'number' && typeof p.lon === 'number')
        .map(p => [p.lat, p.lon] as [number, number]);
      if (latlngs.length < 2) continue;
      const dashArray = line.style === 'dashed' ? '8,4' : line.style === 'dotted' ? '2,4' : undefined;
      L.polyline(latlngs, {
        color: line.color || '#333',
        weight: 3,
        opacity: 0.7,
        dashArray,
      }).addTo(map).bindTooltip(line.name, { permanent: false });
    }

    // Draw movements (arrows)
    for (const mov of movements) {
      if (typeof mov.from_lat !== 'number' || typeof mov.from_lon !== 'number' ||
          typeof mov.to_lat !== 'number' || typeof mov.to_lon !== 'number') continue;
      const from: [number, number] = [mov.from_lat, mov.from_lon];
      const to: [number, number] = [mov.to_lat, mov.to_lon];
      const color = mov.movement_type === 'advance' ? '#2196F3' : mov.movement_type === 'retreat' ? '#F44336' : '#FF9800';
      const dashArray = mov.verification === 'probable' ? '8,4' : mov.verification === 'hypothetical' ? '2,4' : undefined;

      L.polyline([from, to], {
        color,
        weight: 3,
        opacity: 0.8,
        dashArray,
      }).addTo(map).bindTooltip(`${mov.name} (${mov.movement_type})`, { permanent: false });

      // Arrowhead at destination
      const angle = Math.atan2(to[0] - from[0], to[1] - from[1]) * 180 / Math.PI;
      const arrowIcon = L.divIcon({
        className: 'movement-arrow',
        html: `<div style="transform:rotate(${-angle}deg);font-size:20px;color:${color};text-shadow:1px 1px 2px white;">➤</div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });
      L.marker(to, { icon: arrowIcon, interactive: false }).addTo(map);
    }

    // Draw location markers
    const bounds = L.latLngBounds([]);
    for (const loc of locations) {
      if (typeof loc.lat !== 'number' || typeof loc.lon !== 'number') continue;
      const color = VERIFICATION_COLORS[loc.verification] || '#999';
      const icon = createLabelIcon(loc.label_number, color, loc.role);
      const marker = L.marker([loc.lat, loc.lon], { icon }).addTo(map);
      const popupHtml = `
        <div style="min-width:180px;">
          <strong>${loc.name}</strong><br/>
          <span style="color:${color};font-size:11px;">${loc.verification}</span><br/>
          <span style="font-size:11px;color:#666;">Ruolo: ${loc.role}</span><br/>
          <span style="font-size:11px;color:#666;">${loc.lat.toFixed(4)}°N, ${loc.lon.toFixed(4)}°E</span>
          ${loc.source_ids && loc.source_ids.length ? `<br/><span style="font-size:10px;color:#999;">Fonti: ${loc.source_ids.join(', ')}</span>` : ''}
        </div>
      `;
      marker.bindPopup(popupHtml);
      marker.bindTooltip(`${loc.label_number}. ${loc.name}`, { permanent: false, direction: 'top' });
      bounds.extend([loc.lat, loc.lon]);
    }

    // Fit bounds
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [50, 50] });
    }

    mapInstance.current = map;

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [locations, lines, movements]);

  return (
    <div style={{ width: '100%' }}>
      {isPartial && (
        <div style={{
          borderLeft: '3px solid #FF9800',
          paddingLeft: '12px',
          marginBottom: '8px',
          background: '#FFF3E0',
          padding: '8px 12px',
          borderRadius: '4px',
        }}>
          <strong style={{ color: '#E65100' }}>⚠ Mappa parziale</strong>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#666' }}>{partialNote}</p>
        </div>
      )}
      {title && (
        <div style={{ marginBottom: '8px', fontWeight: 600, fontSize: '14px' }}>{title}</div>
      )}
      <div
        ref={mapRef}
        style={{
          width: '100%',
          height: '600px',
          borderRadius: '6px',
          border: '1px solid #ddd',
          zIndex: 0,
        }}
      />
      {phases.length > 0 && (
        <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
          {phases.map((phase, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: 14, height: 14, borderRadius: '50%', background: phase.color }} />
              <div>
                <strong style={{ fontSize: '13px' }}>{phase.name}</strong>
                <span style={{ fontSize: '11px', color: '#666' }}> — {phase.start_date} → {phase.end_date}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
