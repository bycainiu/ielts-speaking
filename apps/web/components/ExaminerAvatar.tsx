import { cn } from '@/lib/utils';
import { Bot } from 'lucide-react';

interface ExaminerAvatarProps {
  status: 'idle' | 'speaking' | 'listening';
  className?: string;
}

export function ExaminerAvatar({ status, className }: ExaminerAvatarProps) {
  return (
    <div className={cn("relative flex items-center justify-center w-32 h-32 rounded-full bg-card border-4", 
      status === 'speaking' ? "border-primary animate-pulse" : 
      status === 'listening' ? "border-secondary" : "border-border",
      className
    )}>
      {status === 'speaking' && (
        <div className="absolute inset-0 rounded-full border-4 border-primary opacity-50 animate-ping"></div>
      )}
      <Bot size={64} className={cn(
        "transition-colors duration-300",
        status === 'speaking' ? "text-primary" : "text-muted-foreground"
      )} />
    </div>
  );
}
