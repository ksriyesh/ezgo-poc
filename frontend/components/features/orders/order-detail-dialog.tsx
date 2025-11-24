'use client'

import { useState } from 'react'
import { Calendar, Package, User, MapPin, Truck, Clock, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Order, OrderStatus } from '@/lib/types'
import { ordersApi } from '@/lib/api/index'

interface OrderDetailDialogProps {
  order: Order | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onOrderScheduled?: () => void
}

export function OrderDetailDialog({
  order,
  open,
  onOpenChange,
  onOrderScheduled,
}: OrderDetailDialogProps) {
  const [schedulingDate, setSchedulingDate] = useState<string>('')
  const [isScheduling, setIsScheduling] = useState(false)
  const [customerOpen, setCustomerOpen] = useState(true)
  const [orderDetailsOpen, setOrderDetailsOpen] = useState(true)
  const [schedulingOpen, setSchedulingOpen] = useState(true)
  const [deliveryOpen, setDeliveryOpen] = useState(false)

  if (!order) return null

  const handleSchedule = async () => {
    if (!schedulingDate) {
      alert('Please select a date')
      return
    }

    try {
      setIsScheduling(true)
      await ordersApi.scheduleOrder(order.order_id, {
        scheduled_date: schedulingDate,
      })
      console.log('[OrderDetailDialog] Order scheduled successfully')
      onOrderScheduled?.()
      onOpenChange(false)
    } catch (error) {
      console.error('[OrderDetailDialog] Failed to schedule order:', error)
      alert('Failed to schedule order. Please try again.')
    } finally {
      setIsScheduling(false)
    }
  }

  const getStatusBadge = (status: OrderStatus) => {
    switch (status) {
      case OrderStatus.UNSCHEDULED:
        return <Badge variant="secondary" className="bg-gray-100 text-gray-800">Unscheduled</Badge>
      case OrderStatus.SCHEDULED:
        return <Badge variant="secondary" className="bg-blue-100 text-blue-800">Scheduled</Badge>
      case OrderStatus.DELAYED:
        return <Badge variant="destructive" className="bg-red-100 text-red-800">Delayed</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-CA', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const isUnscheduled = order.order_status === OrderStatus.UNSCHEDULED

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            Order Details
          </DialogTitle>
          <DialogDescription>
            Order ID: {order.order_id} • {getStatusBadge(order.order_status)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Customer Details */}
          <Collapsible open={customerOpen} onOpenChange={setCustomerOpen}>
            <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-3 hover:bg-accent">
              <div className="flex items-center gap-2 font-medium">
                <User className="h-4 w-4" />
                Customer Details
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${customerOpen ? 'rotate-180' : ''}`} />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-2 border-l-2 border-muted pl-4 ml-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Name:</span>
                  <p className="font-medium">{order.customer_name}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Customer ID:</span>
                  <p className="font-medium">{order.customer_id}</p>
                </div>
                {order.customer_phone && (
                  <div>
                    <span className="text-muted-foreground">Phone:</span>
                    <p className="font-medium">{order.customer_phone}</p>
                  </div>
                )}
                {order.customer_email && (
                  <div>
                    <span className="text-muted-foreground">Email:</span>
                    <p className="font-medium text-xs">{order.customer_email}</p>
                  </div>
                )}
              </div>
              <div>
                <span className="text-muted-foreground text-sm">Address:</span>
                <p className="font-medium text-sm flex items-start gap-1">
                  <MapPin className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  {order.delivery_address}
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Order Details */}
          <Collapsible open={orderDetailsOpen} onOpenChange={setOrderDetailsOpen}>
            <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-3 hover:bg-accent">
              <div className="flex items-center gap-2 font-medium">
                <Package className="h-4 w-4" />
                Order Information
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${orderDetailsOpen ? 'rotate-180' : ''}`} />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-2 border-l-2 border-muted pl-4 ml-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Order Date:</span>
                  <p className="font-medium">{formatDate(order.order_date)}</p>
                </div>
                {order.scheduled_date && (
                  <div>
                    <span className="text-muted-foreground">Scheduled For:</span>
                    <p className="font-medium">{new Date(order.scheduled_date).toLocaleDateString()}</p>
                  </div>
                )}
                {order.total_weight && (
                  <div>
                    <span className="text-muted-foreground">Weight:</span>
                    <p className="font-medium">{order.total_weight} kg</p>
                  </div>
                )}
                {order.total_volume && (
                  <div>
                    <span className="text-muted-foreground">Volume:</span>
                    <p className="font-medium">{order.total_volume} m³</p>
                  </div>
                )}
              </div>
              {order.notes && (
                <div>
                  <span className="text-muted-foreground text-sm">Notes:</span>
                  <p className="font-medium text-sm bg-muted/50 p-2 rounded">{order.notes}</p>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>

          {/* Scheduling Section (only for UNSCHEDULED orders) */}
          {isUnscheduled && (
            <Collapsible open={schedulingOpen} onOpenChange={setSchedulingOpen}>
              <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-3 hover:bg-accent bg-blue-50 border-blue-200">
                <div className="flex items-center gap-2 font-medium text-blue-900">
                  <Calendar className="h-4 w-4" />
                  Schedule Delivery
                </div>
                <ChevronDown className={`h-4 w-4 transition-transform ${schedulingOpen ? 'rotate-180' : ''}`} />
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 space-y-3 border-l-2 border-blue-300 pl-4 ml-3">
                <div className="space-y-2">
                  <Label htmlFor="scheduled_date">Select Delivery Date</Label>
                  <Input
                    id="scheduled_date"
                    type="date"
                    value={schedulingDate}
                    onChange={(e) => setSchedulingDate(e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                    className="w-full"
                  />
                </div>
                <Button
                  onClick={handleSchedule}
                  disabled={isScheduling || !schedulingDate}
                  className="w-full"
                >
                  {isScheduling ? 'Scheduling...' : 'Schedule Delivery'}
                </Button>
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* Delivery Details (only for SCHEDULED orders) */}
          {!isUnscheduled && (
            <Collapsible open={deliveryOpen} onOpenChange={setDeliveryOpen}>
              <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border p-3 hover:bg-accent">
                <div className="flex items-center gap-2 font-medium">
                  <Truck className="h-4 w-4" />
                  Delivery Information
                </div>
                <ChevronDown className={`h-4 w-4 transition-transform ${deliveryOpen ? 'rotate-180' : ''}`} />
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 space-y-2 border-l-2 border-muted pl-4 ml-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {order.scheduled_date && (
                    <div>
                      <span className="text-muted-foreground">Scheduled For:</span>
                      <p className="font-medium flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(order.scheduled_date).toLocaleDateString('en-CA', {
                          weekday: 'short',
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </p>
                    </div>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  View detailed delivery status on the Dashboard.
                </p>
              </CollapsibleContent>
            </Collapsible>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

