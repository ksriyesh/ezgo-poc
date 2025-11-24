"use client"

import { useState } from "react"
import { PackagePlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ordersApi } from "@/lib/api"
import type { OrderCreate } from "@/lib/types"
import { OrderStatus } from "@/lib/types/enums"

interface AddOrderDialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onOrderAdded?: () => void
}

export function AddOrderDialog({ open: controlledOpen, onOpenChange, onOrderAdded }: AddOrderDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  
  // Use controlled state if provided, otherwise use internal state
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? (onOpenChange || (() => {})) : setInternalOpen
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState<OrderCreate>({
    order_id: "",
    customer_id: "",
    customer_name: "",
    customer_phone: undefined,
    customer_email: undefined,
    delivery_address: "",
    lat: 45.4215, // Ottawa default
    lon: -75.6972,
    order_status: OrderStatus.PENDING,
    total_weight: undefined,
    total_volume: undefined,
    notes: undefined,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const order = await ordersApi.create(formData)
      // Auto-create delivery from order
      await ordersApi.createDelivery(order.order_id)
      
      setOpen(false)
      setFormData({
        order_id: "",
        customer_id: "",
        customer_name: "",
        customer_phone: undefined,
        customer_email: undefined,
        delivery_address: "",
        lat: 45.4215,
        lon: -75.6972,
        order_status: OrderStatus.PENDING,
        total_weight: undefined,
        total_volume: undefined,
        notes: undefined,
      })
      onOrderAdded?.()
    } catch (error) {
      console.error("Failed to create order:", error)
      alert("Failed to create order. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!isControlled && (
        <DialogTrigger asChild>
          <Button className="gap-2">
            <PackagePlus className="h-4 w-4" />
            Create Order
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create New Order</DialogTitle>
            <DialogDescription>
              Enter order and customer details. A delivery task will be auto-created.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="order_id" className="text-right">
                Order ID *
              </Label>
              <Input
                id="order_id"
                value={formData.order_id}
                onChange={(e) =>
                  setFormData({ ...formData, order_id: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="customer_name" className="text-right">
                Customer *
              </Label>
              <Input
                id="customer_name"
                value={formData.customer_name}
                onChange={(e) =>
                  setFormData({ ...formData, customer_name: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="customer_id" className="text-right">
                Customer ID *
              </Label>
              <Input
                id="customer_id"
                value={formData.customer_id}
                onChange={(e) =>
                  setFormData({ ...formData, customer_id: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="customer_phone" className="text-right">
                Phone
              </Label>
              <Input
                id="customer_phone"
                type="tel"
                value={formData.customer_phone || ""}
                onChange={(e) =>
                  setFormData({ ...formData, customer_phone: e.target.value || undefined })
                }
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="customer_email" className="text-right">
                Email
              </Label>
              <Input
                id="customer_email"
                type="email"
                value={formData.customer_email || ""}
                onChange={(e) =>
                  setFormData({ ...formData, customer_email: e.target.value || undefined })
                }
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="delivery_address" className="text-right">
                Address *
              </Label>
              <Textarea
                id="delivery_address"
                value={formData.delivery_address}
                onChange={(e) =>
                  setFormData({ ...formData, delivery_address: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Location *</Label>
              <div className="col-span-3 grid grid-cols-2 gap-2">
                <Input
                  type="number"
                  step="any"
                  placeholder="Latitude"
                  value={formData.lat}
                  onChange={(e) =>
                    setFormData({ ...formData, lat: Number(e.target.value) })
                  }
                  required
                />
                <Input
                  type="number"
                  step="any"
                  placeholder="Longitude"
                  value={formData.lon}
                  onChange={(e) =>
                    setFormData({ ...formData, lon: Number(e.target.value) })
                  }
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="notes" className="text-right">
                Notes
              </Label>
              <Textarea
                id="notes"
                value={formData.notes || ""}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value || undefined })
                }
                className="col-span-3"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Creating..." : "Create Order"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

