import { lazy, Suspense, useState } from 'react';
import ModalShell from './ModalShell';
import StatsLoadingFrame from './stats/StatsLoadingFrame';

const ChapterStatsBody = lazy(() => import('./stats/ChapterStatsBody'));

interface ChapterProcessingStatsProps {
  episodeGuid: string;
  hasProcessedAudio: boolean;
  className?: string;
}

export default function ChapterProcessingStats({
  episodeGuid,
  hasProcessedAudio,
  className = ''
}: ChapterProcessingStatsProps) {
  const [showModal, setShowModal] = useState(false);
  const close = () => setShowModal(false);

  if (!hasProcessedAudio) {
    return null;
  }

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className={`btn btn-secondary btn-sm ${className}`}
      >
        Stats
      </button>

      <ModalShell
        isOpen={showModal}
        onClose={close}
        panelClassName="bg-surface rounded-lg w-full max-w-7xl xl:max-w-[96rem] 2xl:max-w-[110rem] flex h-[85dvh] max-h-[85dvh] flex-col overflow-hidden sm:h-[82dvh] sm:max-h-[82dvh] lg:h-[min(88dvh,58rem)] lg:max-h-[min(88dvh,58rem)] xl:h-[min(90dvh,62rem)] xl:max-h-[min(90dvh,62rem)]"
      >
        <Suspense fallback={<StatsLoadingFrame onClose={close} />}>
          <ChapterStatsBody episodeGuid={episodeGuid} onClose={close} />
        </Suspense>
      </ModalShell>
    </>
  );
}
