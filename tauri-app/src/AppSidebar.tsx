import React, {useCallback} from 'react';
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuBadge,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
  SidebarFooter,
  SidebarTrigger,
} from '@/components/ui/sidebar';
import {Activity, BrainCircuit, Container, SlidersHorizontal} from 'lucide-react';
import type {AppTab} from './stores/uiStore';
import {displayJobState, sidebarDotClass} from './lib/jobs';
import {jobBasename} from './jobFormatters';

export interface AppSidebarProps {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  jobs?: unknown[];
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
  envText?: string;
  sidebarOpen: boolean;
  onSidebarOpenChange: (open: boolean) => void;
  sidebarWidth: number;
  onSidebarWidthChange: (width: number) => void;
}

export function AppSidebar({
  activeTab,
  onSelectTab,
  jobs = [],
  selectedJobId,
  onSelectJob,
  envText,
  sidebarOpen,
  onSidebarOpenChange,
  sidebarWidth,
  onSidebarWidthChange,
}: AppSidebarProps) {
  const startResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!sidebarOpen) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = sidebarWidth;

      const onMove = (moveEvent: PointerEvent) => {
        onSidebarWidthChange(startWidth + moveEvent.clientX - startX);
      };
      const onUp = () => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    },
    [onSidebarWidthChange, sidebarOpen, sidebarWidth],
  );

  return (
    <SidebarProvider open={sidebarOpen} onOpenChange={onSidebarOpenChange} style={{'--sidebar-width': `${sidebarWidth}px`} as React.CSSProperties}>
      <Sidebar
        collapsible="icon"
        className="font-sans border-r border-cursor-hairline bg-cursor-canvas text-cursor-ink"
      >
        <SidebarHeader className="border-b border-cursor-hairline px-4 py-3 flex flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-cursor-primary text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div className="flex flex-col min-w-0 group-data-[collapsible=icon]:hidden">
              <strong className="truncate text-sm font-semibold tracking-tight text-cursor-ink">NeuroFlow</strong>
              <span className="text-[11px] font-mono text-cursor-body">MRI Pipeline</span>
            </div>
          </div>
          <SidebarTrigger className="flex-none" />
        </SidebarHeader>

        <SidebarContent className="px-3 py-4">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'pipeline'}
                onClick={() => onSelectTab('pipeline')}
                tooltip="Pipeline Configuration"
                className="h-10 text-sm"
              >
                <SlidersHorizontal className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Pipeline Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'tools'}
                onClick={() => onSelectTab('tools')}
                tooltip="Tools Configuration"
                className="h-10 text-sm"
              >
                <Container className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Tools Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'jobs'}
                onClick={() => onSelectTab('jobs')}
                tooltip="Jobs Monitor"
                className="h-10 text-sm"
              >
                <Activity className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Jobs Monitor</span>
                <SidebarMenuBadge className="bg-cursor-hairline text-cursor-ink">{jobs.length}</SidebarMenuBadge>
              </SidebarMenuButton>

              <SidebarMenuSub className="ml-4 mt-1 border-l border-cursor-hairline pl-2.5">
                {jobs.length === 0 ? (
                  <SidebarMenuSubItem>
                    <span className="block rounded-md bg-cursor-canvas-soft px-2.5 py-1.5 text-xs italic text-cursor-body">
                      No active jobs
                    </span>
                  </SidebarMenuSubItem>
                ) : (
                  jobs.map((jobItem) => {
                    const job = jobItem as Record<string, unknown>;
                    const isSelected = selectedJobId === job.job_id;
                    const stateCls = sidebarDotClass(job);
                    const title = jobBasename(job.display_name || job.job_id || job.remote_job_dir || job.job_dir);
                    const subtitle = displayJobState(job.state);

                    return (
                      <SidebarMenuSubItem key={String(job.job_id || '')}>
                        <SidebarMenuSubButton
                          isActive={isSelected}
                          onClick={() => {
                            onSelectTab('jobs');
                            onSelectJob?.(String(job.job_id || ''));
                          }}
                          className="min-h-11 text-xs flex items-center justify-between gap-2 cursor-pointer rounded-lg border border-transparent px-2 py-2 data-active:border-cursor-hairline data-active:bg-white"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`h-2 w-2 rounded-full flex-none ${stateCls}`} />
                            <span className="grid min-w-0 gap-0.5">
                              <span className="truncate text-[12px] font-medium text-cursor-ink">{title}</span>
                              <span className="truncate text-[10px] uppercase tracking-[0.08em] text-cursor-muted">{subtitle}</span>
                            </span>
                          </div>
                          <span className="rounded border border-cursor-hairline bg-white px-1.5 py-0.5 text-[10px] font-mono uppercase text-cursor-body">
                            {String(job.target || 'Local')}
                          </span>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    );
                  })
                )}
              </SidebarMenuSub>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarContent>

        <SidebarFooter className="border-t border-cursor-hairline p-3 text-xs text-cursor-body">
          <div id="environmentList" className="group-data-[collapsible=icon]:hidden">
            {envText || 'Backend ready'}
          </div>
        </SidebarFooter>
        {sidebarOpen ? (
          <div
            role="separator"
            aria-label="Resize sidebar"
            aria-orientation="vertical"
            onPointerDown={startResize}
            className="absolute right-0 top-0 z-30 h-full w-2 cursor-col-resize bg-transparent before:absolute before:right-0 before:top-0 before:h-full before:w-px before:bg-cursor-hairline hover:before:bg-cursor-primary group-data-[collapsible=icon]:hidden"
          />
        ) : null}
      </Sidebar>
    </SidebarProvider>
  );
}
