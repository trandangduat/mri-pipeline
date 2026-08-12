import React from 'react';
import {cn} from '@/lib/utils';

function Progress({
  value = 0,
  max = 100,
  className,
  indicatorClassName,
  ...props
}: React.ComponentProps<'div'> & {value?: number; max?: number; indicatorClassName?: string}) {
  const percentage = Math.min(Math.max(0, (value / max) * 100), 100);
  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn('relative h-1.5 w-full overflow-hidden rounded-full bg-[#f2f2ee]', className)}
      {...props}
    >
      <div
        className={cn('h-full bg-[#0077b6] transition-all duration-300', indicatorClassName)}
        style={{width: `${percentage}%`}}
      />
    </div>
  );
}

export {Progress};
