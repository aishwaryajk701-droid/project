import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet-draw";

// leaflet-draw 1.0.x ships a `readableArea` implementation that references an
// undeclared `type` variable, which throws under ES modules / strict mode the
// moment a polygon vertex is placed with showArea enabled. Override it.
const GeometryUtil = (L as unknown as {
  GeometryUtil: { readableArea: (a: number, metric: boolean, precision?: unknown) => string };
}).GeometryUtil;
GeometryUtil.readableArea = function (area: number, isMetric: boolean): string {
  if (!isMetric) {
    const acres = area * 0.000247105;
    return `${acres.toFixed(2)} acres`;
  }
  if (area >= 10000) return `${(area * 0.0001).toFixed(2)} ha`;
  return `${Math.round(area)} m²`;
};
import { Layers, Locate, Search, Trash2, Maximize2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiGet } from "@/lib/api";
import { formatHa, polygonAreaHa, bboxOf } from "@/lib/geo";
import type { GeocodeResult } from "@/lib/types";
import { toast } from "sonner";

export interface MapLayerToggle {
  id: string;
  label: string;
  color: string;
  visible: boolean;
}

interface Props {
  onBoundary?: (coords: number[][] | null) => void;
  initialCoordinates?: number[][] | null;
  height?: number | string;
  readOnly?: boolean;
  extraPolygons?: { coordinates: number[][]; color: string; label: string }[];
  overlayPngB64?: string | null;
  overlayOpacity?: number;
}

export default function AgriGisMap({
  onBoundary,
  initialCoordinates = null,
  height = 560,
  readOnly = false,
  extraPolygons = [],
  overlayPngB64 = null,
  overlayOpacity = 0.7,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const drawnRef = useRef<L.FeatureGroup | null>(null);
  const overlayRef = useRef<L.ImageOverlay | null>(null);
  const [boundary, setBoundary] = useState<number[][] | null>(initialCoordinates);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { center: [20.5937, 78.9629], zoom: 5, zoomControl: true });
    mapRef.current = map;

    const sat = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Tiles &copy; Esri", maxZoom: 19 },
    );
    const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    });
    const terrain = L.tileLayer("https://a.tile.opentopomap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenTopoMap",
    });
    sat.addTo(map);
    L.control.layers(
      { Satellite: sat, Streets: streets, "Terrain / DEM": terrain },
      {},
      { position: "topleft" },
    ).addTo(map);

    const drawn = new L.FeatureGroup();
    drawnRef.current = drawn;
    map.addLayer(drawn);

    if (!readOnly) {
      const drawControl = new (L.Control as unknown as { Draw: new (o: unknown) => L.Control }).Draw({
        position: "topright",
        draw: {
          polygon: { allowIntersection: false, showArea: true, shapeOptions: { color: "#10B981", weight: 3, fillOpacity: 0.18 } },
          rectangle: { shapeOptions: { color: "#06B6D4", weight: 3, fillOpacity: 0.18 } },
          polyline: false, circle: false, marker: false, circlemarker: false,
        },
        edit: { featureGroup: drawn },
      });
      map.addControl(drawControl);

      const extract = (layer: L.Layer): number[][] => {
        const latlngs = (layer as L.Polygon).getLatLngs()[0] as L.LatLng[];
        const coords = latlngs.map((ll) => [ll.lng, ll.lat]);
        if (coords.length && (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1])) {
          coords.push(coords[0]);
        }
        return coords;
      };
      map.on(L.Draw.Event.CREATED, (e: L.LeafletEvent) => {
        drawn.clearLayers();
        const layer = (e as unknown as { layer: L.Layer }).layer;
        drawn.addLayer(layer);
        const coords = extract(layer);
        setBoundary(coords);
        onBoundary?.(coords);
      });
      map.on(L.Draw.Event.EDITED, () => {
        const layers = drawn.getLayers();
        if (layers.length) {
          const coords = extract(layers[0]);
          setBoundary(coords);
          onBoundary?.(coords);
        }
      });
      map.on(L.Draw.Event.DELETED, () => {
        setBoundary(null);
        onBoundary?.(null);
      });
    }

    if (initialCoordinates && initialCoordinates.length >= 3) {
      const poly = L.polygon(initialCoordinates.map((c) => [c[1], c[0]] as [number, number]), {
        color: "#10B981", weight: 3, fillOpacity: 0.18,
      });
      drawn.addLayer(poly);
      map.fitBounds(poly.getBounds(), { padding: [30, 30] });
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // extra context polygons (rivers, buildings, flood mask outlines)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const group = L.layerGroup().addTo(map);
    extraPolygons.forEach((p) => {
      if (p.coordinates.length >= 3) {
        L.polygon(p.coordinates.map((c) => [c[1], c[0]] as [number, number]), {
          color: p.color, weight: 2, fillOpacity: 0.25,
        }).bindTooltip(p.label).addTo(group);
      }
    });
    return () => { group.remove(); };
  }, [extraPolygons]);

  // flood-mask style raster overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (overlayRef.current) {
      overlayRef.current.remove();
      overlayRef.current = null;
    }
    if (overlayPngB64 && boundary && boundary.length >= 3) {
      const [minLng, minLat, maxLng, maxLat] = bboxOf(boundary);
      overlayRef.current = L.imageOverlay(
        `data:image/png;base64,${overlayPngB64}`,
        [[minLat, minLng], [maxLat, maxLng]],
        { opacity: overlayOpacity },
      ).addTo(map);
    }
  }, [overlayPngB64, overlayOpacity, boundary]);

  const locate = () => {
    if (!navigator.geolocation) {
      toast.error("Geolocation is not available in this browser");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        mapRef.current?.flyTo([pos.coords.latitude, pos.coords.longitude], 15, { duration: 1.1 });
        L.marker([pos.coords.latitude, pos.coords.longitude]).addTo(mapRef.current!);
        toast.success("Centred on your current location");
      },
      () => toast.error("Could not read your GPS position"),
      { enableHighAccuracy: true, timeout: 9000 },
    );
  };

  const search = async () => {
    if (query.trim().length < 3) {
      toast.error("Type at least 3 characters to search");
      return;
    }
    setSearching(true);
    try {
      const data = await apiGet<{ results: GeocodeResult[] }>(`/satellite/geocode?q=${encodeURIComponent(query)}`);
      setResults(data.results);
      if (!data.results.length) toast.warning("No matching place found");
    } catch {
      toast.error("Place search unavailable right now");
    } finally {
      setSearching(false);
    }
  };

  const clearAll = () => {
    drawnRef.current?.clearLayers();
    setBoundary(null);
    onBoundary?.(null);
  };

  const area = boundary ? polygonAreaHa(boundary) : 0;
  const bbox = boundary ? bboxOf(boundary) : null;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-[#1E3A2B] shadow-2xl shadow-black/50"
         style={{ height }} data-testid="agri-gis-map">
      <div ref={containerRef} className="w-full h-full" />

      {!readOnly && (
        <div className="absolute left-1/2 -translate-x-1/2 top-3 z-[500] w-[min(420px,80%)]">
          <div className="flex gap-2 backdrop-blur-xl bg-[#0B130E]/85 border border-emerald-500/20 rounded-xl p-2 shadow-2xl">
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") search(); }}
                   placeholder="Search a village, district or landmark"
                   data-testid="map-search-input"
                   className="h-9 bg-[#0B130E] border-[#1E3A2B] text-sm" />
            <Button size="sm" onClick={search} disabled={searching} data-testid="map-search-btn">
              <Search className="w-4 h-4" />
            </Button>
          </div>
          {results.length > 0 && (
            <div className="mt-1 backdrop-blur-xl bg-[#0B130E]/95 border border-[#1E3A2B] rounded-xl overflow-hidden max-h-56 overflow-y-auto custom-scrollbar"
                 data-testid="map-search-results">
              {results.map((r, i) => (
                <button key={i} data-testid={`map-search-result-${i}`}
                        onClick={() => { mapRef.current?.flyTo([r.lat, r.lng], 14, { duration: 1 }); setResults([]); }}
                        className="w-full text-left px-3 py-2 text-xs hover:bg-emerald-500/10 border-b border-[#1E3A2B] last:border-0 transition-colors">
                  {r.display_name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="absolute right-3 bottom-3 z-[500] flex flex-col gap-2">
        <Button size="sm" variant="secondary" onClick={locate} data-testid="map-locate-btn"
                className="backdrop-blur-xl bg-[#0B130E]/85 border border-emerald-500/20">
          <Locate className="w-4 h-4 mr-1" /> GPS
        </Button>
        {!readOnly && (
          <Button size="sm" variant="secondary" onClick={clearAll} data-testid="map-clear-btn"
                  className="backdrop-blur-xl bg-[#0B130E]/85 border border-red-500/20 text-red-300">
            <Trash2 className="w-4 h-4 mr-1" /> Clear
          </Button>
        )}
        <Button size="sm" variant="secondary" data-testid="map-fullscreen-btn"
                onClick={() => containerRef.current?.parentElement?.requestFullscreen?.()}
                className="backdrop-blur-xl bg-[#0B130E]/85 border border-emerald-500/20">
          <Maximize2 className="w-4 h-4" />
        </Button>
      </div>

      <div className="absolute left-3 bottom-3 z-[500] backdrop-blur-xl bg-[#0B130E]/85 border border-emerald-500/20 rounded-xl px-3 py-2 text-[11px] font-mono text-emerald-100/90 shadow-2xl max-w-[320px]"
           data-testid="map-boundary-readout">
        <div className="flex items-center gap-2 mb-1 text-emerald-400">
          {boundary ? <Layers className="w-3 h-3" /> : <Pencil className="w-3 h-3" />}
          <span className="tracking-[0.18em] uppercase text-[9px]">
            {boundary ? "Boundary set" : "Draw boundary"}
          </span>
        </div>
        {boundary ? (
          <>
            <div data-testid="map-area-ha">{formatHa(area)} · {(area * 10000).toFixed(0)} m²</div>
            <div className="text-emerald-100/60">{boundary.length - 1} vertices</div>
            {bbox && (
              <div className="text-emerald-100/50 mt-0.5" data-testid="map-bbox">
                bbox {bbox.map((v) => v.toFixed(4)).join(", ")}
              </div>
            )}
          </>
        ) : (
          <div className="text-emerald-100/60">Use the polygon or rectangle tool (top-right)</div>
        )}
      </div>
    </div>
  );
}
