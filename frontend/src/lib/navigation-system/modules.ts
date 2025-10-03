import { Gameplay } from "@/pages/gameplay";
import { LevelStart } from "@/pages/level-start";
import { LevelSummary } from "@/pages/level-summary";
import { LevelMap } from "@/pages/level-map";
import { MockPage } from "@/pages/mock";
import { WelcomePage } from "@/pages/welcome-page";
import { StagePicker } from "@/pages/stage-picker";
import { TitlePage } from "@/pages/title";
import { AboutPage } from "@/pages/about";
import { NavigationLoadingPage } from "@/pages/navigation-loading-page";
import type { Module } from "./types";
import { moduleIdMap } from "./types";
import { FinalResult } from "@/pages/final-result";
import { FinalMap } from "@/pages/final-map";

export const titleGroup: Module = {
  id: moduleIdMap.TITLE,
  pages: [{ id: "title", component: TitlePage, title: "NVIDIA Geo-Guessing" }],
  // initialPage: "title",
};

export const introGroup: Module = {
  id: moduleIdMap.INTRO,
  pages: [
    { id: "welcome-page", component: WelcomePage, title: "Welcome to GeoRemix", showStars: true },
    { id: "about", component: AboutPage, title: "About" },
    { id: "leader-board", component: MockPage, title: "Leader Board" },
    { id: "stage-picker", component: StagePicker, title: "Pick the Stage", showStars: true },
  ],
  // initialPage: "welcome-page",
};

export const levelStartGroup: Module = {
  id: moduleIdMap.LEVEL_START,
  pages: [{ id: "level-start", component: LevelStart, title: "Start the Level", showStars: true }],
};

export const gameplayGroup: Module = {
  id: moduleIdMap.GAMEPLAY,
  pages: [{ id: "gameplay", component: Gameplay, title: "Game" }],
};

export const levelEndGroup: Module = {
  id: moduleIdMap.LEVEL_END,
  pages: [
    { id: "level-summary", component: LevelSummary, title: "Level Results", showStars: true },
    { id: "level-map", component: LevelMap, title: "Result Map" },
  ],
};

export const gameEndGroup: Module = {
  id: moduleIdMap.FINAL,
  pages: [{ id: "final-result", component: FinalResult, title: "Summary", showStars: true }],

};

export const loadingGroup: Module = {
  id: moduleIdMap.LOADING,
  pages: [{ id: "navigation-loading", component: NavigationLoadingPage, title: "Loading..." }],
};

export const modulesMap = {
  [titleGroup.id]: titleGroup,
  [introGroup.id]: introGroup,
  [levelStartGroup.id]: levelStartGroup,
  [levelEndGroup.id]: levelEndGroup,
  [gameEndGroup.id]: gameEndGroup,
  [gameplayGroup.id]: gameplayGroup,
  [loadingGroup.id]: loadingGroup,
} as const;
