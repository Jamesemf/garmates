import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import { CircleMarker, MapContainer, Polyline, TileLayer } from 'react-leaflet'
import { usePalette } from '../lib/theme'
import type { TrackPoint } from '../lib/types'

export function ActivityMap({ points, color }: { points: TrackPoint[]; color: string }) {
  const palette = usePalette()
  const path = points
    .filter((p) => p[1] !== null && p[2] !== null)
    .map((p) => [p[1], p[2]] as LatLngExpression)
  if (path.length < 2) return null
  const lats = path.map((p) => (p as [number, number])[0])
  const lons = path.map((p) => (p as [number, number])[1])
  const bounds: LatLngBoundsExpression = [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ]
  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [24, 24] }} scrollWheelZoom={false} className="h-80 w-full rounded-lg">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={path} pathOptions={{ color: palette.chrome.surface, weight: 6, opacity: 0.9 }} />
      <Polyline positions={path} pathOptions={{ color, weight: 3 }} />
      <CircleMarker center={path[0]} radius={6} pathOptions={{ color: palette.chrome.surface, weight: 2, fillColor: color, fillOpacity: 1 }} />
      <CircleMarker center={path[path.length - 1]} radius={6} pathOptions={{ color: color, weight: 2, fillColor: palette.chrome.surface, fillOpacity: 1 }} />
    </MapContainer>
  )
}
