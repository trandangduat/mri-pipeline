import React from 'react';
import {cn} from '@/lib/utils';

function Card({className, ...props}: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="card"
      className={cn(
        'rounded-lg border border-[#e6e5e0] bg-white text-[#26251e] shadow-none p-3.5 transition-all',
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({className, ...props}: React.ComponentProps<'div'>) {
  return <div data-slot="card-header" className={cn('flex flex-col gap-1 pb-2.5', className)} {...props} />;
}

function CardTitle({className, ...props}: React.ComponentProps<'h3'>) {
  return (
    <h3 data-slot="card-title" className={cn('text-base font-semibold tracking-tight text-[#26251e]', className)} {...props} />
  );
}

function CardDescription({className, ...props}: React.ComponentProps<'p'>) {
  return <p data-slot="card-description" className={cn('text-xs text-[#807d72]', className)} {...props} />;
}

function CardContent({className, ...props}: React.ComponentProps<'div'>) {
  return <div data-slot="card-content" className={cn('p-0', className)} {...props} />;
}

function CardFooter({className, ...props}: React.ComponentProps<'div'>) {
  return (
    <div data-slot="card-footer" className={cn('flex items-center pt-2.5 border-t border-[#e6e5e0]', className)} {...props} />
  );
}

export {Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter};
