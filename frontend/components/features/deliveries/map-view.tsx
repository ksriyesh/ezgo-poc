'use client';

import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { Map as MapboxMap, MapRef, Marker, Popup, Source, Layer } from 'react-map-gl';
import { Filter, ChevronDown, ChevronUp, Package, Warehouse } from 'lucide-react';
import { serviceAreasApi, serviceZonesApi, ordersApi, depotsApi, routeOptimizationApi } from '@/lib/api/index';
import type { ServiceArea, ServiceZone, Order, Depot } from '@/lib/types';
import type { OptimizedRoute } from '@/lib/api/index';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  h3CellsToFeatureCollection,
  calculateBoundingBox,
} from '@/lib/map/h3-utils';
import { OrdersSidebar } from './orders-sidebar';
import 'mapbox-gl/dist/mapbox-gl.css';

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN as string;
const OTTAWA_CENTER = { lat: 45.4215, lng: -75.6972 };

const ROUTE_COLORS = [
  '#3b82f6', // blue
  '#10b981', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // purple
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#f97316', // orange
];

export function MapView() {
  // Data state
  const [serviceAreas, setServiceAreas] = useState<ServiceArea[]>([]);
  const [serviceZones, setServiceZones] = useState<ServiceZone[]>([]);
  const [allOrders, setAllOrders] = useState<Order[]>([]);
  const [depots, setDepots] = useState<Depot[]>([]);
  const [routes, setRoutes] = useState<OptimizedRoute[]>([]);
  const [routeGeometries, setRouteGeometries] = useState<Map<string, any>>(new Map());
  const [clusters, setClusters] = useState<Map<number, { orders: string[], color: string, center: [number, number], coords?: [number, number][] }>>(new Map());
  const [orderClusters, setOrderClusters] = useState<Map<string, number>>(new Map());
  const [totalGroups, setTotalGroups] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Track assigned orders and used drivers per depot
  const [assignedOrderIds, setAssignedOrderIds] = useState<Set<string>>(new Set());
  const [usedDrivers, setUsedDrivers] = useState<Map<string, Set<number>>>(new Map());
  
  // Filter state
  const [selectedServiceAreaId, setSelectedServiceAreaId] = useState<string | 'none'>('none');
  const [selectedServiceZoneId, setSelectedServiceZoneId] = useState<string | 'all' | 'none'>('none');
  const [showOrders, setShowOrders] = useState(false);
  const [showRoutes, setShowRoutes] = useState(true);
  const [showDepots, setShowDepots] = useState(false);
  const [showClusters, setShowClusters] = useState(true);
  const [filterPanelOpen, setFilterPanelOpen] = useState(true);
  
  // UI state
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<OptimizedRoute | null>(null);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [viewState, setViewState] = useState({
    latitude: OTTAWA_CENTER.lat,
    longitude: OTTAWA_CENTER.lng,
    zoom: 11,
    bearing: 0,
    pitch: 0,
  });
  const mapRef = useRef<MapRef>(null);

  // ==========================================================================
  // DATA FETCHING
  // ==========================================================================

  useEffect(() => {
    const fetchAllData = async () => {
      setLoading(true);
      
      try {
        const [areas, zones, orders, depotsData] = await Promise.all([
          serviceAreasApi.getAll({ 
            include_h3: true,
            resolutions: "9",
            active_only: true 
          }),
          serviceZonesApi.getAll({
            include_h3: true,
            resolutions: "9",
            active_only: true
          }),
          ordersApi.getAll({ limit: 1000 }),
          depotsApi.getAll({ active_only: true })
        ]);
        
        setServiceAreas(Array.isArray(areas) ? areas : []);
        setServiceZones(Array.isArray(zones) ? zones : []);
        setAllOrders(Array.isArray(orders) ? orders : []);
        setDepots(Array.isArray(depotsData) ? depotsData : []);
        
        // Zoom to first area if available
        if (Array.isArray(areas) && areas.length > 0) {
          const defaultArea = areas.find(a => 
            a.name.toLowerCase().includes('ottawa')
          ) || areas[0];
          
          setTimeout(() => {
            if (mapRef.current && defaultArea.geometry) {
              const bounds = calculateBoundingBox(defaultArea.geometry);
              if (bounds) {
                mapRef.current.fitBounds(bounds, {
                  padding: 50,
                  duration: 1500,
                });
              }
            }
          }, 500);
        }
      } catch (error) {
        console.error('Failed to fetch data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAllData();
  }, []);

  // ==========================================================================
  // FILTERED DATA
  // ==========================================================================

  // Orders for MAP display - show ALL orders (assigned + unassigned)
  const mapOrders = useMemo(() => {
    if (!showOrders) return [];
    
    let filtered = allOrders.filter(order => 
      order.status === 'pending' || order.status === 'geocoded'
    );
    
    if (selectedServiceZoneId && selectedServiceZoneId !== 'all' && selectedServiceZoneId !== 'none') {
      filtered = filtered.filter(order => order.zone_id === selectedServiceZoneId);
    }
    
    return filtered;
  }, [allOrders, selectedServiceZoneId, showOrders]);
  
  // Orders for SIDEBAR panel - show only UNASSIGNED orders
  const filteredOrders = useMemo(() => {
    return mapOrders.filter(order => !assignedOrderIds.has(order.id));
  }, [mapOrders, assignedOrderIds]);

  const filteredZones = useMemo(() => {
    if (!selectedServiceAreaId) return serviceZones;
    return serviceZones.filter(z => z.service_area_id === selectedServiceAreaId);
  }, [serviceZones, selectedServiceAreaId]);

  // ==========================================================================
  // GEOJSON GENERATION
  // ==========================================================================

  const h3GeoJSONByResolution = useMemo(() => {
    const geoJSONMap = new Map<number, any>();
    
    if (serviceAreas.length === 0 || selectedServiceAreaId === 'none') return geoJSONMap;

    const areasToRender = serviceAreas.filter(a => a.id === selectedServiceAreaId);
    const resolution = 9;
    const allFeatures: any[] = [];

    areasToRender.forEach((area) => {
      if (!area.h3_coverage) return;
      const resKey = resolution.toString();
      if (!area.h3_coverage[resKey]) return;
      const cells = area.h3_coverage[resKey].cells || [];
      const featureCollection = h3CellsToFeatureCollection(cells, {
        area_id: area.id,
        area_name: area.name,
        resolution: resolution,
      });
      allFeatures.push(...featureCollection.features);
    });

    if (allFeatures.length > 0) {
      geoJSONMap.set(resolution, {
        type: 'FeatureCollection' as const,
        features: allFeatures,
      });
    }

    return geoJSONMap;
  }, [serviceAreas, selectedServiceAreaId]);

  const h3ZonesGeoJSONByResolution = useMemo(() => {
    const geoJSONMap = new Map<number, any>();
    
    if (serviceZones.length === 0) return geoJSONMap;
    
    const zonesToRender = selectedServiceZoneId === 'none' 
      ? []
      : selectedServiceZoneId === 'all' 
        ? filteredZones
        : filteredZones.filter(z => z.id === selectedServiceZoneId);
    
    const resolution = 9;
    const allFeatures: any[] = [];
      
    zonesToRender.forEach((zone) => {
      if (!zone.h3_coverage) return;
      const resKey = resolution.toString();
      if (!zone.h3_coverage[resKey]) return;
      const cells = zone.h3_coverage[resKey].cells || [];
      const featureCollection = h3CellsToFeatureCollection(cells, {
        zone_id: zone.id,
        zone_name: zone.name,
        resolution: resolution,
      });
      allFeatures.push(...featureCollection.features);
    });
      
    if (allFeatures.length > 0) {
      geoJSONMap.set(resolution, {
        type: 'FeatureCollection' as const,
        features: allFeatures,
      });
    }
    
    return geoJSONMap;
  }, [serviceZones, selectedServiceZoneId, filteredZones]);

  // ==========================================================================
  // LAYER MANAGEMENT
  // ==========================================================================

  const addH3Layers = useCallback((map: any) => {
    try {
      const resolution = 9;
      
      // Remove existing H3 layers first
      if (map.getLayer(`h3-border-${resolution}`)) map.removeLayer(`h3-border-${resolution}`);
      if (map.getLayer(`h3-fill-${resolution}`)) map.removeLayer(`h3-fill-${resolution}`);
      if (map.getSource(`h3-res-${resolution}`)) map.removeSource(`h3-res-${resolution}`);
      if (map.getLayer(`h3-zones-border-${resolution}`)) map.removeLayer(`h3-zones-border-${resolution}`);
      if (map.getLayer(`h3-zones-fill-${resolution}`)) map.removeLayer(`h3-zones-fill-${resolution}`);
      if (map.getSource(`h3-zones-${resolution}`)) map.removeSource(`h3-zones-${resolution}`);
      
      if (h3GeoJSONByResolution.size === 0 && h3ZonesGeoJSONByResolution.size === 0) return;

      const layers = map.getStyle().layers;
      let firstSymbolId: string | undefined;
      for (const layer of layers) {
        if (layer.type === 'symbol') {
          firstSymbolId = layer.id;
          break;
        }
      }

      // Add service area layer FIRST (renders underneath)
      const areaResolution = Array.from(h3GeoJSONByResolution.keys())[0];
      if (areaResolution !== undefined) {
        const geoJSON = h3GeoJSONByResolution.get(areaResolution);
        if (geoJSON && geoJSON.features.length > 0) {
          map.addSource(`h3-res-${areaResolution}`, {
            type: 'geojson',
            data: geoJSON
          });

          map.addLayer({
            id: `h3-fill-${areaResolution}`,
            type: 'fill',
            source: `h3-res-${areaResolution}`,
            paint: {
              'fill-color': '#3B82F6',
              'fill-opacity': 0.08
            }
          }, firstSymbolId);

          map.addLayer({
            id: `h3-border-${areaResolution}`,
            type: 'line',
            source: `h3-res-${areaResolution}`,
            paint: {
              'line-color': '#3B82F6',
              'line-width': 0.5,
              'line-opacity': 0.3
            }
          }, firstSymbolId);
        }
      }

      // Add service zone layer SECOND (renders on top)
      const zoneResolution = Array.from(h3ZonesGeoJSONByResolution.keys())[0];
      if (zoneResolution !== undefined) {
        const geoJSON = h3ZonesGeoJSONByResolution.get(zoneResolution);
        if (geoJSON && geoJSON.features.length > 0) {
          map.addSource(`h3-zones-${zoneResolution}`, {
            type: 'geojson',
            data: geoJSON
          });
        
          map.addLayer({
            id: `h3-zones-fill-${zoneResolution}`,
            type: 'fill',
            source: `h3-zones-${zoneResolution}`,
            paint: {
              'fill-color': '#FBBF24',
              'fill-opacity': 0.25
            }
          }, firstSymbolId);
        
          map.addLayer({
            id: `h3-zones-border-${zoneResolution}`,
            type: 'line',
            source: `h3-zones-${zoneResolution}`,
            paint: {
              'line-color': '#F59E0B',
              'line-width': 1.5,
              'line-opacity': 0.8
            }
          }, firstSymbolId);
        }
      }

    } catch (error) {
      console.error('Error adding layers:', error);
    }
  }, [h3GeoJSONByResolution, h3ZonesGeoJSONByResolution]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap();
    
    if (map && map.isStyleLoaded()) {
      addH3Layers(map);
    }
  }, [h3GeoJSONByResolution, h3ZonesGeoJSONByResolution, addH3Layers]);

  const handleMapLoad = (event: any) => {
    const map = event.target;
    if (!map.isStyleLoaded()) {
      map.once('styledata', () => addH3Layers(map));
    } else {
      addH3Layers(map);
    }
  };

  // ==========================================================================
  // ROUTE OPTIMIZATION
  // ==========================================================================

  /**
   * Fetch route geometry from Mapbox Directions API
   * @param stops - Array of route stops with latitude/longitude
   * @param depotCoords - Depot coordinates as [longitude, latitude] (Mapbox format)
   */
  const getRouteGeometry = async (stops: any[], depotCoords: [number, number]) => {
    try {
      // Build coordinates array: depot -> stops
      // Mapbox expects [lng, lat] format
      const coordinates: [number, number][] = [
        depotCoords,
        ...stops.map(stop => [stop.longitude, stop.latitude] as [number, number])
      ];
      
      // Mapbox Directions API limit is 25 coordinates
      if (coordinates.length > 25) {
        coordinates.splice(25);
      }
      
      const coords = coordinates.map(c => `${c[0]},${c[1]}`).join(';');
      const url = `https://api.mapbox.com/directions/v5/mapbox/driving/${coords}`;
      const response = await fetch(`${url}?geometries=geojson&access_token=${MAPBOX_TOKEN}`);
      
      if (!response.ok) {
        return null;
      }
      
      const data = await response.json();
      return data.routes?.[0]?.geometry ?? null;
    } catch (error) {
      console.error('Failed to fetch route geometry:', error);
      return null;
    }
  };

  const handleAutoAssignAll = async () => {
    setIsOptimizing(true);
    const allRoutes: OptimizedRoute[] = [];
    const newRouteGeometries = new Map();
    const assignedIds = new Set<string>();
    const clusterMap = new Map<number, { orders: string[], color: string, center: [number, number], coords: [number, number][] }>();
    const orderClusterMap = new Map<string, number>();
    let globalRouteIndex = 0;
    let maxHDBSCANGroups = 0;
    
    try {
      // Group unassigned orders by depot
      const ordersByDepot = filteredOrders.reduce((acc, order) => {
        if (!order.depot_id) return acc;
        if (!acc[order.depot_id]) acc[order.depot_id] = [];
        acc[order.depot_id].push(order);
        return acc;
      }, {} as Record<string, Order[]>);

      // Optimize routes for each depot
      for (const [depotId, orders] of Object.entries(ordersByDepot)) {
        if (orders.length === 0) continue;
        
        const depot = depots.find(d => d.id === depotId);
        if (!depot) continue;
        
        try {
          const result = await routeOptimizationApi.optimize({
            depot_id: depotId,
            use_clustering: true,
            min_cluster_size: 5
          });

          if (result.routes && result.routes.length > 0) {
            const depotTotalGroups = result.metadata?.total_groups || result.num_clusters || 0;
            maxHDBSCANGroups = Math.max(maxHDBSCANGroups, depotTotalGroups);
            
            // Process each route
            for (const route of result.routes) {
              const routeKey = `route-${globalRouteIndex}`;

              // Track assigned order IDs
              route.stops.forEach(stop => assignedIds.add(stop.order_id));
              
              const enrichedRoute = { ...route, routeKey, depotId };
              allRoutes.push(enrichedRoute);
              
              // Fetch geometry - Mapbox expects [lng, lat]
              const geometry = await getRouteGeometry(
                route.stops,
                [depot.longitude, depot.latitude]
              );
              if (geometry) {
                newRouteGeometries.set(routeKey, geometry);
              }
              
              globalRouteIndex++;
            }
            
            // Build route-based clusters
            const routeClusterMap = new Map<number, { orders: string[], coords: [number, number][] }>();
            
            result.routes.forEach((route, routeIndex) => {
              const routeClusterId = globalRouteIndex + routeIndex;
              const routeOrders: string[] = [];
              const routeCoords: [number, number][] = [];
              
              route.stops.forEach(stop => {
                const order = allOrders.find(o => o.id === stop.order_id);
                if (order) {
                  routeOrders.push(order.id);
                  routeCoords.push([order.longitude, order.latitude]);
                }
              });
              
              if (routeOrders.length > 0) {
                routeClusterMap.set(routeClusterId, { orders: routeOrders, coords: routeCoords });
              }
            });
            
            // Add route clusters to global cluster map
            routeClusterMap.forEach((clusterData, clusterId) => {
              const centerLng = clusterData.coords.reduce((a, b) => a + b[0], 0) / clusterData.coords.length;
              const centerLat = clusterData.coords.reduce((a, b) => a + b[1], 0) / clusterData.coords.length;
              
              clusterMap.set(clusterId, {
                orders: clusterData.orders,
                color: ROUTE_COLORS[clusterId % ROUTE_COLORS.length],
                center: [centerLng, centerLat],
                coords: clusterData.coords
              });
              
              clusterData.orders.forEach(orderId => {
                orderClusterMap.set(orderId, clusterId);
              });
            });
          }
        } catch (error) {
          console.error(`Failed to optimize depot ${depot.name}:`, error);
        }
      }

      setRoutes(allRoutes);
      setRouteGeometries(newRouteGeometries);
      
      // Track used drivers
      const newUsedDrivers = new Map<string, Set<number>>();
      allRoutes.forEach(route => {
        const dId = (route as any).depotId;
        if (dId) {
          if (!newUsedDrivers.has(dId)) newUsedDrivers.set(dId, new Set());
          newUsedDrivers.get(dId)!.add(route.vehicle_id);
        }
      });
      setUsedDrivers(newUsedDrivers);
      
      setClusters(clusterMap);
      setOrderClusters(orderClusterMap);
      setTotalGroups(maxHDBSCANGroups);
      
      setAssignedOrderIds(prev => {
        const newSet = new Set(prev);
        assignedIds.forEach(id => newSet.add(id));
        return newSet;
      });
      
    } catch (error) {
      console.error('Auto-assign failed:', error);
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleManualAssign = async (orderIds: string[], vehicleId: number, depotId: string) => {
    setIsOptimizing(true);
    
    try {
      const depot = depots.find(d => d.id === depotId);
      if (!depot) return;
      
      // Check if driver is already used
      const depotUsedDrivers = usedDrivers.get(depotId) || new Set<number>();
      if (depotUsedDrivers.has(vehicleId)) {
        alert(`Vehicle ${vehicleId + 1} is already assigned a route. Please select another vehicle.`);
        return;
      }
      
      const result = await routeOptimizationApi.optimize({
        depot_id: depotId,
        order_ids: orderIds,
        use_clustering: false,
      });
      
      if (result.solver_status === 'NO_VALID_ORDERS') {
        alert('Unable to create route: All selected orders cannot be reached from this depot.');
        return;
      }
      
      if (result.success && result.routes && result.routes.length > 0) {
        const route = result.routes[0];
        const routeKey = `route-manual-${Date.now()}-${vehicleId}`;
        
        const enrichedRoute = {
          ...route,
          routeKey,
          depotId,
          vehicle_id: vehicleId,
        };
        
        // Fetch geometry - Mapbox expects [lng, lat]
        const geometry = await getRouteGeometry(
          route.stops,
          [depot.longitude, depot.latitude]
        );
        
        setRoutes(prev => [...prev, enrichedRoute]);
        if (geometry) {
          setRouteGeometries(prev => new Map(prev).set(routeKey, geometry));
        }
        
        // Update order clusters if clustered
        if (route.cluster_id !== null && route.cluster_id !== undefined) {
          const newOrderClusterMap = new Map(orderClusters);
          route.stops.forEach((stop: any) => {
            newOrderClusterMap.set(stop.order_id, route.cluster_id!);
          });
          setOrderClusters(newOrderClusterMap);
        }
        
        // Track assigned orders
        const manualAssignedIds = new Set(route.stops.map((s: any) => s.order_id));
        setAssignedOrderIds(prev => {
          const newSet = new Set(prev);
          manualAssignedIds.forEach(id => newSet.add(id));
          return newSet;
        });
        
        // Mark driver as used
        setUsedDrivers(prev => {
          const newMap = new Map(prev);
          const depotDrivers = newMap.get(depotId) || new Set<number>();
          depotDrivers.add(vehicleId);
          newMap.set(depotId, depotDrivers);
          return newMap;
        });
      }
    } catch (error) {
      console.error('Manual assignment error:', error);
    } finally {
      setIsOptimizing(false);
    }
  };

  // ==========================================================================
  // HANDLERS
  // ==========================================================================

  const handleMapClick = useCallback((event: any) => {
    const features = event.features;
    if (features && features.length > 0) {
      const clickedFeature = features[0];
      const layerId = clickedFeature.layer.id;
      
      if (layerId && layerId.includes('route-') && layerId.includes('-line')) {
        const routeKey = layerId.replace('-line', '');
        const clickedRoute = routes.find((r: any) => {
          const rKey = r.routeKey || `route-${r.vehicle_id}`;
          return rKey === routeKey;
        });
        
        if (clickedRoute) {
          setSelectedRoute(clickedRoute);
          setSelectedOrder(null);
        }
      }
    }
  }, [routes]);

  const getOrderColor = (status: string) => {
    switch (status) {
      case 'pending': return '#6B7280';
      case 'geocoded': return '#3B82F6';
      case 'assigned': return '#EAB308';
      case 'in_transit': return '#10B981';
      case 'delivered': return '#059669';
      case 'failed': return '#EF4444';
      case 'cancelled': return '#DC2626';
      default: return '#6B7280';
    }
  };

  // ==========================================================================
  // RENDER
  // ==========================================================================

  if (loading && serviceAreas.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <Card className="w-[300px]">
          <CardContent className="p-4 space-y-4">
            <Skeleton className="h-4 w-[200px]" />
            <Skeleton className="h-[200px] w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full w-full relative flex">
      {/* Map */}
      <div className="flex-1 relative">
        <MapboxMap
          ref={mapRef}
          {...viewState}
          onMove={(evt) => setViewState(evt.viewState)}
          style={{ width: '100%', height: '100%' }}
          mapStyle="mapbox://styles/mapbox/streets-v12"
          mapboxAccessToken={MAPBOX_TOKEN}
          attributionControl={false}
          reuseMaps
          onLoad={handleMapLoad}
          onClick={handleMapClick}
          interactiveLayerIds={showRoutes ? routes.map((route: any) => {
            const routeKey = route.routeKey || `route-${route.vehicle_id}`;
            return `${routeKey}-line`;
          }) : []}
          cursor={showRoutes && routes.length > 0 ? 'pointer' : 'grab'}
        >
          {/* Route Lines */}
          {showRoutes && routes.flatMap((route, index) => {
            const routeKey = (route as any).routeKey || `route-${route.vehicle_id}`;
            const geometry = routeGeometries.get(routeKey);
            if (!geometry) return [];

            const isSelected = selectedRoute && (selectedRoute as any).routeKey === routeKey;
            const routeColor = ROUTE_COLORS[index % ROUTE_COLORS.length];
          
            return [
              <Source
                key={routeKey}
                id={routeKey}
                type="geojson"
                data={{
                  type: 'Feature',
                  properties: {},
                  geometry: geometry
                }}
              >
                <Layer
                  id={`${routeKey}-line`}
                  type="line"
                  paint={{
                    'line-color': routeColor,
                    'line-width': isSelected ? 5 : 3,
                    'line-opacity': isSelected ? 1 : 0.6
                  }}
                />
              </Source>,
              
              // Route stop dots
              ...route.stops.map((stop, stopIndex) => (
                <Marker
                  key={`${routeKey}-stop-${stop.order_id}`}
                  longitude={stop.longitude}
                  latitude={stop.latitude}
                  anchor="center"
                  onClick={(e) => {
                    e.originalEvent.stopPropagation();
                    const order = allOrders.find(o => o.id === stop.order_id);
                    if (order) setSelectedOrder(order);
                  }}
                >
                  <div 
                    className="cursor-pointer transform transition-all hover:scale-150 group relative"
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: routeColor,
                      border: '2px solid white',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.4)'
                    }}
                    title={`Stop ${stopIndex + 1}: ${stop.customer_name}`}
                  >
                    <div className="hidden group-hover:block absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded whitespace-nowrap z-50">
                      Stop {stopIndex + 1}: {stop.customer_name}
                    </div>
                  </div>
                </Marker>
              ))
            ];
          })}

          {/* Cluster Polygons */}
          {showClusters && Array.from(clusters.entries()).map(([clusterId, cluster]) => {
            if (!cluster.coords || cluster.coords.length < 3) return null;
            
            const lngs = cluster.coords.map(c => c[0]);
            const lats = cluster.coords.map(c => c[1]);
            const minLng = Math.min(...lngs);
            const maxLng = Math.max(...lngs);
            const minLat = Math.min(...lats);
            const maxLat = Math.max(...lats);
            
            const lngPadding = (maxLng - minLng) * 0.05;
            const latPadding = (maxLat - minLat) * 0.05;
            
            const polygonCoords = [
              [minLng - lngPadding, minLat - latPadding],
              [maxLng + lngPadding, minLat - latPadding],
              [maxLng + lngPadding, maxLat + latPadding],
              [minLng - lngPadding, maxLat + latPadding],
              [minLng - lngPadding, minLat - latPadding]
            ];
          
            return (
              <Source
                key={`cluster-polygon-${clusterId}`}
                id={`cluster-polygon-${clusterId}`}
                type="geojson"
                data={{
                  type: 'Feature',
                  properties: { clusterId, orderCount: cluster.orders.length },
                  geometry: {
                    type: 'Polygon',
                    coordinates: [polygonCoords]
                  }
                }}
              >
                <Layer
                  id={`cluster-fill-${clusterId}`}
                  type="fill"
                  paint={{
                    'fill-color': cluster.color,
                    'fill-opacity': 0.1
                  }}
                />
                <Layer
                  id={`cluster-border-${clusterId}`}
                  type="line"
                  paint={{
                    'line-color': cluster.color,
                    'line-width': 1,
                    'line-opacity': 0.4,
                    'line-dasharray': [3, 3]
                  }}
                />
              </Source>
            );
          })}

          {/* Depot Markers */}
          {showDepots && depots.map((depot) => (
            <Marker
              key={depot.id}
              longitude={depot.longitude}
              latitude={depot.latitude}
              anchor="bottom"
            >
              <div className="flex flex-col items-center cursor-pointer transform transition-transform hover:scale-110">
                <div className="bg-purple-600 text-white px-2 py-1 rounded text-xs font-semibold mb-1 shadow-lg whitespace-nowrap">
                  {depot.name}
                </div>
                <Warehouse 
                  className="h-10 w-10 text-purple-600"
                  fill="currentColor"
                  strokeWidth={1.5}
                  stroke="white"
                />
              </div>
            </Marker>
          ))}

          {/* Order Markers */}
          {showOrders && mapOrders.map((order) => {
            const isAssigned = assignedOrderIds.has(order.id);
            return (
              <Marker
                key={order.id}
                longitude={order.longitude}
                latitude={order.latitude}
                anchor="center"
                onClick={(e) => {
                  e.originalEvent.stopPropagation();
                  setSelectedOrder(order);
                }}
              >
                <div 
                  className="cursor-pointer transform transition-all hover:scale-150"
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    backgroundColor: isAssigned ? '#9ca3af' : getOrderColor(order.status),
                    border: '2px solid white',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
                    opacity: isAssigned ? 0.5 : 1
                  }}
                />
              </Marker>
            );
          })}
        
          {/* Order Popup */}
          {selectedOrder && (
            <Popup
              longitude={selectedOrder.longitude}
              latitude={selectedOrder.latitude}
              anchor="top"
              onClose={() => setSelectedOrder(null)}
              closeOnClick={false}
            >
              <div className="p-2 min-w-[200px]">
                <div className="font-semibold text-sm mb-2 flex items-center gap-2">
                  <Package className="h-4 w-4" />
                  {selectedOrder.order_number}
                </div>
                <div className="space-y-1 text-xs">
                  <div>
                    <span className="text-gray-600">Customer:</span>{' '}
                    <span className="font-medium">{selectedOrder.customer_name}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Address:</span>{' '}
                    <span className="text-gray-900">{selectedOrder.delivery_address}</span>
                  </div>
                  <div className="mt-2">
                    <Badge variant="secondary" className="text-xs">
                      {selectedOrder.status}
                    </Badge>
                  </div>
                </div>
              </div>
            </Popup>
          )}
        </MapboxMap>

        {/* Filter Panel */}
        <div className="absolute top-4 left-4 z-10">
          <Collapsible open={filterPanelOpen} onOpenChange={setFilterPanelOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="outline" className="mb-2 w-full justify-between bg-white shadow-lg">
                <Filter className="h-4 w-4 mr-2" />
                Filters
                {filterPanelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Card className="w-64 bg-white/95 backdrop-blur-sm shadow-lg">
                <CardContent className="p-4 space-y-4">
                  {/* Service Area Filter */}
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Service Area</Label>
                    <Select
                      value={selectedServiceAreaId}
                      onValueChange={(value) => setSelectedServiceAreaId(value as 'none' | string)}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="No Service Area" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No Service Area</SelectItem>
                        {serviceAreas.map((area) => (
                          <SelectItem key={area.id} value={area.id}>
                            {area.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Service Zone Filter */}
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Service Zone</Label>
                    <Select
                      value={selectedServiceZoneId}
                      onValueChange={(value) => setSelectedServiceZoneId(value as any)}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="No Service Zone" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No Service Zone</SelectItem>
                        <SelectItem value="all">All Zones</SelectItem>
                        {filteredZones.map((zone) => (
                          <SelectItem key={zone.id} value={zone.id}>
                            {zone.code ? `${zone.code} - ${zone.name}` : zone.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Display Options */}
                  <div className="space-y-3 pt-2 border-t">
                    <Label className="text-sm font-semibold">Display Options</Label>
                    
                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-orders" 
                        checked={showOrders}
                        onCheckedChange={(checked) => setShowOrders(checked as boolean)}
                      />
                      <label htmlFor="show-orders" className="text-sm font-medium leading-none">
                        Show Orders
                      </label>
                    </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-routes" 
                        checked={showRoutes}
                        onCheckedChange={(checked) => setShowRoutes(checked as boolean)}
                      />
                      <label htmlFor="show-routes" className="text-sm font-medium leading-none">
                        Show Routes
                      </label>
                    </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-depots" 
                        checked={showDepots}
                        onCheckedChange={(checked) => setShowDepots(checked as boolean)}
                      />
                      <label htmlFor="show-depots" className="text-sm font-medium leading-none">
                        Show Depots
                      </label>
                    </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-clusters" 
                        checked={showClusters}
                        onCheckedChange={(checked) => setShowClusters(checked as boolean)}
                      />
                      <label htmlFor="show-clusters" className="text-sm font-medium leading-none">
                        Show Clusters
                      </label>
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="pt-2 border-t space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Unassigned Orders:</span>
                      <span className="font-bold text-blue-600">{filteredOrders.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Active Routes:</span>
                      <span className="font-bold text-green-600">{routes.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Route Clusters:</span>
                      <span className="font-bold text-orange-600">{clusters.size}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">HDBSCAN Groups:</span>
                      <span className="font-bold text-gray-500 text-xs">{totalGroups !== null ? totalGroups : 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Depots:</span>
                      <span className="font-bold text-purple-600">{depots.length}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </CollapsibleContent>
          </Collapsible>
        </div>

        {/* Route Details Panel */}
        {selectedRoute && (
          <div className="absolute bottom-4 left-4 w-96 bg-white rounded-lg shadow-2xl border z-10">
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-lg">Route Details</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedRoute(null)}
                    className="h-8 w-8 p-0"
                  >
                    ✕
                  </Button>
                </div>

                <div className="space-y-3">
                  {/* Route Summary */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-blue-50 p-2 rounded">
                      <div className="text-xs text-gray-600">Vehicle ID</div>
                      <div className="font-bold text-blue-600">#{selectedRoute.vehicle_id}</div>
                    </div>
                    <div className="bg-green-50 p-2 rounded">
                      <div className="text-xs text-gray-600">Stops</div>
                      <div className="font-bold text-green-600">{selectedRoute.num_stops}</div>
                    </div>
                    <div className="bg-orange-50 p-2 rounded">
                      <div className="text-xs text-gray-600">Distance</div>
                      <div className="font-bold text-orange-600">{selectedRoute.total_distance_km.toFixed(1)} km</div>
                    </div>
                    <div className="bg-purple-50 p-2 rounded">
                      <div className="text-xs text-gray-600">Duration</div>
                      <div className="font-bold text-purple-600">{selectedRoute.estimated_duration_minutes.toFixed(0)} min</div>
                    </div>
                  </div>

                  {/* Stops List */}
                  <div>
                    <div className="font-semibold text-sm mb-2">Stops ({selectedRoute.stops.length})</div>
                    <div className="max-h-64 overflow-y-auto space-y-2">
                      {selectedRoute.stops.map((stop, idx) => (
                        <div 
                          key={stop.order_id} 
                          className="flex items-start gap-2 p-2 bg-gray-50 rounded text-xs hover:bg-gray-100 cursor-pointer"
                          onClick={() => {
                            const order = allOrders.find(o => o.id === stop.order_id);
                            if (order) setSelectedOrder(order);
                          }}
                        >
                          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center font-bold">
                            {idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="font-semibold truncate">{stop.customer_name}</div>
                            <div className="text-gray-600 truncate">{stop.address}</div>
                            <div className="text-gray-500">{stop.order_number}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Orders Sidebar */}
      <OrdersSidebar 
        orders={filteredOrders}
        depots={depots}
        onAutoAssignAll={handleAutoAssignAll}
        onManualAssign={handleManualAssign}
        isLoading={isOptimizing}
        orderClusters={orderClusters}
        usedDrivers={usedDrivers}
      />
    </div>
  );
}
