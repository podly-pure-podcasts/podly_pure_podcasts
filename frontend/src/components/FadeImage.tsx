import { useState, type ImgHTMLAttributes } from 'react';

// An <img> that fades in once its bytes arrive instead of popping in, so slow
// artwork lands softly after the surrounding content. Cached images are already
// `complete` at mount and show at once. Tracks the loaded src so a reused
// element fades again when its src changes.
export default function FadeImage({ className = '', onLoad, src, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loadedSrc, setLoadedSrc] = useState<string | undefined>(undefined);
  return (
    <img
      {...props}
      src={src}
      ref={(img) => {
        if (img?.complete && img.naturalWidth > 0 && loadedSrc !== src) setLoadedSrc(src);
      }}
      onLoad={(event) => {
        setLoadedSrc(src);
        onLoad?.(event);
      }}
      className={`transition-opacity duration-300 ease-out motion-reduce:transition-none ${
        loadedSrc === src ? 'opacity-100' : 'opacity-0'
      } ${className}`}
    />
  );
}
