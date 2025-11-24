"use client"

import { useState } from "react"
import { Truck } from "lucide-react"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { vehiclesApi } from "@/lib/api"
import type { VehicleCreate } from "@/lib/types"
import { VehicleType, VehicleStatus } from "@/lib/types/enums"

interface AddVehicleDialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onVehicleAdded?: () => void
}

export function AddVehicleDialog({ open: controlledOpen, onOpenChange, onVehicleAdded }: AddVehicleDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  
  // Use controlled state if provided, otherwise use internal state
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? (onOpenChange || (() => {})) : setInternalOpen
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState<VehicleCreate>({
    vehicle_id: "",
    license_plate: "",
    vehicle_type: VehicleType.VAN,
    capacity_weight: 1000,
    capacity_volume: 10,
    status: VehicleStatus.AVAILABLE,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      await vehiclesApi.create(formData)
      setOpen(false)
      setFormData({
        vehicle_id: "",
        license_plate: "",
        vehicle_type: VehicleType.VAN,
        capacity_weight: 1000,
        capacity_volume: 10,
        status: VehicleStatus.AVAILABLE,
      })
      onVehicleAdded?.()
    } catch (error) {
      console.error("Failed to create vehicle:", error)
      alert("Failed to create vehicle. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!isControlled && (
        <DialogTrigger asChild>
          <Button variant="outline" className="gap-2">
            <Truck className="h-4 w-4" />
            Add Vehicle
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add New Vehicle</DialogTitle>
            <DialogDescription>
              Enter vehicle information to add it to the fleet.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="vehicle_id" className="text-right">
                Vehicle ID *
              </Label>
              <Input
                id="vehicle_id"
                value={formData.vehicle_id}
                onChange={(e) =>
                  setFormData({ ...formData, vehicle_id: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="license_plate" className="text-right">
                License Plate *
              </Label>
              <Input
                id="license_plate"
                value={formData.license_plate}
                onChange={(e) =>
                  setFormData({ ...formData, license_plate: e.target.value.toUpperCase() })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="vehicle_type" className="text-right">
                Type *
              </Label>
              <Select
                value={formData.vehicle_type}
                onValueChange={(value: VehicleType) =>
                  setFormData({ ...formData, vehicle_type: value })
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={VehicleType.VAN}>Van</SelectItem>
                  <SelectItem value={VehicleType.SMALL_TRUCK}>Small Truck</SelectItem>
                  <SelectItem value={VehicleType.LARGE_TRUCK}>Large Truck</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="capacity_weight" className="text-right">
                Weight (kg) *
              </Label>
              <Input
                id="capacity_weight"
                type="number"
                value={formData.capacity_weight}
                onChange={(e) =>
                  setFormData({ ...formData, capacity_weight: Number(e.target.value) })
                }
                className="col-span-3"
                required
                min="0"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="capacity_volume" className="text-right">
                Volume (m³) *
              </Label>
              <Input
                id="capacity_volume"
                type="number"
                step="0.1"
                value={formData.capacity_volume}
                onChange={(e) =>
                  setFormData({ ...formData, capacity_volume: Number(e.target.value) })
                }
                className="col-span-3"
                required
                min="0"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="status" className="text-right">
                Status
              </Label>
              <Select
                value={formData.status}
                onValueChange={(value: VehicleStatus) =>
                  setFormData({ ...formData, status: value })
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={VehicleStatus.AVAILABLE}>Available</SelectItem>
                  <SelectItem value={VehicleStatus.IN_USE}>In Use</SelectItem>
                  <SelectItem value={VehicleStatus.MAINTENANCE}>Maintenance</SelectItem>
                  <SelectItem value={VehicleStatus.OUT_OF_SERVICE}>Out of Service</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Adding..." : "Add Vehicle"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

