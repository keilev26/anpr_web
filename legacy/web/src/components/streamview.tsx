// components/SonyLiveView.tsx
"use client";
import { useEffect, useState } from "react";

type Props = {
  isLive: boolean;              // control externo de pausa
  onError?: (err: string) => void;
};

export default function SonyLiveView({ isLive, onError }: Props) {
  const [src, setSrc] = useState<string | null>("/api/camera/live");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (isLive) {
      setFailed(false);
      setSrc(`/api/camera/live?ts=${Date.now()}`); // cache-bust al reanudar
    } else {
      setSrc(null); // cortar la request MJPEG
    }
  }, [isLive]);

  return (
    <>
      {src && !failed ? (
        <img
          src={src}
          alt="Sony Liveview"
          className="absolute inset-0 h-full w-full object-contain z-0 select-none"
          draggable={false}
          onError={() => {
            setFailed(true);
            onError?.("stream error");
          }}
        />
      ) : null}
    </>
  );
}
