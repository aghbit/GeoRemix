import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ButtonLarge } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MapZoomControls } from "@/components/ui/map-zoom-controls";
import { useGameStateManager } from "@/context/game-state";
import { useNavigation } from "@/lib/navigation-system/navigation-provider";
import { moduleIdMap } from "@/lib/navigation-system/types";
import { ArrowLeft, Gamepad2 } from "lucide-react";

// Fix for default markers in React Leaflet
delete (L.Icon.Default.prototype as unknown as { _getIconUrl: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

const actualLocationIcon = L.divIcon({
  html: `
    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24"
                      stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="var(--main)">
                      <path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528" />
                    </svg>
  `,
  className: "",
  iconSize: [36, 36],
  iconAnchor: [7, 33],
});

const guessLocationIcon = L.divIcon({
  html: `
    <svg width="36" height="36" viewBox="0 0 24 24"
                      xmlns="http://www.w3.org/2000/svg"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
                      fill="var(--main)">
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

// Component to fit bounds when markers change
function MapBounds({
  actualPosition,
  guessPosition,
}: {
  actualPosition: [number, number];
  guessPosition: [number, number];
}) {
  const map = useMap();

  useEffect(() => {
    const bounds = L.latLngBounds([actualPosition, guessPosition]);
    map.fitBounds(bounds, { padding: [50, 50] });
  }, [map, actualPosition, guessPosition]);

  return null;
}

export function LevelMap() {
  const { navigateTo, navigateWithLoading } = useNavigation();
  const gameStateManager = useGameStateManager();
  const [resultData, setResultData] = useState<{
    distance: number;
    actualPosition: [number, number];
    guessPosition: [number, number];
  } | null>(null);

  useEffect(() => {
    try {
      const levelResult = gameStateManager.levelResult;

      const submittedPosition = levelResult.submittedPosition;
      const actualPosition = levelResult.answerPosition;

      setResultData({
        distance: levelResult.distance,
        actualPosition: [actualPosition.lat, actualPosition.lng],
        guessPosition: [submittedPosition.lat, submittedPosition.lng],
      });
    } catch (error) {
      console.error("Error loading result data:", error);
      // Fallback to mock data
      setResultData({
        distance: 1230,
        actualPosition: [50.0619, 19.9368],
        guessPosition: [50.0647, 19.945],
      });
    }
  }, [gameStateManager]);

  const handleBackToSummary = () => {
    navigateTo(moduleIdMap.LEVEL_END, "level-summary");
  };

  const handleNextLevel = () => {
    if (gameStateManager.numberOfLevels === gameStateManager.currentLevelInfo.number) {
      navigateTo(moduleIdMap.FINAL, "final-result");
    } else {
      const loadingPromise = new Promise((resolve) => {
        gameStateManager.loadNextLevel();
        resolve(null);
      });
      navigateWithLoading(moduleIdMap.LEVEL_START, "level-start", loadingPromise);
    }
  };

  const formatDistance = (distance: number) => {
    if (distance < 1000) {
      return `${Math.round(distance)}m`;
    } else {
      return `${(distance / 1000).toFixed(1)} km`;
    }
  };

  if (!resultData) {
    return (
      <div className="flex items-center justify-center min-h-full">
        <div className="text-lg">Loading map...</div>
      </div>
    );
  }

  return (
    <div className="flex items-center h-full justify-center min-h-full bg-background p-4">
      <div className="max-w-4xl w-full flex flex-col justify-center h-full space-y-6">
        {/* Map Container with Legend Card Overlay */}
        <div className="relative flex-1 max-h-[80%] min-h-[400px]">
          {/* Legend Card - positioned outside bounds with higher z-index */}
          <div className=" absolute -top-2 z-[2000] p-0 -left-2">
            <Card className="p-0 bg-secondary-background gradient">
              <CardContent className="px-3 py-2">
                <div className="space-y-2 text-sm">
                  <div className="flex items-center space-x-2">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      stroke="black"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      fill="var(--main)">
                      <path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528" />
                    </svg>
                    <span className="text-foreground font-base">Faktyczna lokalizacja</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <svg
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      xmlns="http://www.w3.org/2000/svg"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      fill="var(--main)">
                      <path d="M12.56 20.82a.96.96 0 0 1-1.12 0C6.611 17.378 1.486 10.298 6.667 5.182A7.6 7.6 0 0 1 12 3c2 0 3.919.785 5.333 2.181 5.181 5.116.056 12.196-4.773 15.64" />
                      <path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4" />
                    </svg>
                    <span className="text-foreground font-base">Twoja odpowiedź</span>
                  </div>
                </div>
              </CardContent>
            </Card>
            {/* Distance Card - positioned below legend */}
            <Card className="mt-4 z-[2000] p-0 bg-secondary-background gradient">
              <CardContent className="px-3 py-2">
                <div className="text-2xl font-bold text-background dark:text-foreground font-outline-1">
                  Dystans: {formatDistance(resultData.distance)}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Map Card */}
          <Card className="bg-secondary-background h-full gradient relative overflow-hidden p-0">
            <CardContent className="p-0 h-full">
              <div className="h-full relative">
                <MapContainer
                  center={resultData.actualPosition}
                  zoom={13}
                  minZoom={2}
                  maxZoom={18}
                  style={{ height: "100%", width: "100%" }}
                  zoomControl={false}
                  attributionControl={false}>
                  <TileLayer url={mapLayer.url} attribution={mapLayer.attribution} />

                  {/* Actual location marker */}
                  <Marker position={resultData.actualPosition} icon={actualLocationIcon} />

                  {/* Guess location marker */}
                  <Marker position={resultData.guessPosition} icon={guessLocationIcon} />

                  {/* White "border" line */}
                  <Polyline
                    positions={[resultData.actualPosition, resultData.guessPosition]}
                    color="white"
                    weight={5}
                    opacity={0.7}
                    dashArray="5, 10"
                  />

                  {/* Line connecting the two points */}
                  <Polyline
                    positions={[resultData.actualPosition, resultData.guessPosition]}
                    color="var(--main)"
                    weight={3}
                    opacity={0.7}
                    dashArray="5, 10"
                  />

                  {/* Auto-fit bounds to show both markers */}
                  <MapBounds
                    actualPosition={resultData.actualPosition}
                    guessPosition={resultData.guessPosition}
                  />

                  {/* Custom Zoom Controls */}
                  <MapZoomControls />
                </MapContainer>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Action Buttons - Same line */}
        <div className="flex space-x-4">
          <ButtonLarge onClick={handleBackToSummary} className="flex-1">
            <ArrowLeft className="mt-1" /> Powrót do Podsumowania
          </ButtonLarge>
          <ButtonLarge onClick={handleNextLevel} className="flex-1">
            Następna Runda <Gamepad2 className="mt-1" />
          </ButtonLarge>
        </div>
      </div>
    </div>
  );
}
