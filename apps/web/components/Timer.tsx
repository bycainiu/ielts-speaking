import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface TimerProps {
  initialSeconds: number;
  onTimeUp?: () => void;
  className?: string;
  isWarning?: boolean; // Can be controlled externally if needed
}

export function Timer({ initialSeconds, onTimeUp, className, isWarning = false }: TimerProps) {
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);
  const onTimeUpRef = useRef(onTimeUp);
  const hasFiredTimeUpRef = useRef(false);

  useEffect(() => {
    onTimeUpRef.current = onTimeUp;
  }, [onTimeUp]);

  useEffect(() => {
    setSecondsLeft(initialSeconds);
    hasFiredTimeUpRef.current = false;
  }, [initialSeconds]);

  useEffect(() => {
    if (secondsLeft > 0) return;
    if (initialSeconds <= 0 || hasFiredTimeUpRef.current) return;

    hasFiredTimeUpRef.current = true;
    onTimeUpRef.current?.();
  }, [initialSeconds, secondsLeft]);

  useEffect(() => {
    if (secondsLeft <= 0) {
      return;
    }

    const timeoutId = setTimeout(() => {
      setSecondsLeft((prev) => Math.max(prev - 1, 0));
    }, 1000);

    return () => clearTimeout(timeoutId);
  }, [secondsLeft]);

  const formatTime = (totalSeconds: number) => {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const isNearingEnd = secondsLeft <= 10 || isWarning;

  return (
    <div className={cn(
      "font-mono text-xl tabular-nums rounded-md px-3 py-1 transition-colors duration-300",
      isNearingEnd ? "text-destructive bg-destructive/10" : "text-primary bg-primary/10",
      className
    )}>
      {formatTime(secondsLeft)}
    </div>
  );
}
