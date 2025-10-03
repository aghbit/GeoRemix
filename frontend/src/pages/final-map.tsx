import { useEffect, useState, useRef } from "react";
import { MapContainer, TileLayer, Marker, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ArrowLeft, Trophy } from "lucide-react";
import { ButtonLarge } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MapZoomControls } from "@/components/ui/map-zoom-controls";
import { useGameStateManager } from "@/context/game-state";
import { useNavigation } from "@/lib/navigation-system/navigation-provider";
import { moduleIdMap } from "@/lib/navigation-system/types";

// Fix for default markers in React Leaflet
delete (L.Icon.Default.prototype as unknown as { _getIconUrl: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

// Create color variations for different levels
const createActualLocationIcon = (color: string) =>
  L.divIcon({
    html: `
    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24"
                      stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="${color}">
                      <path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528" />
                    </svg>
  `,
    className: "",
    iconSize: [36, 36],
    iconAnchor: [7, 33],
  });

const createGuessLocationIcon = (color: string) =>
  L.divIcon({
    html: `
    <svg width="36" height="36" viewBox="0 0 24 24"
                      xmlns="http://www.w3.org/2000/svg"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
                      fill="${color}">
                      <path d="M12.56 20.82a.96.96 0 0 1-1.12 0C6.611 17.378 1.486 10.298 6.667 5.182A7.6 7.6 0 0 1 12 3c2 0 3.919.785 5.333 2.181 5.181 5.116.056 12.196-4.773 15.64" />
                      <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4" />
                    </svg>
  `,
    className: "",
    iconSize: [36, 36],
    iconAnchor: [18, 36],
  });

const mapLayer = {
  url: "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}{r}.png",
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};

// Level colors for differentiation
const levelColors = [
  "#FF6B6B", // Red
  "#4ECDC4", // Teal
  "#45B7D1", // Blue
  "#FFA07A", // Light Salmon
  "#98D8C8", // Mint
  "#F7DC6F", // Yellow
  "#BB8FCE", // Purple
  "#85C1E2", // Sky Blue
];

interface LevelMapData {
  levelNumber: number;
  distance: number;
  actualPosition: [number, number];
  guessPosition: [number, number];
  color: string;
}

// Component to fit bounds for all markers
function MapBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap();

  useEffect(() => {
    if (positions.length > 0) {
      const bounds = L.latLngBounds(positions);
      map.fitBounds(bounds, { padding: [100, 100] });
    }
  }, [map, positions]);

  return null;
}

// Component to handle map instance and zoom operations
interface MapHandlerProps {
  onMapReady: (map: L.Map) => void;
}

function MapHandler({ onMapReady }: MapHandlerProps) {
  const map = useMap();

  useEffect(() => {
    onMapReady(map);
  }, [map, onMapReady]);

  return null;
}

export function FinalMap() {
  const { navigateTo } = useNavigation();
  const gameStateManager = useGameStateManager();
  const [levelsData, setLevelsData] = useState<LevelMapData[]>([]);
  const mapInstanceRef = useRef<L.Map | null>(null);

  useEffect(() => {
    try {
      const allResults = gameStateManager.allLevelResults;
      
      const mappedData: LevelMapData[] = allResults.map((result, index) => ({
        levelNumber: index + 1,
        distance: result.distance,
        actualPosition: [result.answerPosition.lat, result.answerPosition.lng] as [number, number],
        guessPosition: [result.submittedPosition.lat, result.submittedPosition.lng] as [number, number],
        color: levelColors[index % levelColors.length],
      }));

      setLevelsData(mappedData);
    } catch (error) {
      console.error("Error loading all level results:", error);
      // Fallback to mock data
      setLevelsData([
        {
          levelNumber: 1,
          distance: 245,
          actualPosition: [50.0619, 19.9368],
          guessPosition: [50.0643, 19.9401],
          color: levelColors[0],
        },
        {
          levelNumber: 2,
          distance: 1250,
          actualPosition: [52.2297, 21.0122],
          guessPosition: [52.2403, 21.0189],
          color: levelColors[1],
        },
      ]);
    }
  }, [gameStateManager]);

  const handleBackToResults = () => {
    navigateTo(moduleIdMap.FINAL, "final-result");
  };

  const handleShowLeaderboard = () => {
    // TODO: Implement leaderboard navigation
    console.log("Show leaderboard - to be implemented");
    alert("Tabela wyników - wkrótce!");
  };

  const formatDistance = (distance: number) => {
    if (distance < 1000) {
      return `${Math.round(distance)}m`;
    } else {
      return `${(distance / 1000).toFixed(1)} km`;
    }
  };

  const handleMarkerClick = (actualPos: [number, number], guessPos: [number, number]) => {
    if (mapInstanceRef.current) {
      const bounds = L.latLngBounds([actualPos, guessPos]);
      mapInstanceRef.current.fitBounds(bounds, { 
        padding: [100, 100],
        maxZoom: 15,
        animate: true,
        duration: 1.5 // Animation duration in seconds
      });
    }
  };

  // Get all positions for bounds calculation
  const allPositions = levelsData.flatMap((level) => [
    level.actualPosition,
    level.guessPosition,
  ]);

  if (levelsData.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-full">
        <div className="text-lg">Ładowanie mapy...</div>
      </div>
    );
  }

  return (
    <div className="flex items-center h-full justify-center min-h-full bg-background space-y-8 p-6">
      <div className="max-w-6xl w-full flex flex-col justify-center h-full space-y-8">
        {/* Map Container with Legend Card Overlay */}
        <div className="relative flex-1 h-[80%] min-h-[500px]">
          {/* Legend Card - positioned outside bounds with higher z-index */}
          <div className="absolute -top-2 z-[2000] p-0 -left-2 max-w-xs">
            <Card className="p-0 bg-secondary-background gradient">
              <CardContent className="px-3 py-2">
                <div className="space-y-3">
                  <div className="text-sm font-bold text-foreground mb-2">Legenda:</div>
                  <div className="space-y-2 text-xs max-h-64 overflow-y-auto">
                    {levelsData.map((level) => (
                      <div key={level.levelNumber} className="space-y-1">
                        <div className="flex items-center space-x-2">
                          <div
                            className="w-3 h-3 rounded-full border border-black"
                            style={{ backgroundColor: level.color }}
                          />
                          <span className="text-foreground font-bold">
                            Runda {level.levelNumber}
                          </span>
                        </div>
                        <div className="ml-5 text-muted-foreground">
                          Dystans: {formatDistance(level.distance)}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="pt-2 border-t border-border space-y-2 text-xs">
                    <div className="flex items-center space-x-2">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        stroke="black"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        fill="transparent">
                        <path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528" />
                      </svg>
                      <span className="text-foreground font-base">Faktyczna lokalizacja</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        xmlns="http://www.w3.org/2000/svg"
                        stroke="black"
                        stroke-width="1.5"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        fill="transparent">
                        <path d="M12.56 20.82a.96.96 0 0 1-1.12 0C6.611 17.378 1.486 10.298 6.667 5.182A7.6 7.6 0 0 1 12 3c2 0 3.919.785 5.333 2.181 5.181 5.116.056 12.196-4.773 15.64" />
                        <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4" />
                      </svg>
                      <span className="text-foreground font-base">Twoja odpowiedź</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Map Card */}
          <Card className="bg-secondary-background h-full gradient relative overflow-hidden p-0">
            <CardContent className="p-0 h-full">
              <div className="h-full relative">
                <MapContainer
                  center={levelsData[0].actualPosition}
                  zoom={6}
                  minZoom={2}
                  maxZoom={18}
                  style={{ height: "100%", width: "100%" }}
                  zoomControl={false}
                  attributionControl={false}>
                  <TileLayer url={mapLayer.url} attribution={mapLayer.attribution} />

                  {/* Render markers and lines for each level */}
                  {levelsData.map((level) => (
                    <div key={level.levelNumber}>
                      {/* Actual location marker */}
                      <Marker
                        position={level.actualPosition}
                        icon={createActualLocationIcon(level.color)}
                        eventHandlers={{
                          click: () => handleMarkerClick(level.actualPosition, level.guessPosition)
                        }}
                      />

                      {/* Guess location marker */}
                      <Marker
                        position={level.guessPosition}
                        icon={createGuessLocationIcon(level.color)}
                        eventHandlers={{
                          click: () => handleMarkerClick(level.actualPosition, level.guessPosition)
                        }}
                      />

                      {/* White "border" line */}
                      <Polyline
                        positions={[level.actualPosition, level.guessPosition]}
                        color="white"
                        weight={5}
                        opacity={0.7}
                        dashArray="5, 10"
                      />

                      {/* Line connecting the two points with level color */}
                      <Polyline
                        positions={[level.actualPosition, level.guessPosition]}
                        color={level.color}
                        weight={3}
                        opacity={0.7}
                        dashArray="5, 10"
                      />
                    </div>
                  ))}

                  {/* Auto-fit bounds to show all markers */}
                  <MapBounds positions={allPositions} />

                  {/* Map handler to capture map instance */}
                  <MapHandler onMapReady={(map) => { mapInstanceRef.current = map; }} />

                  {/* Custom Zoom Controls */}
                  <MapZoomControls />
                </MapContainer>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-4">
          <ButtonLarge onClick={handleBackToResults} className="flex-1">
            <ArrowLeft className="mt-1" /> Powrót do Wyników
          </ButtonLarge>
          <ButtonLarge onClick={handleShowLeaderboard} className="flex-1">
            Tabela Wyników <Trophy className="mt-1" />
          </ButtonLarge>
        </div>
      </div>
    </div>
  );
}
