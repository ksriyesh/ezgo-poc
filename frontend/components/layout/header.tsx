'use client';

import { Map, Table2, LayoutDashboard } from 'lucide-react';
import { useAppStore } from '@/lib/stores';
import { Button } from '@/components/ui/button';
import { SidebarTrigger } from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';

export function Header() {
  const { viewMode, setViewMode } = useAppStore();

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      
      <div className="flex items-center gap-2 flex-1">
        <LayoutDashboard className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Dashboard</h2>
      </div>

      <div className="flex items-center gap-3">
        {/* View Toggle */}
        <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
          <Button
            variant={viewMode === 'map' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setViewMode('map')}
            className="gap-2"
          >
            <Map className="h-4 w-4" />
            <span className="hidden sm:inline">Map</span>
          </Button>
          <Button
            variant={viewMode === 'table' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setViewMode('table')}
            className="gap-2"
          >
            <Table2 className="h-4 w-4" />
            <span className="hidden sm:inline">Table</span>
          </Button>
        </div>
      </div>
    </header>
  );
}


