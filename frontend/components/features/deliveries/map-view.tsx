'use client';

import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { Map as MapboxMap, MapRef, Marker, Popup, Source, Layer } from 'react-map-gl';
import { Filter, ChevronDown, ChevronUp, MapPin, Package, Warehouse } from 'lucide-react';
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
  getH3ResolutionForZoom,
  calculateBoundingBox,
} from '@/lib/map/h3-utils';
import { OrdersSidebar } from './orders-sidebar';
import { cellToBoundary } from 'h3-js';
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

  // ============================================================================
  // DATA FETCHING
  // ============================================================================

  useEffect(() => {
    const fetchAllData = async () => {
      console.log('[MapView] Loading all data...');
        setLoading(true);
      
      try {
        // Load data with one H3 resolution (resolution 9 - good balance)
        const [areas, zones, orders, depotsData] = await Promise.all([
          serviceAreasApi.getAll({ 
          include_h3: true,
          resolutions: "9", // Single resolution for simplicity
          active_only: true 
          }),
          serviceZonesApi.getAll({
            include_h3: true,
            resolutions: "9", // Single resolution for simplicity
            active_only: true
          }),
          ordersApi.getAll({ limit: 1000 }),
          depotsApi.getAll({ active_only: true })
        ]);
        
        setServiceAreas(Array.isArray(areas) ? areas : []);
        setServiceZones(Array.isArray(zones) ? zones : []);
        setAllOrders(Array.isArray(orders) ? orders : []);
        setDepots(Array.isArray(depotsData) ? depotsData : []);
        
        console.log('[MapView] Data loaded:', {
          areas: Array.isArray(areas) ? areas.length : 0,
          zones: Array.isArray(zones) ? zones.length : 0,
          orders: Array.isArray(orders) ? orders.length : 0,
          depots: Array.isArray(depotsData) ? depotsData.length : 0
        });
        
        // DEBUG: Check coordinate values
        if (Array.isArray(orders) && orders.length > 0) {
          console.log('[MapView] 🔍 DEBUG - First 3 orders coordinates:');
          orders.slice(0, 3).forEach((order, idx) => {
            console.log(`  Order ${idx + 1}: lat=${order.latitude}, lng=${order.longitude}, address=${order.delivery_address?.substring(0, 50)}`);
            if (order.latitude < 0 || order.latitude > 90 || order.longitude > 0 || order.longitude < -90) {
              console.warn(`  ⚠️  Order ${idx + 1} has suspicious coordinates! Expected: lat ~45, lng ~-75`);
            }
          });
        }
        
        if (Array.isArray(depotsData) && depotsData.length > 0) {
          console.log('[MapView] 🔍 DEBUG - All depots coordinates:');
          depotsData.forEach((depot, idx) => {
            console.log(`  Depot ${idx + 1} (${depot.name}): lat=${depot.latitude}, lng=${depot.longitude}`);
            if (depot.latitude < 0 || depot.latitude > 90 || depot.longitude > 0 || depot.longitude < -90) {
              console.warn(`  ⚠️  Depot ${idx + 1} has suspicious coordinates! Expected: lat ~45, lng ~-75`);
            }
          });
        }
        
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
        console.error('[MapView] Failed to fetch data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAllData();
  }, []);

  // ============================================================================
  // FILTERED DATA
  // ============================================================================

  // Orders for MAP display - show ALL orders (assigned + unassigned)
  const mapOrders = useMemo(() => {
    if (!showOrders) {
      return [];
    }
    
    let filtered = allOrders;
    
    // Filter by status
    filtered = filtered.filter(order => 
      order.status === 'pending' || order.status === 'geocoded'
    );
    
    // Filter by selected zone (if not 'none' or 'all')
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

  // ============================================================================
  // GEOJSON GENERATION
  // ============================================================================

  // Simplified: Render resolution 9 only
  const h3GeoJSONByResolution = useMemo(() => {
    const geoJSONMap = new Map<number, any>();
    
    // Don't show any areas if "No Service Area" is selected
    if (serviceAreas.length === 0 || selectedServiceAreaId === 'none') return geoJSONMap;

    const areasToRender = serviceAreas.filter(a => a.id === selectedServiceAreaId);

    // Use resolution 9 (good balance between detail and performance)
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

  // Simplified: Render resolution 9 only
  const h3ZonesGeoJSONByResolution = useMemo(() => {
    const geoJSONMap = new Map<number, any>();
    
    if (serviceZones.length === 0) return geoJSONMap;
    
    const zonesToRender = selectedServiceZoneId === 'none' 
      ? []
      : selectedServiceZoneId === 'all' 
        ? filteredZones
        : filteredZones.filter(z => z.id === selectedServiceZoneId);
    
    // Use resolution 9 (good balance between detail and performance)
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

  // ============================================================================
  // LAYER MANAGEMENT
  // ============================================================================

  // Simplified: Only add layers for resolution 9
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

      // Add service area layer (only ONE resolution now)
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
              'fill-opacity': 0.15
          }
        }, firstSymbolId);

        map.addLayer({
            id: `h3-border-${areaResolution}`,
    type: 'line',
            source: `h3-res-${areaResolution}`,
    paint: {
            'line-color': '#2563EB',
            'line-width': 0.5,
              'line-opacity': 0.4
          }
        }, firstSymbolId);
        }
      }

      // Add service zone layer (only ONE resolution now)
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
              'fill-opacity': 0.2
          }
        }, firstSymbolId);
        
        map.addLayer({
            id: `h3-zones-border-${zoneResolution}`,
    type: 'line',
            source: `h3-zones-${zoneResolution}`,
    paint: {
              'line-color': '#F59E0B',
              'line-width': 1,
            'line-opacity': 0.6
          }
        }, firstSymbolId);
        }
      }

    } catch (error) {
      console.error('[MapView] Error adding layers:', error);
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

  // ============================================================================
  // AUTO ASSIGN ROUTES
  // ============================================================================

  const getRouteGeometry = async (stops: any[], depotCoords: [number, number]) => {
    try {
      // Build coordinates array: depot -> stops (return to depot implied)
      // Mapbox expects [lng, lat] format
      const coordinates: [number, number][] = [
        depotCoords, // Already in [lng, lat] format from caller
        ...stops.map(stop => [stop.longitude, stop.latitude] as [number, number]) // DB stores lat/lng separately, use as [lng, lat] for Mapbox
      ];
      
      // Mapbox Directions API limit is 25 coordinates
      if (coordinates.length > 25) {
        console.warn(`[MapView] Route has ${coordinates.length} coordinates, exceeding Mapbox limit of 25. Truncating...`);
        // Keep depot + first 24 stops
        coordinates.splice(25);
      }
      
      const coords = coordinates.map(c => `${c[0]},${c[1]}`).join(';');
      const url = `https://api.mapbox.com/directions/v5/mapbox/driving/${coords}`;
      const response = await fetch(`${url}?geometries=geojson&access_token=${MAPBOX_TOKEN}`);
      
      if (!response.ok) {
        console.error(`[MapView] Mapbox Directions API error: ${response.status} ${response.statusText}`);
        const errorData = await response.json();
        console.error('[MapView] Error details:', errorData);
        return null;
      }
      
      const data = await response.json();
      
      if (data.routes && data.routes[0]) {
        return data.routes[0].geometry;
      }
      return null;
    } catch (error) {
      console.error('[MapView] Failed to fetch route geometry:', error);
      return null;
    }
  };

  const handleAutoAssignAll = async () => {
    setIsOptimizing(true);
    const allRoutes: OptimizedRoute[] = [];
    const newRouteGeometries = new Map();
    const assignedOrderIds = new Set<string>();
    const clusterMap = new Map<number, { orders: string[], color: string, center: [number, number], coords: [number, number][] }>();
    const orderClusterMap = new Map<string, number>();
    let globalRouteIndex = 0;
    let maxHDBSCANGroups = 0; // Track max HDBSCAN groups across all depots
    
    try {
      // Group unassigned orders by depot
      const ordersByDepot = filteredOrders.reduce((acc, order) => {
        if (!order.depot_id) return acc;
        if (!acc[order.depot_id]) acc[order.depot_id] = [];
        acc[order.depot_id].push(order);
        return acc;
      }, {} as Record<string, Order[]>);

      console.log('[MapView] 🚀 Auto-assigning for depots:', Object.keys(ordersByDepot).length);
      console.log('[MapView] 📦 Orders by depot:', Object.entries(ordersByDepot).map(([id, orders]) => ({
        depotId: id,
        depotName: depots.find(d => d.id === id)?.name,
        orderCount: orders.length
      })));

      // Optimize routes for each depot
      for (const [depotId, orders] of Object.entries(ordersByDepot)) {
        if (orders.length === 0) continue;
        
        const depot = depots.find(d => d.id === depotId);
        if (!depot) {
          console.warn(`[MapView] ⚠️ Depot not found for ID: ${depotId}`);
          continue;
        }
        
        console.log(`[MapView] 🔄 Optimizing ${orders.length} orders for depot "${depot.name}" (${depotId})`);
        
        try {
          const result = await routeOptimizationApi.optimize({
            depot_id: depotId,
            use_clustering: true,
            min_cluster_size: 5
          });

          console.log(`[MapView] 📥 API Response for depot "${depot.name}":`, {
            success: result.success,
            routesCount: result.routes?.length || 0,
            totalOrders: result.total_orders,
            totalDistance: result.total_distance_km,
            unassignedCount: result.unassigned_orders?.length || 0,
            solverStatus: result.solver_status,
            usedClustering: result.used_clustering
          });

          // Consider it successful if routes were created, even if success is false (e.g., PARTIAL_SUCCESS)
          if (result.routes && result.routes.length > 0) {
            console.log(`[MapView] ✅ Created ${result.routes.length} routes for depot "${depot.name}" (success: ${result.success}, status: ${result.solver_status})`);
            console.log(`[MapView] 📊 Clustering info:`, {
              numClusters: result.num_clusters,
              outlierCount: result.outlier_count,
              totalGroups: result.metadata?.total_groups,
              usedClustering: result.used_clustering
            });
            
            // Extract cluster assignments from metadata if available
            // Use original_cluster_assignments for visualization (shows outliers as separate groups)
            const clusterAssignments = result.metadata?.original_cluster_assignments || result.metadata?.cluster_assignments || {};
            const depotTotalGroups = result.metadata?.total_groups || result.num_clusters || 0;
            
            console.log(`[MapView] 🔍 Cluster assignments for depot "${depot.name}":`, {
              hasOriginal: !!result.metadata?.original_cluster_assignments,
              hasRegular: !!result.metadata?.cluster_assignments,
              assignmentCount: Object.keys(clusterAssignments).length,
              sampleAssignments: Object.entries(clusterAssignments).slice(0, 5),
              usedClustering: result.used_clustering
            });
            
            // Track HDBSCAN total groups for reference (accumulate across depots)
            // This is just for display - we use route clusters, not HDBSCAN clusters
            maxHDBSCANGroups = Math.max(maxHDBSCANGroups, depotTotalGroups);
            
            // Add routes with unique identifiers and fetch geometry
            for (const route of result.routes) {
              // Create unique route key using global index
              const routeKey = `route-${globalRouteIndex}`;
              
              console.log(`[MapView]   Route ${globalRouteIndex}:`, {
                vehicleId: route.vehicle_id,
                stops: route.num_stops,
                distance: route.total_distance_km,
                stopIds: route.stops.map(s => s.order_id)
              });

              // Track assigned order IDs
              route.stops.forEach(stop => assignedOrderIds.add(stop.order_id));
              
              // Add the unique key to the route
              const enrichedRoute = {
                ...route,
                routeKey,
                depotId
              };
              
              allRoutes.push(enrichedRoute);
              
              // Fetch geometry for this route
              // Mapbox expects [lng, lat] format
              // NOTE: Database has coordinates swapped, so we swap them here
              const geometry = await getRouteGeometry(
                route.stops,
                [depot.latitude, depot.longitude] as [number, number]
              );
              if (geometry) {
                newRouteGeometries.set(routeKey, geometry);
    } else {
                console.warn(`[MapView] ⚠️ Failed to get geometry for route ${routeKey}`);
              }
              
              globalRouteIndex++;
      }
            
            // Build route-based clusters (one cluster per route) instead of HDBSCAN clusters
            // This makes clusters match routes: 7 routes = 7 clusters
            const routeClusterMap = new Map<number, { orders: string[], coords: [number, number][] }>();
            
            // Create one cluster per route
            result.routes.forEach((route, routeIndex) => {
              const routeClusterId = globalRouteIndex + routeIndex; // Use global route index as cluster ID
              const routeOrders: string[] = [];
              const routeCoords: [number, number][] = [];
              
              route.stops.forEach(stop => {
                const order = allOrders.find(o => o.id === stop.order_id);
                if (order) {
                  routeOrders.push(order.id);
                  // Store coords in [lng, lat] format for Mapbox/GeoJSON
                  routeCoords.push([order.longitude, order.latitude]);
                }
              });
              
              if (routeOrders.length > 0) {
                routeClusterMap.set(routeClusterId, {
                  orders: routeOrders,
                  coords: routeCoords
                });
              }
            });
            
            // Add route clusters to global cluster map
            routeClusterMap.forEach((clusterData, clusterId) => {
              // Calculate cluster center (coords are in [lng, lat] format)
              const centerLng = clusterData.coords.reduce((a, b) => a + b[0], 0) / clusterData.coords.length;
              const centerLat = clusterData.coords.reduce((a, b) => a + b[1], 0) / clusterData.coords.length;
              
              clusterMap.set(clusterId, {
                orders: clusterData.orders,
                color: ROUTE_COLORS[clusterId % ROUTE_COLORS.length],
                center: [centerLng, centerLat], // [lng, lat] for Mapbox
                coords: clusterData.coords
              });
              
              // Map orders to cluster
              clusterData.orders.forEach(orderId => {
                orderClusterMap.set(orderId, clusterId);
              });
            });
            
            console.log(`[MapView] 📊 Created ${routeClusterMap.size} route-based clusters for depot "${depot.name}" (matching ${result.routes.length} routes)`);
    } else {
            if (result.solver_status === 'NO_VALID_ORDERS') {
              console.warn(`[MapView] ⚠️ No valid orders for depot "${depot.name}" - all orders unroutable`);
            } else {
              console.error(`[MapView] ❌ Optimization failed or no routes for depot "${depot.name}"`, result);
            }
          }
        } catch (error) {
          console.error(`[MapView] ❌ Failed to optimize depot "${depot.name}" (${depotId}):`, error);
        }
      }

      setRoutes(allRoutes);
      setRouteGeometries(newRouteGeometries);
      
      // Track used drivers from auto-assign
      const newUsedDrivers = new Map<string, Set<number>>();
      allRoutes.forEach(route => {
        const depotId = (route as any).depotId;
        if (depotId) {
          if (!newUsedDrivers.has(depotId)) {
            newUsedDrivers.set(depotId, new Set());
          }
          newUsedDrivers.get(depotId)!.add(route.vehicle_id);
        }
      });
      setUsedDrivers(newUsedDrivers);
      
      // Clusters are already built from routes in the loop above
      setClusters(clusterMap);
      setOrderClusters(orderClusterMap);
      setTotalGroups(maxHDBSCANGroups); // Set HDBSCAN groups for reference
      console.log('[MapView] 📊 Route clusters created:', clusterMap.size, '(should match routes:', allRoutes.length, ')');
      console.log('[MapView] 📊 HDBSCAN groups:', maxHDBSCANGroups);
      console.log('[MapView] 📊 Order-to-cluster mappings:', orderClusterMap.size);
      console.log('[MapView] 📊 Cluster details:', Array.from(clusterMap.entries()).map(([id, c]) => ({
        id,
        orders: c.orders.length,
        center: c.center,
        color: c.color
      })));
      
      console.log('[MapView] 🎯 Summary:');
      console.log(`  Total routes created: ${allRoutes.length}`);
      console.log(`  Total route geometries: ${newRouteGeometries.size}`);
      console.log(`  Assigned order IDs: ${assignedOrderIds.size}`);
      console.log(`  Clusters: ${clusterMap.size}`);
      
      // Track assigned orders (don't remove from allOrders - keep them visible on map)
      setAssignedOrderIds(prev => {
        const newSet = new Set(prev);
        assignedOrderIds.forEach(id => newSet.add(id));
        return newSet;
      });
      
    } catch (error) {
      console.error('[MapView] ❌ Auto-assign failed:', error);
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleManualAssign = async (orderIds: string[], vehicleId: number, depotId: string) => {
    setIsOptimizing(true);
    console.log('[MapView] 🔧 Manual assignment:', {orderIds, vehicleId, depotId});
    
    try {
      const depot = depots.find(d => d.id === depotId);
      if (!depot) {
        console.error('[MapView] Depot not found:', depotId);
        return;
      }
      
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
      
      console.log('[MapView] 📥 Manual assignment result:', {
        success: result.success,
        routesCount: result.routes?.length || 0,
        totalOrders: result.total_orders,
        status: result.solver_status,
      });
      
      // Handle unroutable orders
      if (result.solver_status === 'NO_VALID_ORDERS') {
        console.error('[MapView] ❌ All selected orders are unroutable from this depot');
        alert('Unable to create route: All selected orders cannot be reached from this depot. These orders may be in unreachable locations.');
        return;
      }
      
      if (result.success && result.routes && result.routes.length > 0) {
        const route = result.routes[0];
        const routeKey = `route-manual-${Date.now()}-${vehicleId}`;
        
        console.log('[MapView] ✅ Created manual route:', {
          routeKey,
          stops: route.num_stops,
          distance: route.total_distance_km,
        });
        
        // Enrich route with unique key and depot ID
        const enrichedRoute = {
          ...route,
          routeKey,
          depotId,
          vehicle_id: vehicleId, // Override with selected vehicle
        };
        
        // Fetch geometry for this route
        // Mapbox expects [lng, lat] format
        // NOTE: Database has coordinates swapped, so we swap them here
        const geometry = await getRouteGeometry(
          route.stops,
          [depot.latitude, depot.longitude] as [number, number]
        );
        
        // Update state
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
        
        // Track assigned orders (don't remove from allOrders - keep them visible on map)
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
        
        console.log('[MapView] ✅ Manual assignment complete. Driver marked as used:', vehicleId);
    } else {
        console.error('[MapView] ❌ Manual assignment failed or returned no routes');
      }
    } catch (error) {
      console.error('[MapView] ❌ Manual assignment error:', error);
    } finally {
      setIsOptimizing(false);
    }
  };

  // ============================================================================
  // HANDLERS & CALLBACKS
  // ============================================================================

  // Handle map clicks for route selection
  const handleMapClick = useCallback((event: any) => {
    const features = event.features;
    if (features && features.length > 0) {
      const clickedFeature = features[0];
      const layerId = clickedFeature.layer.id;
      
      // Check if a route line was clicked
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

  // ============================================================================
  // ORDER PIN COLOR
  // ============================================================================

  const getOrderColor = (status: string) => {
    switch (status) {
      case 'pending': return '#6B7280'; // gray
      case 'geocoded': return '#3B82F6'; // blue
      case 'assigned': return '#EAB308'; // yellow
      case 'in_transit': return '#10B981'; // green
      case 'delivered': return '#059669'; // dark green
      case 'failed': return '#EF4444'; // red
      case 'cancelled': return '#DC2626'; // dark red
      default: return '#6B7280';
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

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
          
            // Return array of Source and Markers (all direct children of Map)
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
                    if (order) {
                      setSelectedOrder(order);
                    }
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
                    {/* Tooltip on hover */}
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
            
            // Create a simple bounding polygon (convex hull approximation)
            // For simplicity, we'll create a polygon from the bounding box with some padding
            const lngs = cluster.coords.map(c => c[0]);
            const lats = cluster.coords.map(c => c[1]);
            const minLng = Math.min(...lngs);
            const maxLng = Math.max(...lngs);
            const minLat = Math.min(...lats);
            const maxLat = Math.max(...lats);
            
            // Add padding (about 5% of the range)
            const lngPadding = (maxLng - minLng) * 0.05;
            const latPadding = (maxLat - minLat) * 0.05;
            
            const polygonCoords = [
              [minLng - lngPadding, minLat - latPadding],
              [maxLng + lngPadding, minLat - latPadding],
              [maxLng + lngPadding, maxLat + latPadding],
              [minLng - lngPadding, maxLat + latPadding],
              [minLng - lngPadding, minLat - latPadding] // Close polygon
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
                    'fill-opacity': 0.1  // Increased opacity for better visibility
                  }}
                />
                <Layer
                  id={`cluster-border-${clusterId}`}
                  type="line"
                  paint={{
                    'line-color': cluster.color,
                    'line-width': 1,  // Thinner border
                    'line-opacity': 0.4,  // Increased opacity for better visibility
                    'line-dasharray': [3, 3]  // Subtle dashed line
                  }}
                />
              </Source>
            );
          })}

          {/* Depot Markers */}
          {showDepots && depots.map((depot) => (
            <Marker
              key={depot.id}
              longitude={depot.latitude}
              latitude={depot.longitude}
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

          {/* Order Markers - All orders (assigned shown grayed out) - Small circular dots */}
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
                backgroundColor: isAssigned ? '#9ca3af' : getOrderColor(order.status), // Gray for assigned
                border: '2px solid white',
                boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
                opacity: isAssigned ? 0.5 : 1 // Lower opacity for assigned
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
                      <label
                        htmlFor="show-orders"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        Show Orders
                      </label>
                  </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-routes" 
                        checked={showRoutes}
                        onCheckedChange={(checked) => setShowRoutes(checked as boolean)}
                      />
                      <label
                        htmlFor="show-routes"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        Show Routes
                      </label>
                  </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-depots" 
                        checked={showDepots}
                        onCheckedChange={(checked) => setShowDepots(checked as boolean)}
                      />
                      <label
                        htmlFor="show-depots"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        Show Depots
                      </label>
                  </div>

                    <div className="flex items-center space-x-2">
                      <Checkbox 
                        id="show-clusters" 
                        checked={showClusters}
                        onCheckedChange={(checked) => setShowClusters(checked as boolean)}
                      />
                      <label
                        htmlFor="show-clusters"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
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
