import L from "leaflet";
import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import { Button } from "@/components/ui/button";
import { MapZoomControls } from "@/components/ui/map-zoom-controls";
import { type MapCoordinates } from "@/types/project";
import { useEventBridge, useGameStateManager } from "@/context/game-state";

interface MapLayer {
  url: string;
  attribution: string;
}

interface MapClickHandlerProps {
  onPositionSelect: (position: MapCoordinates) => void;
}

const mapLayer: MapLayer = {
  url: "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}{r}.png",
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};

function MapClickHandler({ onPositionSelect }: MapClickHandlerProps) {
  useMapEvents({
    click(e) {
      onPositionSelect(e.latlng);
    },
  });

  return null;
}

function MapResizer() {
  const map = useMap();

  useEffect(() => {
    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });

    const mapContainer = map.getContainer();
    resizeObserver.observe(mapContainer);

    return () => {
      resizeObserver.disconnect();
    };
  }, [map]);

  return null;
}

export default function MapViewer() {
  const [position, setPosition] = useState<MapCoordinates | null>(null);
  const gameStateManager = useGameStateManager();
  const eventBridge = useEventBridge();

  const handleSubmit = () => {
    if (!position) {
      return;
    }
    gameStateManager.calculateResult(position);
    eventBridge.emit("resultSubmitted", {});
  };

  const selectedLocationIcon = L.divIcon({
    html: `
      <svg width="32" height="32" viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
        fill="var(--main)">
          <path d="M12.56 20.82a.96.96 0 0 1-1.12 0C6.611 17.378 1.486 10.298 6.667 5.182A7.6 7.6 0 0 1 12 3c2 0 3.919.785 5.333 2.181 5.181 5.116.056 12.196-4.773 15.64" />
          <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4" />
      </svg>
    `,
    className: "custom-mappin-icon",
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -32],
  });

  return (
    <>
      <MapContainer
        center={[51.505, -0.09]}
        zoom={2}
        minZoom={2}
        maxZoom={18}
        zoomControl={false}
        attributionControl={false}
        style={{ height: "100%", width: "100%", cursor: "default" }}>
        <TileLayer url={mapLayer.url} attribution={mapLayer.attribution} />
        <MapClickHandler onPositionSelect={setPosition} />
        <MapResizer />
        {position && <Marker position={position} icon={selectedLocationIcon} />}
        <MapZoomControls className="absolute bottom-4 right-4 z-[999]" size="sm" />
      </MapContainer>
      <div
        style={{ opacity: position ? 1 : 0, pointerEvents: position ? "auto" : "none" }}
        className="absolute bottom-4 left-1/2 transform transition-opacity duration-200 ease-in-out -translate-x-1/2 z-[1000]">
        <Button onClick={handleSubmit} className="relative z-[1000]">
          To tutaj!
        </Button>
      </div>
    </>
  );
}
