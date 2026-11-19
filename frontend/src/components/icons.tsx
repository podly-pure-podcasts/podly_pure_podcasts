import type { ReactNode, SVGProps } from 'react';

// One icon set for the app: 24px outline glyphs at a shared stroke width, plus
// the few filled media glyphs the player needs. Icons are decorative by
// default; give the surrounding control the accessible name.
type IconProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { className?: string };

function Outline({ className = 'h-4 w-4', children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

function Solid({ className = 'h-4 w-4', children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false" {...rest}>
      {children}
    </svg>
  );
}

export const CloseIcon = (p: IconProps) => <Outline {...p}><path d="M6 18L18 6M6 6l12 12" /></Outline>;
export const MenuIcon = (p: IconProps) => <Outline {...p}><path d="M4 6h16M4 12h16M4 18h16" /></Outline>;
export const CheckIcon = (p: IconProps) => <Outline {...p}><path d="M5 13l4 4L19 7" /></Outline>;
export const BlockedIcon = (p: IconProps) => (
  <Outline {...p}><path d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" /></Outline>
);
export const BoltIcon = (p: IconProps) => <Outline {...p}><path d="M13 10V3L4 14h7v7l9-11h-7z" /></Outline>;
export const PlusIcon = (p: IconProps) => <Outline {...p}><path d="M12 4v16m8-8H4" /></Outline>;
export const ChevronDownIcon = (p: IconProps) => <Outline {...p}><path d="M19 9l-7 7-7-7" /></Outline>;
export const InfoIcon = (p: IconProps) => (
  <Outline {...p}><path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></Outline>
);
export const WarningIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </Outline>
);
export const MusicIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
  </Outline>
);
export const LinkIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
  </Outline>
);
export const RefreshIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </Outline>
);
export const SlidersIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
  </Outline>
);
export const GearIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </Outline>
);
export const DotsVerticalIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
  </Outline>
);
export const TrashIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </Outline>
);
export const LogoutIcon = (p: IconProps) => (
  <Outline {...p}>
    <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </Outline>
);
export const DownloadIcon = (p: IconProps) => (
  <Outline {...p}><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></Outline>
);
export const RssIcon = (p: IconProps) => (
  <Outline {...p}><path d="M6 5c7.18 0 13 5.82 13 13M6 11a7 7 0 017 7m-6 0a1 1 0 11-2 0 1 1 0 012 0z" /></Outline>
);
export const SunIcon = (p: IconProps) => (
  <Outline {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2.5M12 19.5V22m-7.07-17.07 1.77 1.77m10.6 10.6 1.77 1.77M2 12h2.5m15 0H22M4.93 19.07l1.77-1.77m10.6-10.6 1.77-1.77" />
  </Outline>
);
export const MoonIcon = (p: IconProps) => (
  <Outline {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3c0 .24-.01.48-.01.72A7 7 0 0 0 20.28 12c.24 0 .48-.01.72-.01Z" /></Outline>
);

export const PlayIcon = (p: IconProps) => <Solid {...p}><path d="M8 5v14l11-7z" /></Solid>;
export const PauseIcon = (p: IconProps) => <Solid {...p}><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></Solid>;
export const SpeakerWaveIcon = (p: IconProps) => (
  <Solid {...p}>
    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
  </Solid>
);
export const SpeakerMuteIcon = (p: IconProps) => (
  <Solid {...p}>
    <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
  </Solid>
);
