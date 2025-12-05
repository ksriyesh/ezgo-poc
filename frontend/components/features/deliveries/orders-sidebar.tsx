'use client';

import { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, Loader2, Package, Warehouse, Truck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Order, Depot } from '@/lib/types';

const ROUTE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#f97316',
];

interface OrdersSidebarProps {
  orders: Order[];
  depots: Depot[];
  onAutoAssignAll: () => void;
  onManualAssign: (orderIds: string[], vehicleId: number, depotId: string) => void;
  isLoading: boolean;
  orderClusters: Map<string, number>;
  usedDrivers: Map<string, Set<number>>;
}

export function OrdersSidebar({ 
  orders, 
  depots, 
  onAutoAssignAll, 
  onManualAssign, 
  isLoading, 
  orderClusters, 
  usedDrivers 
}: OrdersSidebarProps) {
  const [selectedOrders, setSelectedOrders] = useState<Set<string>>(new Set());
  const [selectedDepots, setSelectedDepots] = useState<Set<string>>(new Set(depots.map(d => d.id)));
  const [selectedVehicle, setSelectedVehicle] = useState<number | null>(null);
  const [expandedDepots, setExpandedDepots] = useState<Set<string>>(new Set());

  const filteredOrders = useMemo(() => {
    return orders.filter(order => order.depot_id && selectedDepots.has(order.depot_id));
  }, [orders, selectedDepots]);

  const ordersByDepot = useMemo(() => {
    return filteredOrders.reduce((acc, order) => {
      if (!order.depot_id) return acc;
      if (!acc[order.depot_id]) acc[order.depot_id] = [];
      acc[order.depot_id].push(order);
      return acc;
    }, {} as Record<string, Order[]>);
  }, [filteredOrders]);

  useMemo(() => {
    setExpandedDepots(new Set(Object.keys(ordersByDepot)));
  }, [ordersByDepot]);

  const toggleDepot = (depotId: string) => {
    const newExpanded = new Set(expandedDepots);
    if (newExpanded.has(depotId)) {
      newExpanded.delete(depotId);
    } else {
      newExpanded.add(depotId);
    }
    setExpandedDepots(newExpanded);
  };

  const totalUnassignedOrders = filteredOrders.length;
  const depotsWithOrders = Object.keys(ordersByDepot).length;
  
  const selectedOrdersDepotId = useMemo(() => {
    if (selectedOrders.size === 0) return null;
    const firstOrder = orders.find(o => selectedOrders.has(o.id));
    return firstOrder?.depot_id || null;
  }, [selectedOrders, orders]);
  
  const selectedDepot = depots.find(d => d.id === selectedOrdersDepotId);
  const totalDrivers = selectedDepot?.available_drivers || 0;
  const depotUsedDrivers = selectedOrdersDepotId ? (usedDrivers.get(selectedOrdersDepotId) || new Set()) : new Set();
  const availableVehicles = Array.from({ length: totalDrivers }, (_, i) => i).filter(i => !depotUsedDrivers.has(i));

  const toggleOrderSelection = (orderId: string) => {
    const newSelected = new Set(selectedOrders);
    if (newSelected.has(orderId)) {
      newSelected.delete(orderId);
    } else {
      newSelected.add(orderId);
    }
    setSelectedOrders(newSelected);
  };
  
  const toggleDepotSelection = (depotId: string) => {
    const newSelected = new Set(selectedDepots);
    if (newSelected.has(depotId)) {
      newSelected.delete(depotId);
    } else {
      newSelected.add(depotId);
    }
    setSelectedDepots(newSelected);
  };
  
  const selectAllOrdersForDepot = (depotId: string, select: boolean) => {
    const depotOrders = ordersByDepot[depotId] || [];
    const newSelected = new Set(selectedOrders);
    depotOrders.forEach(order => {
      if (select) {
        newSelected.add(order.id);
      } else {
        newSelected.delete(order.id);
      }
    });
    setSelectedOrders(newSelected);
  };
  
  const handleManualAssign = () => {
    if (selectedOrders.size === 0 || selectedVehicle === null || !selectedOrdersDepotId) return;
    onManualAssign(Array.from(selectedOrders), selectedVehicle, selectedOrdersDepotId);
    setSelectedOrders(new Set());
    setSelectedVehicle(null);
  };

  return (
    <div className="h-full w-96 bg-white border-l flex flex-col shadow-lg">
      {/* Header */}
      <div className="p-4 border-b bg-gradient-to-r from-blue-50 to-white space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900">Unassigned Orders</h2>
          <div className="flex items-center gap-2">
            {selectedOrders.size > 0 && (
              <Badge variant="default" className="bg-green-600">
                {selectedOrders.size} selected
              </Badge>
            )}
            <Badge variant="secondary" className="text-lg px-3 py-1">
              {totalUnassignedOrders}
            </Badge>
          </div>
        </div>
        
        {/* Depot Filter */}
        <div className="space-y-1.5">
          <Label className="text-xs text-gray-600">Filter by Depot</Label>
          <Select
            value={selectedDepots.size === depots.length ? 'all' : 'custom'}
            onValueChange={(value) => {
              if (value === 'all') {
                setSelectedDepots(new Set(depots.map(d => d.id)));
              }
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue>
                {selectedDepots.size === depots.length 
                  ? 'All Depots' 
                  : `${selectedDepots.size} Depot${selectedDepots.size !== 1 ? 's' : ''}`}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Depots</SelectItem>
              {depots.map(depot => (
                <div
                  key={depot.id}
                  className="flex items-center space-x-2 px-2 py-1.5 cursor-pointer hover:bg-gray-100"
                  onClick={(e) => {
                    e.preventDefault();
                    toggleDepotSelection(depot.id);
                  }}
                >
                  <Checkbox
                    checked={selectedDepots.has(depot.id)}
                    onCheckedChange={() => toggleDepotSelection(depot.id)}
                  />
                  <span className="text-sm">{depot.name}</span>
                </div>
              ))}
            </SelectContent>
          </Select>
        </div>
        
        {/* Vehicle Selection */}
        {selectedOrders.size > 0 && (
          <div className="space-y-1.5">
            <Label className="text-xs text-gray-600">
              Assign to Vehicle ({availableVehicles.length} of {totalDrivers} available)
            </Label>
            {availableVehicles.length === 0 ? (
              <div className="text-sm text-red-600 p-2 bg-red-50 rounded">
                All drivers are assigned. Complete current routes before manual assignment.
              </div>
            ) : (
              <Select
                value={selectedVehicle?.toString() || ''}
                onValueChange={(value) => setSelectedVehicle(parseInt(value))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {selectedVehicle !== null ? `Vehicle ${selectedVehicle + 1}` : 'Select vehicle'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {availableVehicles.map((vehicleId) => (
                    <SelectItem key={vehicleId} value={vehicleId.toString()}>
                      <div className="flex items-center gap-2">
                        <Truck className="h-4 w-4" />
                        Vehicle {vehicleId + 1}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        )}
        
        {/* Action Buttons */}
        <div className="space-y-2">
          {selectedOrders.size > 0 && (
            <Button
              onClick={handleManualAssign}
              disabled={isLoading || selectedVehicle === null || availableVehicles.length === 0}
              className="w-full bg-green-600 hover:bg-green-700"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Assigning...
                </>
              ) : (
                <>
                  <Truck className="mr-2 h-5 w-5" />
                  Manual Assign Selected
                </>
              )}
            </Button>
          )}
          <Button
            onClick={onAutoAssignAll}
            disabled={isLoading || totalUnassignedOrders === 0}
            className="w-full bg-blue-600 hover:bg-blue-700"
            size="lg"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                Creating Routes...
              </>
            ) : (
              <>
                <Package className="mr-2 h-5 w-5" />
                Auto Assign All
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Orders List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {depotsWithOrders === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-500">
            <Package className="h-16 w-16 mb-4 text-gray-300" />
            <p className="text-lg font-medium">No unassigned orders</p>
            <p className="text-sm mt-2">All orders have been assigned to routes</p>
          </div>
        ) : (
          Object.entries(ordersByDepot).map(([depotId, depotOrders]) => {
            const depot = depots.find(d => d.id === depotId);
            if (!depot) return null;

            const isExpanded = expandedDepots.has(depotId);
            const depotOrderIds = depotOrders.map(o => o.id);
            const selectedCount = depotOrderIds.filter(id => selectedOrders.has(id)).length;
            const allSelected = selectedCount === depotOrders.length && depotOrders.length > 0;

            return (
              <Card key={depotId} className="overflow-hidden">
                <Collapsible open={isExpanded} onOpenChange={() => toggleDepot(depotId)}>
                  <CollapsibleTrigger asChild>
                    <CardHeader className="p-3 cursor-pointer hover:bg-gray-50 transition-colors">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 flex-1">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-gray-500" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-gray-500" />
                          )}
                          <Checkbox
                            checked={allSelected}
                            onCheckedChange={(checked) => selectAllOrdersForDepot(depotId, checked as boolean)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <Warehouse className="h-5 w-5 text-blue-600" />
                          <div className="flex-1">
                            <CardTitle className="text-sm font-semibold">{depot.name}</CardTitle>
                            <p className="text-xs text-gray-500 mt-0.5">{depot.address}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {selectedCount > 0 && (
                            <Badge variant="default" className="bg-green-600 text-xs">
                              {selectedCount}
                            </Badge>
                          )}
                          <Badge variant="outline" className="ml-2">
                            {depotOrders.length}
                          </Badge>
                        </div>
                      </div>
                    </CardHeader>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <CardContent className="p-0">
                      <div className="max-h-96 overflow-y-auto">
                        {depotOrders.map((order) => {
                          const isSelected = selectedOrders.has(order.id);
                          const clusterId = orderClusters.get(order.id);
                          const clusterColor = clusterId !== undefined 
                            ? ROUTE_COLORS[clusterId % ROUTE_COLORS.length]
                            : null;

                          return (
                            <div
                              key={order.id}
                              className={`p-3 border-t hover:bg-gray-50 transition-colors ${isSelected ? 'bg-blue-50' : ''}`}
                              style={{
                                borderLeftWidth: clusterColor ? '4px' : '0',
                                borderLeftColor: clusterColor || 'transparent',
                              }}
                            >
                              <div className="flex items-start gap-2">
                                <Checkbox
                                  checked={isSelected}
                                  onCheckedChange={() => toggleOrderSelection(order.id)}
                                  className="mt-0.5 flex-shrink-0"
                                />
                                <Package className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <span className="text-xs font-mono text-blue-600 font-semibold">
                                      {order.order_number}
                                    </span>
                                    {clusterId !== undefined && (
                                      <Badge
                                        variant="outline"
                                        className="text-xs px-1.5 py-0"
                                        style={{ borderColor: clusterColor || undefined, color: clusterColor || undefined }}
                                      >
                                        C{clusterId}
                                      </Badge>
                                    )}
                                    <Badge variant="secondary" className="text-xs px-1.5 py-0">
                                      {order.status}
                                    </Badge>
                                  </div>
                                  <p className="text-sm font-medium text-gray-900 truncate">
                                    {order.customer_name}
                                  </p>
                                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                                    {order.delivery_address}
                                  </p>
                                  {order.scheduled_delivery_date && (
                                    <p className="text-xs text-gray-400 mt-1">
                                      Delivery: {order.scheduled_delivery_date}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </CollapsibleContent>
                </Collapsible>
              </Card>
            );
          })
        )}
      </div>

      {/* Footer Stats */}
      <div className="p-4 border-t bg-gray-50">
        <div className="grid grid-cols-2 gap-4 text-center">
          <div>
            <p className="text-2xl font-bold text-blue-600">{totalUnassignedOrders}</p>
            <p className="text-xs text-gray-600 mt-1">Total Orders</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-green-600">{depotsWithOrders}</p>
            <p className="text-xs text-gray-600 mt-1">Depots</p>
          </div>
        </div>
      </div>
    </div>
  );
}
