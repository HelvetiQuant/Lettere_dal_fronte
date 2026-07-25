import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { useAudience } from '@/hooks/useAudience';
import { HomePage } from '@/pages/HomePage';
import { ExplorePage } from '@/pages/ExplorePage';
import { EventsPage, EventDossierPage } from '@/pages/EventsPage';
import { EventResearchPage } from '@/pages/EventResearchPage';
import { ResearchPage } from '@/pages/ResearchPage';
import { ResearchPlansPage } from '@/pages/ResearchPlansPage';
import { ResearchSubjectsPage } from '@/pages/ResearchSubjectsPage';
import { ResearchGapsPage } from '@/pages/ResearchGapsPage';
import { ViewpointsPage } from '@/pages/ViewpointsPage';
import { HeuristicLinksPage } from '@/pages/HeuristicLinksPage';
import { GraphEntityPage } from '@/pages/GraphEntityPage';
import { ChatPage } from '@/pages/ChatPage';
import { RecognitionsPage } from '@/pages/RecognitionsPage';
import { AdminPage } from '@/pages/AdminPage';
import { SoldierDossierPage } from '@/pages/SoldierDossierPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

export function AppRouter() {
  const [audience, setAudience] = useAudience();

  return (
    <BrowserRouter>
      <AppShell audience={audience} onAudienceChange={setAudience}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/esplora" element={<ExplorePage />} />
          <Route path="/eventi" element={<EventsPage />} />
          <Route path="/eventi/:eventName" element={<EventDossierPage />} />
          <Route path="/ricerca-evento/:eventName" element={<EventResearchPage />} />
          <Route path="/ricerca" element={<ResearchPage />} />
          <Route path="/ricerca/piani" element={<ResearchPlansPage />} />
          <Route path="/ricerca/soggetti" element={<ResearchSubjectsPage />} />
          <Route path="/ricerca/lacune" element={<ResearchGapsPage />} />
          <Route path="/punti-di-vista" element={<ViewpointsPage />} />
          <Route path="/collegamenti" element={<HeuristicLinksPage />} />
          <Route path="/grafo/:sourceTable/:sourceId" element={<GraphEntityPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/riconoscimenti" element={<RecognitionsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/soldato/:type/:id" element={<SoldierDossierPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
