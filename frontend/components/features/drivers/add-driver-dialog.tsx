"use client"

import { useState } from "react"
import { Plus } from "lucide-react"
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
import { driversApi } from "@/lib/api"
import type { DriverCreate } from "@/lib/types"
import { DriverAvailability } from "@/lib/types/enums"

interface AddDriverDialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onDriverAdded?: () => void
}

export function AddDriverDialog({ open: controlledOpen, onOpenChange, onDriverAdded }: AddDriverDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  
  // Use controlled state if provided, otherwise use internal state
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? (onOpenChange || (() => {})) : setInternalOpen
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState<DriverCreate>({
    driver_id: "",
    name: "",
    phone: "",
    email: "",
    license_number: "",
    license_expiry: undefined,
    availability_status: DriverAvailability.AVAILABLE,
    assigned_vehicle_id: undefined,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      await driversApi.create(formData)
      setOpen(false)
      setFormData({
        driver_id: "",
        name: "",
        phone: "",
        email: "",
        license_number: "",
        license_expiry: undefined,
        availability_status: DriverAvailability.AVAILABLE,
        assigned_vehicle_id: undefined,
      })
      onDriverAdded?.()
    } catch (error) {
      console.error("Failed to create driver:", error)
      alert("Failed to create driver. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!isControlled && (
        <DialogTrigger asChild>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Driver
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add New Driver</DialogTitle>
            <DialogDescription>
              Enter driver information to add them to the system.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="driver_id" className="text-right">
                Driver ID *
              </Label>
              <Input
                id="driver_id"
                value={formData.driver_id}
                onChange={(e) =>
                  setFormData({ ...formData, driver_id: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                Name *
              </Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="phone" className="text-right">
                Phone *
              </Label>
              <Input
                id="phone"
                type="tel"
                value={formData.phone}
                onChange={(e) =>
                  setFormData({ ...formData, phone: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="email" className="text-right">
                Email *
              </Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="license_number" className="text-right">
                License # *
              </Label>
              <Input
                id="license_number"
                value={formData.license_number}
                onChange={(e) =>
                  setFormData({ ...formData, license_number: e.target.value })
                }
                className="col-span-3"
                required
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="license_expiry" className="text-right">
                License Expiry
              </Label>
              <Input
                id="license_expiry"
                type="date"
                value={formData.license_expiry || ""}
                onChange={(e) =>
                  setFormData({ ...formData, license_expiry: e.target.value || undefined })
                }
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="status" className="text-right">
                Status
              </Label>
              <Select
                value={formData.availability_status}
                onValueChange={(value: DriverAvailability) =>
                  setFormData({ ...formData, availability_status: value })
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={DriverAvailability.AVAILABLE}>Available</SelectItem>
                  <SelectItem value={DriverAvailability.ON_DUTY}>On Duty</SelectItem>
                  <SelectItem value={DriverAvailability.OFF_DUTY}>Off Duty</SelectItem>
                  <SelectItem value={DriverAvailability.UNAVAILABLE}>Unavailable</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Adding..." : "Add Driver"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

